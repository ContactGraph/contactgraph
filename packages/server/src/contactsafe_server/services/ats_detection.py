"""Detect ATS provider and board token from organization careers URLs.

Detection runs in three layers:

* Layer 1 (`detect_ats_from_url`) — pure, instant. Matches when the careers URL's
  own hostname is a known ATS host (e.g. ``boards.greenhouse.io/stripe``).
* Layer 2 (`detect_ats_from_page`) — async fallback that looks *through* a vanity
  careers domain (e.g. ``mercury.com/jobs``) by fetching the page and finding the
  real ATS board it redirects to or links out to. Only used where the caller can
  afford a network round-trip (org enrichment).
* Layer 3 (`detect_ats_by_probe`) — async last resort for careers sites that
  render their listings client-side and so never mention the ATS in their HTML
  (e.g. ``hubspot.com/careers``, whose board is Greenhouse ``hubspotjobs``).
  Derives candidate tokens from the org's name and domain and asks each ATS API
  whether such a board exists.
"""

from __future__ import annotations

import logging
import re
from collections import Counter
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Literal, cast
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


# Layer-3 probe tuning.
_PROBE_TIMEOUT_SECONDS: float = 8.0
# Hard cap on probes per org so a bad name can't fan out into dozens of calls.
_MAX_PROBES_PER_ORG: int = 12
# Suffixes companies commonly append to their board token.
_TOKEN_SUFFIXES: tuple[str, ...] = ("", "jobs", "careers", "hq", "inc")
# Corporate suffixes to strip from a canonical name before tokenizing.
_NAME_NOISE_RE: re.Pattern[str] = re.compile(
    r"\b(inc|inc\.|llc|ltd|limited|corp|corporation|co|company|holdings|group|"
    r"technologies|technology|labs|software|the)\b",
    flags=re.IGNORECASE,
)

# Board APIs that answer "does this token exist, and does it have jobs?".
_PROBE_ENDPOINTS: tuple[tuple[AtsProvider, str], ...] = (
    ("greenhouse", "https://boards-api.greenhouse.io/v1/boards/{token}/jobs"),
    ("lever", "https://api.lever.co/v0/postings/{token}?mode=json"),
    ("ashby", "https://api.ashbyhq.com/posting-api/job-board/{token}"),
)

# A probe reports how many postings a candidate board has (0 if it doesn't exist).
BoardProbe = Callable[[str, str], Awaitable[int]]


def _job_count_from_payload(payload: object) -> int:
    """Count postings in a board API response, tolerating each provider's shape."""
    if isinstance(payload, list):
        return len(cast(list[object], payload))
    if isinstance(payload, dict):
        typed: dict[str, object] = cast(dict[str, object], payload)
        for key in ("jobs", "postings"):
            value: object | None = typed.get(key)
            if isinstance(value, list):
                return len(cast(list[object], value))
    return 0


async def _default_board_probe(provider: str, url: str) -> int:
    async with httpx.AsyncClient(
        timeout=_PROBE_TIMEOUT_SECONDS,
        follow_redirects=True,
        headers={"User-Agent": _USER_AGENT},
    ) as client:
        response = await client.get(url)
        if response.status_code != 200:
            return 0
        try:
            return _job_count_from_payload(response.json())
        except Exception:
            return 0


def candidate_board_tokens(
    canonical_name: str | None,
    careers_url: str | None,
) -> list[str]:
    """Guess board tokens for an org, most likely first.

    Derived from the careers-URL domain label and the canonical name, each with
    the suffixes companies tend to append (``hubspot`` -> ``hubspotjobs``).
    """
    bases: list[str] = []

    if careers_url:
        host: str = (urlparse(careers_url.strip()).hostname or "").lower()
        host = re.sub(r"^www\.", "", host)
        label: str = host.split(".")[0] if host else ""
        if label and label not in {"jobs", "careers", "boards"}:
            bases.append(label)

    if canonical_name:
        cleaned: str = _NAME_NOISE_RE.sub(" ", canonical_name.lower())
        squashed: str = re.sub(r"[^a-z0-9]+", "", cleaned)
        if squashed:
            bases.append(squashed)
        hyphenated: str = re.sub(r"[^a-z0-9]+", "-", cleaned).strip("-")
        if hyphenated and hyphenated != squashed:
            bases.append(hyphenated)

    tokens: list[str] = []
    for base in bases:
        if len(base) < 2:
            continue
        for suffix in _TOKEN_SUFFIXES:
            token: str = f"{base}{suffix}"
            if token not in tokens:
                tokens.append(token)
    return tokens


async def detect_ats_by_probe(
    canonical_name: str | None,
    careers_url: str | None,
    *,
    probe: BoardProbe | None = None,
) -> AtsDetectionResult:
    """Ask each ATS API directly whether a plausible board token exists.

    A board is only accepted when it returns at least one posting. HubSpot's
    Greenhouse board is ``hubspotjobs``; the obvious guess ``hubspot`` also
    returns HTTP 200 but with zero jobs, so existence alone is not enough.

    Never raises — probing is best-effort.
    """
    tokens: list[str] = candidate_board_tokens(canonical_name, careers_url)
    if not tokens:
        return AtsDetectionResult(provider=None, board_token=None)

    prober: BoardProbe = probe or _default_board_probe
    attempts: int = 0
    for token in tokens:
        for provider, template in _PROBE_ENDPOINTS:
            if attempts >= _MAX_PROBES_PER_ORG:
                logger.debug("probe cap reached for %s", canonical_name)
                return AtsDetectionResult(provider=None, board_token=None)
            attempts += 1
            try:
                count: int = await prober(provider, template.format(token=token))
            except Exception:
                logger.debug("probe failed for %s/%s", provider, token, exc_info=True)
                continue
            if count > 0:
                return AtsDetectionResult(provider=provider, board_token=token)
    return AtsDetectionResult(provider=None, board_token=None)


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


async def apply_ats_probe_detection_to_org(
    org: Org,
    *,
    probe: BoardProbe | None = None,
) -> None:
    """Layer-3 fallback — a no-op unless Layers 1 and 2 both came up empty.

    Separate from :func:`apply_ats_page_detection_to_org` because it guesses
    rather than reads: it should only run once cheaper, evidence-based detection
    has failed.
    """
    if org.ats_board_token:
        return
    result: AtsDetectionResult = await detect_ats_by_probe(
        org.canonical_name,
        org.careers_url,
        probe=probe,
    )
    if result.provider is not None:
        org.ats_provider = result.provider
        org.ats_board_token = result.board_token
