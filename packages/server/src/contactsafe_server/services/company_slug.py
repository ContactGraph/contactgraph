"""URL slug helpers for public company pages."""

from __future__ import annotations

import re
import unicodedata

_SLUG_RE: re.Pattern[str] = re.compile(r"[^a-z0-9]+")


def company_slug(name: str) -> str:
    normalized: str = unicodedata.normalize("NFKD", name)
    ascii_name: str = normalized.encode("ascii", "ignore").decode("ascii")
    slug: str = _SLUG_RE.sub("-", ascii_name.lower()).strip("-")
    return slug or "company"


def domain_slug(primary_domain: str | None) -> str | None:
    if primary_domain is None:
        return None
    value: str = primary_domain.strip().lower()
    if value.startswith("www."):
        value = value.removeprefix("www.")
    if not value:
        return None
    return value.split(".", maxsplit=1)[0] or None


def company_slug_candidates(
    name: str,
    primary_domain: str | None,
) -> tuple[str, ...]:
    candidates: list[str] = []
    name_slug: str = company_slug(name)
    candidates.append(name_slug)
    domain: str | None = domain_slug(primary_domain)
    if domain is not None and domain not in candidates:
        candidates.append(domain)
    return tuple(candidates)


def matches_company_slug(
    slug: str,
    name: str,
    primary_domain: str | None,
) -> bool:
    normalized_slug: str = slug.strip().lower()
    return normalized_slug in company_slug_candidates(name, primary_domain)
