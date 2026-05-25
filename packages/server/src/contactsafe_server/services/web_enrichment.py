"""Apply web search results to Person enrichment fields."""

import re
from dataclasses import dataclass
from urllib.parse import urlparse

from contactsafe_server.db.models import Person
from contactsafe_server.services.category_inference import infer_categories_from_contact
from contactsafe_server.services.org_enrichment import should_apply_enrichment_org
from contactsafe_server.services.web_search_types import WebSearchHit

_ROLE_PATTERNS: list[tuple[str, str]] = [
    (r"\bgeneral partner\b", "General Partner"),
    (r"\bmanaging partner\b", "Managing Partner"),
    (r"\bventure partner\b", "Venture Partner"),
    (r"\bpartner\b", "Partner"),
    (r"\binvestor\b", "Investor"),
    (r"\bprincipal\b", "Principal"),
    (r"\bassociate\b", "Associate"),
    (r"\bfounder\b", "Founder"),
    (r"\bco-founder\b", "Co-Founder"),
    (r"\bceo\b", "CEO"),
    (r"\bchief executive officer\b", "CEO"),
    (r"\bengineer\b", "Engineer"),
    (r"\bsoftware engineer\b", "Software Engineer"),
    (r"\bproduct manager\b", "Product Manager"),
    (r"\brevops\b", "RevOps"),
]

_SOCIAL_HOSTS: dict[str, str] = {
    "linkedin.com": "linkedin",
    "github.com": "github",
    "twitter.com": "twitter",
    "x.com": "twitter",
    "bsky.app": "bluesky",
    "substack.com": "substack",
    "medium.com": "medium",
}


@dataclass(frozen=True, slots=True)
class PersonWebHints:
    categories: list[str]
    current_role: str | None
    org_name: str | None
    social_profiles: dict[str, str]
    activity_blob: str


# Backward-compatible alias.
ExaPersonHints = PersonWebHints


def extract_hints_from_web_hits(
    *,
    hits: list[WebSearchHit],
    email: str,
    display_name: str,
    org_hint: str | None,
    pitch_outbound_count: int = 0,
    activity_posts: str = "",
) -> PersonWebHints:
    blob: str = _context_blob(hits)
    combined_blob: str = f"{blob} {activity_posts}".strip()
    categories: list[str] = infer_categories_from_contact(
        email=email,
        display_name=f"{display_name} {combined_blob}",
        org_name=org_hint,
        pitch_outbound_count=pitch_outbound_count,
    )
    role: str | None = _extract_role(combined_blob)
    org_name: str | None = _extract_org_name(combined_blob, org_hint)
    social_profiles: dict[str, str] = _extract_social_profiles(hits)
    return PersonWebHints(
        categories=categories,
        current_role=role,
        org_name=org_name,
        social_profiles=social_profiles,
        activity_blob=activity_posts,
    )


def extract_hints_from_exa_hits(
    *,
    hits: list[WebSearchHit],
    email: str,
    display_name: str,
    org_hint: str | None,
    pitch_outbound_count: int = 0,
) -> PersonWebHints:
    return extract_hints_from_web_hits(
        hits=hits,
        email=email,
        display_name=display_name,
        org_hint=org_hint,
        pitch_outbound_count=pitch_outbound_count,
    )


def apply_web_hints_to_person(person: Person, hints: PersonWebHints) -> None:
    """Legacy direct-mutation helper — superseded by claim writes in the new graph."""
    if hints.categories:
        merged: list[str] = list(dict.fromkeys([*person.inferred_categories, *hints.categories]))
        person.inferred_categories = merged
    primary_email: str = person.primary_email or ""
    if hints.current_role and not person.current_role and primary_email:
        local_part: str = primary_email.rsplit("@", 1)[0].lower()
        if local_part not in {"info", "team", "hello", "support", "contact", "customer_service"}:
            person.current_role = hints.current_role
    if hints.org_name and should_apply_enrichment_org(
        primary_email=primary_email,
        proposed_org=hints.org_name,
    ):
        person.current_org_name = hints.org_name
    if hints.social_profiles:
        existing: dict[str, str] = dict(person.social_profiles or {})
        existing.update(hints.social_profiles)
        person.social_profiles = existing
    if hints.activity_blob.strip() and not person.bio_summary:
        person.bio_summary = hints.activity_blob.strip()[:2000]


def apply_exa_hints_to_person(person: Person, hints: PersonWebHints) -> None:
    apply_web_hints_to_person(person, hints)


def _context_blob(hits: list[WebSearchHit]) -> str:
    parts: list[str] = []
    for hit in hits:
        if hit.title:
            parts.append(hit.title)
        parts.extend(hit.highlights)
        if hit.text:
            parts.append(hit.text[:1500])
    return " ".join(parts)


def extract_social_profiles_from_hits(hits: list[WebSearchHit]) -> dict[str, str]:
    return _extract_social_profiles(hits)


def _extract_social_profiles(hits: list[WebSearchHit]) -> dict[str, str]:
    profiles: dict[str, str] = {}
    for hit in hits:
        if not hit.url:
            continue
        parsed = urlparse(hit.url)
        host: str = (parsed.hostname or "").lower().removeprefix("www.")
        for domain, key in _SOCIAL_HOSTS.items():
            if host == domain or host.endswith(f".{domain}"):
                if key not in profiles:
                    profiles[key] = hit.url
                break
    return profiles


def _extract_role(blob: str) -> str | None:
    for pattern, label in _ROLE_PATTERNS:
        if re.search(pattern, blob, flags=re.IGNORECASE):
            return label
    return None


def _extract_org_name(blob: str, org_hint: str | None) -> str | None:
    linkedin_match: re.Match[str] | None = re.search(
        r"[-–|]\s*[^-|]{2,80}\s*[-–|]\s*([A-Z][A-Za-z0-9&.\s'-]{2,60})\s*(?:\||$|·|\n)",
        blob,
    )
    if linkedin_match is not None:
        candidate: str = linkedin_match.group(1).strip()
        if candidate and not _looks_like_role(candidate):
            return candidate

    for pattern in (
        r"\bpartner\s+at\s+([A-Z][A-Za-z0-9&.\s'-]{2,60})",
        r"\binvestor\s+at\s+([A-Z][A-Za-z0-9&.\s'-]{2,60})",
        r"\bworks?\s+at\s+([A-Z][A-Za-z0-9&.\s'-]{2,60})",
        r"\bat\s+([A-Z][A-Za-z0-9&.\s'-]{2,60})\s*(?:\||·|,|\.)",
    ):
        match: re.Match[str] | None = re.search(pattern, blob)
        if match is not None:
            org: str = match.group(1).strip().rstrip(".")
            if org and not _looks_like_role(org):
                return org
    return None


def _looks_like_role(value: str) -> bool:
    lowered: str = value.lower()
    role_words: frozenset[str] = frozenset(
        {"partner", "investor", "founder", "engineer", "ceo", "director", "manager"}
    )
    return lowered in role_words
