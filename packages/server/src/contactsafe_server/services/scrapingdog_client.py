"""Async client for ScrapingDog's LinkedIn profile scraper API."""

from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass, field
from datetime import date
from typing import cast

import httpx

from contactsafe_server.config import Settings

logger: logging.Logger = logging.getLogger(__name__)

_LINKEDIN_SLUG_RE: re.Pattern[str] = re.compile(
    r"(?:https?://)?(?:[\w.]+\.)?linkedin\.com/in/([^/?#]+)",
    flags=re.IGNORECASE,
)
_PRESENT_TOKENS: frozenset[str] = frozenset({"present", "current"})

_request_lock: asyncio.Lock = asyncio.Lock()
_last_request_at: float = 0.0


class ScrapingDogError(Exception):
    """Base error for ScrapingDog API failures."""


class ScrapingDogPendingError(ScrapingDogError):
    """Profile scrape accepted but not ready yet (HTTP 202)."""

    def __init__(self, *, retry_after_seconds: float, link_id: str) -> None:
        self.retry_after_seconds: float = retry_after_seconds
        self.link_id: str = link_id
        super().__init__(
            f"ScrapingDog profile {link_id} pending; retry after {retry_after_seconds}s"
        )


class ScrapingDogRateLimitError(ScrapingDogError):
    """HTTP 429 from ScrapingDog."""


@dataclass(frozen=True, slots=True)
class ScrapedLinkedInExperience:
    company: str
    title: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    is_current: bool = False
    location: str | None = None


@dataclass(frozen=True, slots=True)
class ScrapedLinkedInProfile:
    link_id: str
    name: str | None = None
    headline: str | None = None
    location: str | None = None
    profile_url: str | None = None
    current_company: str | None = None
    current_title: str | None = None
    experiences: tuple[ScrapedLinkedInExperience, ...] = ()
    raw: dict[str, object] = field(default_factory=dict)


def extract_linkedin_slug(linkedin_url: str) -> str | None:
    """Extract the LinkedIn profile slug from a full or partial URL."""
    match: re.Match[str] | None = _LINKEDIN_SLUG_RE.search(linkedin_url.strip())
    if match is None:
        return None
    slug: str = match.group(1).strip().rstrip("/")
    return slug or None


def linkedin_profile_url(link_id: str) -> str:
    return f"https://www.linkedin.com/in/{link_id}"


class ScrapingDogClient:
    def __init__(self, settings: Settings) -> None:
        self._settings: Settings = settings
        self._api_key: str | None = settings.scrapingdog_api_key
        self._base_url: str = settings.scrapingdog_base_url.rstrip("/")
        self._timeout: float = settings.scrapingdog_request_timeout_seconds
        self._semaphore: asyncio.Semaphore = asyncio.Semaphore(
            max(1, settings.scrapingdog_concurrency),
        )

    @property
    def is_configured(self) -> bool:
        return bool(self._api_key)

    async def fetch_profile(
        self,
        link_id: str,
        *,
        premium: bool = True,
    ) -> ScrapedLinkedInProfile:
        if not self._api_key:
            raise ScrapingDogError("SCRAPINGDOG_API_KEY is not configured")

        normalized_link_id: str = link_id.strip().strip("/")
        if not normalized_link_id:
            raise ScrapingDogError("LinkedIn profile id is empty")

        async with self._semaphore:
            await self._rate_limit()
            params: dict[str, str] = {
                "api_key": self._api_key,
                "type": "profile",
                "id": normalized_link_id,
                "webhook": "false",
                "fresh": "false",
            }
            if premium:
                params["premium"] = "true"

            try:
                async with httpx.AsyncClient(timeout=self._timeout) as http:
                    response = await http.get(
                        f"{self._base_url}/profile",
                        params=params,
                    )
            except httpx.TimeoutException as exc:
                raise ScrapingDogError(
                    f"ScrapingDog request timed out for {normalized_link_id}: {exc}",
                ) from exc
            except httpx.HTTPError as exc:
                raise ScrapingDogError(
                    f"ScrapingDog HTTP error for {normalized_link_id}: {exc}",
                ) from exc

            if response.status_code == 202:
                raise ScrapingDogPendingError(
                    retry_after_seconds=self._settings.scrapingdog_retry_delay_seconds,
                    link_id=normalized_link_id,
                )
            if response.status_code == 429:
                raise ScrapingDogRateLimitError("ScrapingDog rate limit exceeded")
            if response.status_code == 403:
                message: str = response.text[:300]
                raise ScrapingDogError(
                    f"ScrapingDog returned HTTP 403 for {normalized_link_id}: {message}",
                )
            if response.status_code in {400, 404} and not premium:
                return await self.fetch_profile(normalized_link_id, premium=True)
            if response.status_code != 200:
                raise ScrapingDogError(
                    f"ScrapingDog returned HTTP {response.status_code} for {normalized_link_id}",
                )

            payload: object = response.json()
            profile_payload: dict[str, object] = _coerce_profile_payload(payload)

            return parse_scrapingdog_profile(
                profile_payload,
                link_id=normalized_link_id,
            )

    async def _rate_limit(self) -> None:
        global _last_request_at

        delay: float = max(0.0, self._settings.scrapingdog_request_delay_seconds)
        if delay <= 0:
            return

        async with _request_lock:
            loop: asyncio.AbstractEventLoop = asyncio.get_running_loop()
            now: float = loop.time()
            elapsed: float = now - _last_request_at
            if elapsed < delay:
                await asyncio.sleep(delay - elapsed)
            _last_request_at = loop.time()


