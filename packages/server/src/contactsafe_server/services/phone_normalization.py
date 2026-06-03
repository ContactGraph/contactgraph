"""Normalize phone numbers for alias lookup and deduplication."""

from __future__ import annotations

import re

_DIGITS_ONLY_RE: re.Pattern[str] = re.compile(r"\D+")


def normalize_phone(value: str, *, default_country_code: str = "1") -> str:
    """Return an E.164-style phone string for matching (e.g. ``+14157132682``)."""
    stripped: str = value.strip()
    digits: str = _DIGITS_ONLY_RE.sub("", stripped)
    if not digits:
        return stripped

    country_code: str = default_country_code.lstrip("+")
    if stripped.startswith("+"):
        return f"+{digits}"
    if len(digits) == 10:
        return f"+{country_code}{digits}"
    if len(digits) == 11 and digits.startswith(country_code):
        return f"+{digits}"
    return f"+{digits}" if not stripped.startswith("+") else stripped
