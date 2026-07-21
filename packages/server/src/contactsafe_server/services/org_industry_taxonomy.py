"""NAICS 2-digit sector tags plus a few CRM-friendly extensions for org classification."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Final

from contactsafe_server.services.org_company_size import (
    LINKEDIN_SIZE_BAND_VALUES,
    normalize_linkedin_size_band,
)
from contactsafe_server.services.org_funding_stage import (
    FUNDING_STAGE_VALUES,
    normalize_funding_stage,
)

# NAICS 2022 sector codes (2-digit) stored as naics:{code}.
# Friendly labels are for UI display only.
NAICS_SECTOR_LABELS: Final[dict[str, str]] = {
    "naics:11": "Agriculture",
    "naics:21": "Mining & Energy",
    "naics:22": "Utilities",
    "naics:23": "Construction",
    "naics:31": "Manufacturing",
    "naics:42": "Wholesale",
    "naics:44": "Retail",
    "naics:48": "Transportation",
    "naics:51": "Technology & Media",
    "naics:52": "Financial Services",
    "naics:53": "Real Estate",
    "naics:54": "Professional Services",
    "naics:55": "Holding Companies",
    "naics:56": "Business Services",
    "naics:61": "Education",
    "naics:62": "Healthcare",
    "naics:71": "Arts & Entertainment",
    "naics:72": "Hospitality",
    "naics:81": "Other Services",
    "naics:92": "Government",
}

# Extensions not represented cleanly as NAICS top-level sectors.
EXTENSION_INDUSTRY_LABELS: Final[dict[str, str]] = {
    "nonprofit": "Nonprofit",
    "venture_capital": "Venture Capital",
    "legal": "Legal",
}

ORG_INDUSTRY_TAG_LABELS: Final[dict[str, str]] = {
    **NAICS_SECTOR_LABELS,
    **EXTENSION_INDUSTRY_LABELS,
}

ORG_INDUSTRY_TAG_VALUES: Final[tuple[str, ...]] = tuple(ORG_INDUSTRY_TAG_LABELS.keys())

MAX_ORG_INDUSTRY_TAGS: Final[int] = 1

_EXTENSION_INDUSTRY_TAGS: Final[frozenset[str]] = frozenset(EXTENSION_INDUSTRY_LABELS.keys())

_INVESTOR_CATEGORY_TAGS: Final[frozenset[str]] = frozenset(
    {"vc", "investor", "venture_capital", "naics:52"},
)

_KEYWORD_INDUSTRY_PATTERNS: Final[tuple[tuple[str, tuple[str, ...]], ...]] = (
    ("venture_capital", ("venture capital", " vc ", "private equity", "seed fund")),
    ("legal", (" law firm", "attorneys at law", "attorney", " llp", " l.l.p.")),
    (
        "nonprofit",
        (
            "nonprofit",
            "non-profit",
            "not-for-profit",
            "501(c)(3)",
            "501(c)",
            "charitable organization",
        ),
    ),
    ("naics:62", ("hospital", "healthcare", "health care", "medical center", "clinic")),
    ("naics:51", ("software", "saas", "technology company", " cloud ", " ai platform")),
    ("naics:52", ("bank", "insurance", " fintech", "financial services")),
    ("naics:61", ("university", "school district", " college", "education")),
    ("naics:92", ("government agency", " municipal", " federal agency", " state agency")),
)


@dataclass(frozen=True, slots=True)
class StructuredCompanySummary:
    description: str | None
    industries: tuple[str, ...]
    company_size_band: str | None = None
    funding_stage: str | None = None


def industry_tag_label(tag: str) -> str:
    normalized: str = tag.strip().lower()
    return ORG_INDUSTRY_TAG_LABELS.get(normalized, tag)


def normalize_industry_tags(
    raw_tags: list[str],
    *,
    max_tags: int = MAX_ORG_INDUSTRY_TAGS,
) -> list[str]:
    seen: set[str] = set()
    normalized: list[str] = []
    for raw in raw_tags:
        tag: str | None = _normalize_single_tag(raw)
        if tag is None or tag in seen:
            continue
        seen.add(tag)
        normalized.append(tag)
        if len(normalized) >= max_tags:
            break
    return normalized


def select_primary_industry_tag(raw_tags: list[str]) -> list[str]:
    """Return zero or one tag, preferring NAICS sectors over extension tags."""
    candidates: list[str] = normalize_industry_tags(raw_tags, max_tags=10)
    if not candidates:
        return []

    naics_tags: list[str] = [tag for tag in candidates if tag.startswith("naics:")]
    if naics_tags:
        return [naics_tags[0]]

    return [candidates[0]]


def is_investor_industry_tag(tag: str) -> bool:
    return tag.strip().lower() in _INVESTOR_CATEGORY_TAGS


def exa_company_summary_schema() -> dict[str, object]:
    return {
        "type": "object",
        "properties": {
            "description": {
                "type": "string",
                "description": (
                    "One or two sentences describing what the company does, "
                    "its product, or its business model."
                ),
            },
            "industries": {
                "type": "array",
                "description": (
                    "Exactly one primary industry sector tag from the allowed enum. "
                    "Use NAICS sector codes (naics:51) for most for-profit companies. "
                    "Use nonprofit only for registered nonprofits—not for companies that "
                    "donate, have a foundation, or use a .org domain."
                ),
                "items": {
                    "type": "string",
                    "enum": list(ORG_INDUSTRY_TAG_VALUES),
                },
                "minItems": 1,
                "maxItems": 1,
            },
            "company_size_band": {
                "type": "string",
                "description": (
                    "LinkedIn-style employee count range based on estimated headcount."
                ),
                "enum": list(LINKEDIN_SIZE_BAND_VALUES),
            },
            "funding_stage": {
                "type": "string",
                "description": (
                    "Best-effort funding stage. Use public for publicly traded companies, "
                    "mature for profitable/bootstrapped/non-VC private firms, and unknown "
                    "when unsure."
                ),
                "enum": list(FUNDING_STAGE_VALUES),
            },
        },
        "required": ["description", "industries"],
        "additionalProperties": False,
    }


def build_company_summary_query(company_name: str) -> str:
    return (
        f"Describe what {company_name} does, choose exactly one primary industry "
        "sector tag, estimate its LinkedIn employee count range if possible, and "
        "estimate its funding stage (seed, series_a, series_b, series_c_plus, "
        "mezzanine, public, mature, or unknown). Use public if it is publicly traded, "
        "mature for profitable/bootstrapped/non-VC private firms, and unknown when unsure. "
        "For for-profit companies, return a NAICS sector such as naics:51. "
        "Only use nonprofit for registered nonprofits."
    )


def parse_structured_company_summary(raw: str) -> StructuredCompanySummary | None:
    text: str = raw.strip()
    if not text.startswith("{"):
        return None
    try:
        payload: object = json.loads(text)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    data: dict[str, object] = payload

    description: str | None = None
    description_raw: object = data.get("description")
    if isinstance(description_raw, str) and description_raw.strip():
        description = description_raw.strip()

    industries_raw: object = data.get("industries")
    industries: list[str] = []
    if isinstance(industries_raw, list):
        for item in industries_raw:
            if isinstance(item, str):
                industries.append(item)

    company_size_band: str | None = None
    size_band_raw: object = data.get("company_size_band")
    if isinstance(size_band_raw, str):
        company_size_band = normalize_linkedin_size_band(size_band_raw)

    funding_stage: str | None = None
    funding_stage_raw: object = data.get("funding_stage")
    if isinstance(funding_stage_raw, str):
        funding_stage = normalize_funding_stage(funding_stage_raw)

    return StructuredCompanySummary(
        description=description,
        industries=tuple(select_primary_industry_tag(industries)),
        company_size_band=company_size_band,
        funding_stage=funding_stage,
    )


def infer_industry_tags_from_text(*texts: str) -> list[str]:
    blob: str = f" {' '.join(texts)} ".lower()
    blob = re.sub(r"\s+", " ", blob)
    matched: list[str] = []
    for tag, patterns in _KEYWORD_INDUSTRY_PATTERNS:
        if any(pattern in blob for pattern in patterns):
            matched.append(tag)
    return select_primary_industry_tag(matched)


def _normalize_single_tag(raw: str) -> str | None:
    value: str = raw.strip().lower()
    if not value:
        return None
    if value in ORG_INDUSTRY_TAG_LABELS:
        return value
    if value.isdigit() and len(value) == 2:
        candidate: str = f"naics:{value}"
        if candidate in ORG_INDUSTRY_TAG_LABELS:
            return candidate
    if value.startswith("naics:"):
        suffix: str = value.removeprefix("naics:")
        if suffix.isdigit() and len(suffix) == 2:
            candidate = f"naics:{suffix}"
            if candidate in ORG_INDUSTRY_TAG_LABELS:
                return candidate
    alias_map: dict[str, str] = {
        "technology": "naics:51",
        "tech": "naics:51",
        "software": "naics:51",
        "healthcare": "naics:62",
        "health care": "naics:62",
        "finance": "naics:52",
        "financial services": "naics:52",
        "retail": "naics:44",
        "government": "naics:92",
        "education": "naics:61",
        "vc": "venture_capital",
        "investor": "venture_capital",
    }
    mapped: str | None = alias_map.get(value)
    if mapped is not None:
        return mapped
    return None
