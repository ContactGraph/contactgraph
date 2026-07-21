"""Canonical funding-stage tokens for org classification."""

from __future__ import annotations

import re
from typing import Final

FUNDING_STAGE_LABELS: Final[dict[str, str]] = {
    "seed": "Seed",
    "series_a": "Series A",
    "series_b": "Series B",
    "series_c_plus": "Series C+",
    "mezzanine": "Mezzanine",
    "public": "Public",
    "mature": "Mature",
    "unknown": "Unknown",
}

FUNDING_STAGE_ORDER: Final[tuple[str, ...]] = (
    "seed",
    "series_a",
    "series_b",
    "series_c_plus",
    "mezzanine",
    "public",
    "mature",
    "unknown",
)

FUNDING_STAGE_VALUES: Final[tuple[str, ...]] = tuple(FUNDING_STAGE_LABELS.keys())

_FUNDING_STAGE_ALIASES: Final[dict[str, str]] = {
    "seed": "seed",
    "pre-seed": "seed",
    "preseed": "seed",
    "pre seed": "seed",
    "angel": "seed",
    "series a": "series_a",
    "seriesa": "series_a",
    "series-a": "series_a",
    "a": "series_a",
    "series b": "series_b",
    "seriesb": "series_b",
    "series-b": "series_b",
    "b": "series_b",
    "series c": "series_c_plus",
    "seriesc": "series_c_plus",
    "series-c": "series_c_plus",
    "series c+": "series_c_plus",
    "series c plus": "series_c_plus",
    "series_c": "series_c_plus",
    "series d": "series_c_plus",
    "series e": "series_c_plus",
    "series f": "series_c_plus",
    "growth": "series_c_plus",
    "late stage": "series_c_plus",
    "late-stage": "series_c_plus",
    "c": "series_c_plus",
    "mezzanine": "mezzanine",
    "bridge": "mezzanine",
    "pre-ipo": "mezzanine",
    "pre ipo": "mezzanine",
    "public": "public",
    "ipo": "public",
    "listed": "public",
    "publicly traded": "public",
    "public company": "public",
    "mature": "mature",
    "bootstrapped": "mature",
    "bootstrap": "mature",
    "profitable": "mature",
    "self-funded": "mature",
    "self funded": "mature",
    "non-vc": "mature",
    "non vc": "mature",
    "private equity": "mature",
    "unknown": "unknown",
    "n/a": "unknown",
    "na": "unknown",
    "none": "unknown",
    "unsure": "unknown",
}


def funding_stage_label(stage: str | None) -> str:
    if stage is None or not stage.strip():
        return "—"
    normalized: str | None = normalize_funding_stage(stage)
    if normalized is None:
        return stage.strip()
    return FUNDING_STAGE_LABELS.get(normalized, stage.strip())


def normalize_funding_stage(raw: str | None) -> str | None:
    if raw is None:
        return None
    value: str = raw.strip().lower().replace("_", " ").replace("–", "-").replace("—", "-")
    value = re.sub(r"\s+", " ", value)
    if not value:
        return None
    underscored: str = value.replace(" ", "_").replace("-", "_")
    if underscored in FUNDING_STAGE_LABELS:
        return underscored
    mapped: str | None = _FUNDING_STAGE_ALIASES.get(value)
    if mapped is not None:
        return mapped
    mapped = _FUNDING_STAGE_ALIASES.get(underscored.replace("_", " "))
    if mapped is not None:
        return mapped
    # Compact forms like "seriesA" / "seriesC+"
    compact: str = re.sub(r"[^a-z0-9+]", "", value)
    compact_aliases: dict[str, str] = {
        "seed": "seed",
        "preseed": "seed",
        "seriesa": "series_a",
        "seriesb": "series_b",
        "seriesc": "series_c_plus",
        "seriescplus": "series_c_plus",
        "seriesc+": "series_c_plus",
        "seriesd": "series_c_plus",
        "ipo": "public",
        "public": "public",
        "mezzanine": "mezzanine",
        "mature": "mature",
        "bootstrapped": "mature",
        "unknown": "unknown",
    }
    return compact_aliases.get(compact)
