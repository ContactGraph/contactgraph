"""Detect ATS provider and board token from organization careers URLs.

Detection runs in two layers:

* Layer 1 (`detect_ats_from_url`) — pure, instant. Matches when the careers URL's
  own hostname is a known ATS host (e.g. ``boards.greenhouse.io/stripe``).
* Layer 2 (`detect_ats_from_page`) — async fallback that looks *through* a vanity
  careers domain (e.g. ``mercury.com/jobs``) by fetching the page and finding the
  real ATS board it redirects to or links out to. Only used where the caller can
  afford a network round-trip (org enrichment).
"""

from __future__ import annotations

import logging
import re
from collections import Counter
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Literal
from urllib.parse import urlparse

import httpx

from contactsafe_server.db.models import Org

logger: logging.Logger = logging.getLogger(__name__)

AtsProvider = Literal["greenhouse", "lever", "ashby"]

# Layer-2 page fetch tuning.
_PAGE_FETCH_TIMEOUT_SECONDS: float = 10.0
_MAX_BODY_CHARS: int = 1_000_000
_USER_AGENT: str = "ContactGraphBot/1.0 (+https://contactgraph.ai)"

# Greenhouse path segments that are never board tokens (embed scaffolding).
_RESERVED_SLUGS: frozenset[str] = frozenset({"embed"})

# Board links that may appear in the body of a vanity careers page.
_ATS_LINK_IN_PAGE_RE: re.Pattern[str] = re.compile(
    r"https?://(?:boards\.greenhouse\.io|job-boards\.greenhouse\.io|"
    r"jobs\.lever\.co|jobs\.ashbyhq\.com)/[A-Za-z0-9_.-]+",
    flags=re.IGNORECASE,
)
# Greenhouse JS/iframe embed form: ...greenhouse.io/embed/job_board?for=<token>
_GREENHOUSE_EMBED_FOR_RE: re.Pattern[str] = re.compile(
    r"greenhouse\.io/embed/job_board(?:/js)?\?for=([A-Za-z0-9_-]+)",
    flags=re.IGNORECASE,
)

