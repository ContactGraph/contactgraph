"""Apply Exa web search results to Person enrichment fields."""

import re
from dataclasses import dataclass

from contactsafe_server.db.models import Person
from contactsafe_server.services.category_inference import infer_categories_from_contact
from contactsafe_server.services.exa_client import ExaSearchHit

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


@dataclass(frozen=True, slots=True)
class ExaPersonHints:
    categories: list[str]
    current_role: str | None
    org_name: str | None


def extract_hints_from_exa_hits(
    *,
    hits: list[ExaSearchHit],
    email: str,
    display_name: str,
    org_hint: str | None,
    pitch_outbound_count: int = 0,
) -> ExaPersonHints:
    blob: str = _context_blob(hits)
    categories: list[str] = infer_categories_from_contact(
        email=email,
        display_name=f"{display_name} {blob}",
        org_name=org_hint,
        pitch_outbound_count=pitch_outbound_count,
    )
    role: str | None = _extract_role(blob)
    org_name: str | None = _extract_org_name(blob, org_hint)
    return ExaPersonHints(
        categories=categories,
        current_role=role,
        org_name=org_name,
    )


def apply_exa_hints_to_person(person: Person, hints: ExaPersonHints) -> None:
    if hints.categories:
        merged: list[str] = list(dict.fromkeys([*person.inferred_categories, *hints.categories]))
        person.inferred_categories = merged
    if hints.current_role and not person.current_role:
        person.current_role = hints.current_role
    if hints.org_name:
        person.current_org_name = hints.org_name


def _context_blob(hits: list[ExaSearchHit]) -> str:
    parts: list[str] = []
    for hit in hits:
        if hit.title:
            parts.append(hit.title)
        parts.extend(hit.highlights)
        if hit.text:
            parts.append(hit.text[:1500])
    return " ".join(parts)


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
