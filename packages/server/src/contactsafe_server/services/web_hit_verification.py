"""Verify web search hits refer to the intended contact before writing claims."""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlparse

from contactsafe_server.services.org_search import is_generic_personal_domain
from contactsafe_server.services.person_search_query import is_generic_email
from contactsafe_server.services.web_search_types import WebSearchHit

_LINKEDIN_PROFILE_RE: re.Pattern[str] = re.compile(
    r"linkedin\.com/in/([a-zA-Z0-9\-_%]+)",
    flags=re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class VerifiedHits:
    employer_hits: list[WebSearchHit]
    confidence: float
    skip_employment: bool
    skip_categories: bool
    verified_social_profiles: dict[str, str]


def _normalize_linkedin_url(url: str) -> str:
    return url.lower().rstrip("/").split("?")[0]


def _linkedin_profile_slug(url: str) -> str | None:
    match: re.Match[str] | None = _LINKEDIN_PROFILE_RE.search(url)
    if match is None:
        return None
    return match.group(1).lower()


def _name_slug(display_name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", display_name.lower())


def _hit_blob(hits: list[WebSearchHit]) -> str:
    parts: list[str] = []
    for hit in hits:
        if hit.title:
            parts.append(hit.title)
        parts.extend(hit.highlights)
        if hit.text:
            parts.append(hit.text)
        if hit.url:
            parts.append(hit.url)
    return " ".join(parts).lower()


def _email_in_blob(email: str, blob: str) -> bool:
    return email.lower() in blob


def _domain_in_blob(domain: str, blob: str) -> bool:
    normalized: str = domain.lower().removeprefix("www.")
    return normalized in blob or normalized.split(".")[0] in blob


def _org_in_blob(org_hint: str, blob: str) -> bool:
    normalized_hint: str = org_hint.lower().strip()
    if not normalized_hint:
        return False
    return normalized_hint in blob


def _linkedin_url_matches(known_url: str, hit_url: str) -> bool:
    known_slug: str | None = _linkedin_profile_slug(known_url)
    hit_slug: str | None = _linkedin_profile_slug(hit_url)
    if known_slug is None or hit_slug is None:
        return _normalize_linkedin_url(known_url) == _normalize_linkedin_url(hit_url)
    return known_slug == hit_slug


def _conflicting_linkedin_in_hits(
    hits: list[WebSearchHit],
    known_linkedin_url: str,
) -> bool:
    known_slug: str | None = _linkedin_profile_slug(known_linkedin_url)
    if known_slug is None:
        return False
    for hit in hits:
        if not hit.url or "linkedin.com/in/" not in hit.url.lower():
            continue
        hit_slug: str | None = _linkedin_profile_slug(hit.url)
        if hit_slug is not None and hit_slug != known_slug:
            return True
    return False


def _social_profile_matches_name(url: str, display_name: str) -> bool:
    slug: str = _name_slug(display_name)
    if not slug or len(slug) < 4:
        return False
    parsed = urlparse(url)
    path: str = (parsed.path or "").lower()
    host: str = (parsed.hostname or "").lower()
    if "linkedin.com" in host:
        profile_slug: str | None = _linkedin_profile_slug(url)
        if profile_slug is None:
            return False
        normalized_profile: str = re.sub(r"[^a-z0-9]+", "", profile_slug)
        return slug in normalized_profile or normalized_profile in slug
    return slug in path.replace("/", "").replace("-", "")


def verify_web_hits(
    *,
    hits: list[WebSearchHit],
    email: str,
    display_name: str,
    org_hint: str | None,
    known_linkedin_url: str | None,
    social_profiles: dict[str, str],
) -> VerifiedHits:
    blob: str = _hit_blob(hits)
    generic_email: bool = is_generic_email(email)
    work_domain: str | None = None
    if "@" in email and not generic_email:
        work_domain = email.rsplit("@", 1)[1].lower()

    has_linkedin_match: bool = False
    has_email_match: bool = _email_in_blob(email, blob)
    has_org_match: bool = bool(org_hint and _org_in_blob(org_hint, blob))
    has_domain_match: bool = bool(work_domain and _domain_in_blob(work_domain, blob))

    if known_linkedin_url:
        for hit in hits:
            if hit.url and _linkedin_url_matches(known_linkedin_url, hit.url):
                has_linkedin_match = True
                break
        if _conflicting_linkedin_in_hits(hits, known_linkedin_url):
            return VerifiedHits(
                employer_hits=[],
                confidence=0.0,
                skip_employment=True,
                skip_categories=True,
                verified_social_profiles={},
            )

    identity_confirmed: bool = (
        has_linkedin_match
        or has_email_match
        or has_org_match
        or has_domain_match
    )

    if generic_email and not identity_confirmed:
        verified_socials: dict[str, str] = {
            platform: url
            for platform, url in social_profiles.items()
            if _social_profile_matches_name(url, display_name)
        }
        return VerifiedHits(
            employer_hits=[],
            confidence=0.0,
            skip_employment=True,
            skip_categories=True,
            verified_social_profiles=verified_socials,
        )

    confidence: float = 0.7
    if has_linkedin_match:
        confidence = 0.85
    elif has_email_match:
        confidence = 0.8
    elif has_org_match or has_domain_match:
        confidence = 0.75

    if work_domain and not is_generic_personal_domain(work_domain):
        identity_confirmed = True

    return VerifiedHits(
        employer_hits=hits if identity_confirmed else [],
        confidence=confidence if identity_confirmed else 0.0,
        skip_employment=not identity_confirmed,
        skip_categories=not identity_confirmed,
        verified_social_profiles=dict(social_profiles) if identity_confirmed else {},
    )
