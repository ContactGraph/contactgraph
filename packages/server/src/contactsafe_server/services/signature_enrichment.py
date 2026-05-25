"""Extract employer and role hints from email signature blocks in snippets."""

import re
from dataclasses import dataclass

_ROLE_LINE_PATTERNS: list[tuple[str, str]] = [
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
    (r"\bvp\b", "VP"),
    (r"\bvice president\b", "Vice President"),
    (r"\bdirector\b", "Director"),
    (r"\bengineer\b", "Engineer"),
    (r"\bsoftware engineer\b", "Software Engineer"),
    (r"\bproduct manager\b", "Product Manager"),
]

_ORG_PATTERNS: list[str] = [
    r"\b(?:partner|investor|director|manager|engineer|founder|ceo|vp)\s+(?:at|@)\s+([A-Z][A-Za-z0-9&. '-]{2,60})",
    r"\b([A-Z][A-Za-z0-9&. '-]{2,60})\s*\|\s*(?:partner|investor|founder|ceo|engineer|director)\b",
    r"\|\s*([A-Z][A-Za-z0-9&. '-]{2,60})\s*$",
]

_PHONE_RE: re.Pattern[str] = re.compile(
    r"(?:\+?\d{1,3}[\s.-]?)?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}"
)


@dataclass(frozen=True, slots=True)
class SignatureHints:
    current_role: str | None
    org_name: str | None
    phone_numbers: list[str]
    location: str | None


def parse_signature_from_snippets(
    snippets: list[str],
    *,
    display_name: str,
) -> SignatureHints:
    """Best-effort signature parse from Gmail snippets (often truncated)."""
    if not snippets:
        return SignatureHints(
            current_role=None,
            org_name=None,
            phone_numbers=[],
            location=None,
        )

    combined: str = "\n".join(snippets)
    tail: str = combined[-1200:] if len(combined) > 1200 else combined
    role: str | None = _extract_role(tail)
    org_name: str | None = _extract_org(tail)
    phones: list[str] = _extract_phones(tail)
    location: str | None = _extract_location(tail, display_name=display_name)
    return SignatureHints(
        current_role=role,
        org_name=org_name,
        phone_numbers=phones,
        location=location,
    )


def apply_signature_hints_to_person(
    person: object,
    hints: SignatureHints,
) -> None:
    from contactsafe_server.db.models import Person
    from contactsafe_server.services.org_enrichment import should_apply_enrichment_org

    if not isinstance(person, Person):
        return

    primary_email: str = person.email_addresses[0] if person.email_addresses else ""
    if hints.current_role and not person.current_role:
        person.current_role = hints.current_role
    if hints.org_name and should_apply_enrichment_org(
        primary_email=primary_email,
        proposed_org=hints.org_name,
    ):
        person.current_org_name = hints.org_name
    if hints.phone_numbers:
        merged_phones: list[str] = list(
            dict.fromkeys([*person.phone_numbers, *hints.phone_numbers])
        )
        person.phone_numbers = merged_phones
    if hints.location and not person.location:
        person.location = hints.location


def _extract_role(text: str) -> str | None:
    for pattern, label in _ROLE_LINE_PATTERNS:
        if re.search(pattern, text, flags=re.IGNORECASE):
            return label
    return None


def _extract_org(text: str) -> str | None:
    for pattern in _ORG_PATTERNS:
        match: re.Match[str] | None = re.search(pattern, text, flags=re.IGNORECASE | re.MULTILINE)
        if match is not None:
            org: str = match.group(1).strip().rstrip(".,")
            if org and len(org) >= 2:
                return org
    return None


def _extract_phones(text: str) -> list[str]:
    return list(dict.fromkeys(_PHONE_RE.findall(text)))


def _extract_location(text: str, *, display_name: str) -> str | None:
    lines: list[str] = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return None
    name_lower: str = display_name.lower()
    for line in reversed(lines[-8:]):
        if name_lower and name_lower in line.lower():
            continue
        if re.search(r"\b(partner|investor|founder|engineer|ceo|director|manager)\b", line, re.I):
            continue
        if _PHONE_RE.search(line):
            continue
        if re.search(r"@|https?://|www\.", line, re.I):
            continue
        if re.match(r"^[A-Z][a-z]+(?:,\s*[A-Z]{2})?$", line):
            return line
        city_state: re.Match[str] | None = re.search(
            r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?,\s*[A-Z]{2})\b",
            line,
        )
        if city_state is not None:
            return city_state.group(1)
    return None
