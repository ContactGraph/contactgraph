"""LinkedIn-style employee count ranges for org classification."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

LINKEDIN_SIZE_BAND_LABELS: Final[dict[str, str]] = {
    "1-10": "1–10 employees",
    "11-50": "11–50 employees",
    "51-200": "51–200 employees",
    "201-500": "201–500 employees",
    "501-1000": "501–1,000 employees",
    "1001-5000": "1,001–5,000 employees",
    "5001-10000": "5,001–10,000 employees",
    "10001+": "10,001+ employees",
}

LINKEDIN_SIZE_BAND_VALUES: Final[tuple[str, ...]] = tuple(LINKEDIN_SIZE_BAND_LABELS.keys())

_LINKEDIN_SIZE_BAND_RANGES: Final[tuple[tuple[int, int | None, str], ...]] = (
    (1, 10, "1-10"),
    (11, 50, "11-50"),
    (51, 200, "51-200"),
    (201, 500, "201-500"),
    (501, 1000, "501-1000"),
    (1001, 5000, "1001-5000"),
    (5001, 10000, "5001-10000"),
    (10001, None, "10001+"),
)


@dataclass(frozen=True, slots=True)
class ParsedCompanySize:
    employee_count: int | None
    company_size_band: str | None


def linkedin_size_band_label(band: str | None) -> str:
    if band is None or not band.strip():
        return "—"
    normalized: str = band.strip().lower()
    return LINKEDIN_SIZE_BAND_LABELS.get(normalized, band)


def normalize_linkedin_size_band(raw: str) -> str | None:
    value: str = raw.strip().lower().replace("–", "-").replace("—", "-")
    if not value:
        return None
    if value in LINKEDIN_SIZE_BAND_LABELS:
        return value
    alias_map: dict[str, str] = {
        "1-10 employees": "1-10",
        "11-50 employees": "11-50",
        "51-200 employees": "51-200",
        "201-500 employees": "201-500",
        "501-1000 employees": "501-1000",
        "1001-5000 employees": "1001-5000",
        "5001-10000 employees": "5001-10000",
        "10001+ employees": "10001+",
        "10000+": "10001+",
        "10001+": "10001+",
    }
    mapped: str | None = alias_map.get(value)
    if mapped is not None:
        return mapped
    return None


def headcount_to_linkedin_band(employee_count: int) -> str | None:
    if employee_count < 1:
        return None
    for minimum, maximum, band in _LINKEDIN_SIZE_BAND_RANGES:
        if maximum is None and employee_count >= minimum:
            return band
        if maximum is not None and minimum <= employee_count <= maximum:
            return band
    return "10001+"