_GREENHOUSE_HOST_RE: re.Pattern[str] = re.compile(
    r"^(?:boards|job-boards)\.greenhouse\.io$",
    flags=re.IGNORECASE,
)
_GREENHOUSE_PATH_RE: re.Pattern[str] = re.compile(
    r"^/([^/?#]+)",
    flags=re.IGNORECASE,
)
_LEVER_HOST_RE: re.Pattern[str] = re.compile(
    r"^jobs\.lever\.co$",
    flags=re.IGNORECASE,
)
_ASHBY_HOST_RE: re.Pattern[str] = re.compile(
    r"^jobs\.ashbyhq\.com$",
    flags=re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class AtsDetectionResult:
    provider: AtsProvider | None
    board_token: str | None


def detect_ats_from_url(careers_url: str) -> AtsDetectionResult:
    normalized: str = careers_url.strip()
    if not normalized:
        return AtsDetectionResult(provider=None, board_token=None)

    parsed = urlparse(normalized)
    host: str = (parsed.hostname or "").lower()
    if not host:
        return AtsDetectionResult(provider=None, board_token=None)

    path_match: re.Match[str] | None = _GREENHOUSE_PATH_RE.match(parsed.path or "")
    slug: str | None = path_match.group(1) if path_match is not None else None
    if slug and _GREENHOUSE_HOST_RE.match(host):
        return AtsDetectionResult(provider="greenhouse", board_token=slug)

    if slug and _LEVER_HOST_RE.match(host):
        return AtsDetectionResult(provider="lever", board_token=slug)

    if slug and _ASHBY_HOST_RE.match(host):
        return AtsDetectionResult(provider="ashby", board_token=slug)

    return AtsDetectionResult(provider=None, board_token=None)


def apply_ats_detection_to_org(org: Org) -> None:
    if org.careers_url is None or not org.careers_url.strip():
        org.ats_provider = None
        org.ats_board_token = None
        return
    result: AtsDetectionResult = detect_ats_from_url(org.careers_url)
    org.ats_provider = result.provider
    org.ats_board_token = result.board_token


@dataclass(frozen=True, slots=True)
class FetchedPage:
    """Minimal result of fetching a careers page for Layer-2 detection."""

    final_url: str
    body: str


# A fetcher takes a URL and returns the fetched page, or None if it couldn't be
# fetched. Injectable so tests (and callers) can supply pages without real HTTP.
PageFetcher = Callable[[str], Awaitable["FetchedPage | None"]]


async def _default_page_fetcher(url: str) -> FetchedPage | None:
    async with httpx.AsyncClient(
        timeout=_PAGE_FETCH_TIMEOUT_SECONDS,
        follow_redirects=True,
        headers={"User-Agent": _USER_AGENT},
    ) as client:
        response = await client.get(url)
        response.raise_for_status()
        body: str = response.text
        if len(body) > _MAX_BODY_CHARS:
            body = body[:_MAX_BODY_CHARS]
        return FetchedPage(final_url=str(response.url), body=body)


async def detect_ats_from_page(
    careers_url: str,
    *,
    fetch: PageFetcher | None = None,
) -> AtsDetectionResult:
    """Look through a vanity careers domain to the ATS board behind it.

    Fetches ``careers_url`` and detects the ATS by, in order:

    1. **Redirect** — if following redirects landed on a known ATS host, detect
       straight from the final URL.
    2. **Page body** — otherwise scan for links to a known ATS board (or a
       Greenhouse ``?for=<token>`` embed) and take the most frequently referenced
       ``(provider, token)``.

    Reuses :func:`detect_ats_from_url` for the actual host/token rules, so there is
    a single source of truth. Never raises: any fetch/parse failure yields an empty
    result, since detection is best-effort and must not break enrichment.
    """
    normalized: str = careers_url.strip()
    if not normalized:
        return AtsDetectionResult(provider=None, board_token=None)

    fetcher: PageFetcher = fetch or _default_page_fetcher
    try:
        page: FetchedPage | None = await fetcher(normalized)
    except Exception:
        logger.warning("ATS page fetch failed for %s", normalized, exc_info=True)
        return AtsDetectionResult(provider=None, board_token=None)
    if page is None:
        return AtsDetectionResult(provider=None, board_token=None)

    # 1) Redirected onto a real ATS host.
    from_final: AtsDetectionResult = detect_ats_from_url(page.final_url)
    if from_final.provider is not None:
        return from_final

    # 2) The board is linked/embedded in the page body.
    candidates: list[tuple[AtsProvider, str]] = []
    for link in _ATS_LINK_IN_PAGE_RE.findall(page.body):
        detected: AtsDetectionResult = detect_ats_from_url(link)
        token: str | None = detected.board_token
        if (
            detected.provider is not None
            and token is not None
            and token.lower() not in _RESERVED_SLUGS
        ):
            candidates.append((detected.provider, token))
    for embed_token in _GREENHOUSE_EMBED_FOR_RE.findall(page.body):
        candidates.append(("greenhouse", embed_token))

    if not candidates:
        return AtsDetectionResult(provider=None, board_token=None)

    (provider, board_token), _ = Counter(candidates).most_common(1)[0]
    return AtsDetectionResult(provider=provider, board_token=board_token)


async def apply_ats_page_detection_to_org(
    org: Org,
    *,
    fetch: PageFetcher | None = None,
) -> None:
    """Layer-2 fallback applied to an org — a no-op unless Layer 1 came up empty.

    Call this after :func:`apply_ats_detection_to_org`. It only fetches when the
    org still has no token but does have a careers URL, so already-detected orgs
    pay no network cost.
    """
    if org.ats_board_token:
        return
    if org.careers_url is None or not org.careers_url.strip():
        return
    result: AtsDetectionResult = await detect_ats_from_page(org.careers_url, fetch=fetch)
    if result.provider is not None:
        org.ats_provider = result.provider
        org.ats_board_token = result.board_token
