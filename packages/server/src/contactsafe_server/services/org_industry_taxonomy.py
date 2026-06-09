"""NAICS 2-digit sector tags plus a few CRM-friendly extensions for org classification."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Final

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

_INVESTOR_CATEGORY_TAGS: Final[frozenset[str]] = frozenset(
    {"vc", "investor", "venture_capital", "naics:52"},
)

_KEYWORD_INDUSTRY_PATTERNS: Final[tuple[tuple[str, tuple[str, ...]], ...]] = (
    ("venture_capital", ("venture capital", " vc ", "private equity", "seed fund")),
    ("legal", (" law firm", "attorney", " legal ", " LLP", " L.L.P.")),
    ("nonprofit", ("nonprofit", "non-profit", "501(c)", "charitable", "foundation")),
    ("naics:62", ("hospital", "healthcare", "health care", "medical center", "clinic")),
    ("naics:51", ("software", "saas", "technology", " cloud ", " ai ")),
    ("naics:52", ("bank", "insurance", " fintech", "financial services")),
    ("naics:61", ("university", "school district", " college", "education")),
    ("naics:92", ("government", " municipal", " federal agency", " state agency")),
)


@dataclass(frozen=True, slots=True)
class StructuredCompanySummary:
    description: str | None
    industries: tuple[str, ...]


def industry_tag_label(tag: str) -> str:
    normalized: str = tag.strip().lower()
    return ORG_INDUSTRY_TAG_LABELS.get(normalized, tag)


def normalize_industry_tags(raw_tags: list[str]) -> list[str]:
    seen: set[str] = set()
    normalized: list[str] = []
    for raw in raw_tags:
        tag: str | None = _normalize_single_tag(raw)
        if tag is None or tag in seen:
            continue
        seen.add(tag)
        normalized.append(tag)
        if len(normalized) >= 3:
            break
    return normalized


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
                    "Up to 3 industry sector tags from the allowed enum. "
                    "Prefer NAICS sector codes (naics:51) and add extension tags "
                    "like nonprofit or venture_capital when they clearly apply."
                ),
                "items": {
                    "type": "string",
                    "enum": list(ORG_INDUSTRY_TAG_VALUES),
                },
                "maxItems": 3,
            },
        },
        "required": ["description", "industries"],
        "additionalProperties": False,
    }


def build_company_summary_query(company_name: str) -> str:
    return (
        f"Describe what {company_name} does and classify the company into "
        "industry sectors using only the allowed tag values."
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
    return StructuredCompanySummary(
        description=description,
        industries=tuple(normalize_industry_tags(industries)),
    )


def infer_industry_tags_from_text(*texts: str) -> list[str]:
    blob: str = f" {' '.join(texts)} ".lower()
    blob = re.sub(r"\s+", " ", blob)
    matched: list[str] = []
    for tag, patterns in _KEYWORD_INDUSTRY_PATTERNS:
        if any(pattern in blob for pattern in patterns):
            matched.append(tag)
    return normalize_industry_tags(matched)


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
