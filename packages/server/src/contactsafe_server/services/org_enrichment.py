"""Helpers for deciding when enrichment may override domain-derived org names."""

import re

from contactsafe_server.services.org_search import (
    is_generic_personal_domain,
    org_name_from_email,
)

_REJECTED_ORG_SLDS: frozenset[str] = frozenset(
    {
        "gmail",
        "googlemail",
        "yahoo",
        "hotmail",
        "outlook",
        "icloud",
        "me",
        "mac",
        "live",
        "protonmail",
        "fastmail",
        "aol",
        "msn",
        "ymail",
        "mail",
        "repository",
    }
)

_ORG_SUFFIX_RE: re.Pattern[str] = re.compile(
    r"\s*(?:\.(?:com|ai|io|co|vc|org|net|edu)|\s+(?:inc|llc|ltd|corp|corporation|company))\s*$",
    flags=re.IGNORECASE,
)


def domain_derived_org_name(email: str) -> str | None:
    """Org name inferred from a work email domain, if any."""
    return org_name_from_email(email)


def has_domain_derived_org(email: str) -> bool:
    """True when the email domain maps to a non-generic org name."""
    return domain_derived_org_name(email) is not None


def is_rejected_org_name(org_name: str | None) -> bool:
    """Reject consumer-provider labels and other obvious non-company names."""
    if org_name is None:
        return True
    normalized: str = normalize_org_name_for_compare(org_name)
    if not normalized or len(normalized) < 2:
        return True
    if normalized in _REJECTED_ORG_SLDS:
        return True
    return False


def normalize_org_name_for_compare(org_name: str) -> str:
    """Lowercase org label with common suffixes stripped for fuzzy compare."""
    cleaned: str = org_name.strip().lower()
    cleaned = _ORG_SUFFIX_RE.sub("", cleaned).strip()
    cleaned = re.sub(r"[^a-z0-9]+", "", cleaned)
    return cleaned


def org_names_equivalent(left: str | None, right: str | None) -> bool:
    if left is None or right is None:
        return False
    left_norm: str = normalize_org_name_for_compare(left)
    right_norm: str = normalize_org_name_for_compare(right)
    if not left_norm or not right_norm:
        return False
    return left_norm == right_norm or left_norm in right_norm or right_norm in left_norm


def should_apply_enrichment_org(*, primary_email: str, proposed_org: str | None) -> bool:
    """Only accept enrichment org names when domain inference does not apply."""
    if is_rejected_org_name(proposed_org):
        return False
    if has_domain_derived_org(primary_email):
        domain_org: str | None = domain_derived_org_name(primary_email)
        if domain_org is not None and org_names_equivalent(domain_org, proposed_org):
            return False
        return False
    _, domain = primary_email.rsplit("@", 1)
    if is_generic_personal_domain(domain):
        return True
    return proposed_org is not None