def _coerce_profile_payload(payload: object) -> dict[str, object]:
    if isinstance(payload, list):
        if not payload:
            raise ScrapingDogError("ScrapingDog returned an empty profile list")
        first_item: object = payload[0]
        if not isinstance(first_item, dict):
            raise ScrapingDogError("ScrapingDog profile list item was not a JSON object")
        return cast(dict[str, object], first_item)
    if isinstance(payload, dict):
        return cast(dict[str, object], payload)
    raise ScrapingDogError("ScrapingDog response was not a JSON object")


def parse_scrapingdog_profile(
    payload: dict[str, object],
    *,
    link_id: str,
) -> ScrapedLinkedInProfile:
    name: str | None = (
        _coerce_str(payload.get("name"))
        or _coerce_str(payload.get("fullName"))
        or _coerce_str(payload.get("full_name"))
    )
    headline: str | None = _coerce_str(payload.get("headline")) or _coerce_str(
        payload.get("description"),
    )
    if headline == "":
        headline = None
    about: str | None = _coerce_str(payload.get("about"))
    if about and not headline:
        headline = about
    location: str | None = _coerce_str(payload.get("location")) or _coerce_str(
        payload.get("address"),
    )
    profile_url: str | None = (
        _coerce_str(payload.get("profileUrl"))
        or _coerce_str(payload.get("url"))
        or linkedin_profile_url(link_id)
    )

    raw_experiences: list[object] = _coerce_list(
        payload.get("experience")
        or payload.get("experiences")
        or payload.get("position"),
    )
    experiences: list[ScrapedLinkedInExperience] = [
        parsed
        for index, item in enumerate(raw_experiences)
        if (parsed := _parse_experience_item(item, index=index)) is not None
    ]

    current_company: str | None = None
    current_title: str | None = None
    for exp in experiences:
        if exp.is_current:
            current_company = exp.company
            current_title = exp.title
            break
    if current_company is None and experiences:
        current_company = experiences[0].company
        current_title = experiences[0].title

    return ScrapedLinkedInProfile(
        link_id=link_id,
        name=name,
        headline=headline,
        location=location,
        profile_url=profile_url,
        current_company=current_company,
        current_title=current_title,
        experiences=tuple(experiences),
        raw=payload,
    )


def _parse_experience_item(item: object, *, index: int = 0) -> ScrapedLinkedInExperience | None:
    if not isinstance(item, dict):
        return None

    company: str | None = (
        _coerce_str(item.get("company"))
        or _coerce_str(item.get("company_name"))
        or _coerce_str(item.get("organization"))
    )
    if company is None:
        return None

    title: str | None = (
        _coerce_str(item.get("title"))
        or _coerce_str(item.get("position"))
        or _coerce_str(item.get("role"))
    )
    location: str | None = _coerce_str(item.get("location"))
    duration: str | None = _coerce_str(item.get("duration")) or _coerce_str(item.get("date"))
    end_raw: str | None = (
        _coerce_str(item.get("end_date"))
        or _coerce_str(item.get("endDate"))
        or _coerce_str(item.get("ends_at"))
    )
    start_raw: str | None = (
        _coerce_str(item.get("start_date"))
        or _coerce_str(item.get("startDate"))
        or _coerce_str(item.get("starts_at"))
    )

    is_current: bool = bool(item.get("is_current") or item.get("isCurrent"))
    if end_raw and end_raw.strip().lower() in _PRESENT_TOKENS:
        is_current = True
        end_raw = None
    elif not end_raw and index == 0:
        is_current = True
    if duration and "present" in duration.lower():
        is_current = True

    return ScrapedLinkedInExperience(
        company=company,
        title=title,
        start_date=_parse_partial_date(start_raw),
        end_date=_parse_partial_date(end_raw),
        is_current=is_current,
        location=location,
    )


def _parse_partial_date(raw: str | None) -> date | None:
    if raw is None or not raw.strip():
        return None
    text: str = raw.strip()
    if text.lower() in _PRESENT_TOKENS:
        return None
    try:
        return date.fromisoformat(text)
    except ValueError:
        pass
    from datetime import datetime

    for fmt in ("%b %Y", "%B %Y", "%Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def _coerce_str(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    stripped: str = value.strip()
    return stripped or None


def _coerce_list(value: object) -> list[object]:
    if isinstance(value, list):
        return value
    return []
