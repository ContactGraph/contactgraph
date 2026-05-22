"""Heuristic category tags from email metadata (no LLM required)."""

import re


def infer_categories_from_contact(
    *,
    email: str,
    display_name: str,
    org_name: str | None,
    pitch_outbound_count: int = 0,
) -> list[str]:
    """Return lowercase category tags such as ``vc``, ``founder``."""
    domain: str = email.rsplit("@", 1)[-1].lower() if "@" in email else ""
    blob: str = f"{display_name} {org_name or ''} {domain}".lower()
    categories: list[str] = []

    if pitch_outbound_count > 0 or _looks_like_vc(blob, domain):
        categories.append("vc")

    if re.search(r"\bfounder\b|\bco-founder\b", blob):
        categories.append("founder")
    if re.search(r"\bengineer\b|\bdeveloper\b|\bsoftware\b", blob):
        categories.append("engineer")
    if re.search(r"\bsales\b|\baccount executive\b", blob):
        categories.append("sales")

    return _dedupe_lower(categories)


def _looks_like_vc(blob: str, domain: str) -> bool:
    if ".vc" in domain or domain.endswith(".vc"):
        return True
    vc_domain_markers: tuple[str, ...] = (
        "ventures",
        "venture",
        "capital",
        "partners",
        "vcfund",
        "seedfund",
    )
    if any(marker in domain for marker in vc_domain_markers):
        return True
    if re.search(r"\b(vc|venture capital|general partner|managing partner)\b", blob):
        return True
    if "investor" in blob and "newsletter" not in blob:
        return True
    return False


def _dedupe_lower(values: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        key = value.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(key)
    return out
