"""Deterministic seniority-level classification for jobs and user profiles."""

from __future__ import annotations

import re
from typing import Final

# Ordinal ladder: higher = more senior.
SENIORITY_INTERN: Final[int] = 0
SENIORITY_ENTRY: Final[int] = 1
SENIORITY_ASSOCIATE: Final[int] = 2
SENIORITY_MID: Final[int] = 3
SENIORITY_SENIOR: Final[int] = 4
SENIORITY_STAFF: Final[int] = 5
SENIORITY_MANAGER: Final[int] = 6
SENIORITY_DIRECTOR: Final[int] = 7
SENIORITY_VP: Final[int] = 8
SENIORITY_CLEVEL: Final[int] = 9

SENIORITY_LEVEL_LABELS: Final[dict[int, str]] = {
    SENIORITY_INTERN: "Intern",
    SENIORITY_ENTRY: "Entry",
    SENIORITY_ASSOCIATE: "Associate",
    SENIORITY_MID: "Mid",
    SENIORITY_SENIOR: "Senior",
    SENIORITY_STAFF: "Staff / Principal",
    SENIORITY_MANAGER: "Manager",
    SENIORITY_DIRECTOR: "Director",
    SENIORITY_VP: "VP",
    SENIORITY_CLEVEL: "C-level",
}

# Neutral score when either side is unknown.
_NEUTRAL_SCORE: Final[int] = 85
# Per-level penalty for a job BELOW the target range. Steep: under-leveled
# postings are the dominant source of feed noise, and "Product Manager" two
# rungs below a Staff target is a different job, not a near miss.
_BELOW_TARGET_PENALTY: Final[int] = 45
# Per-level penalty for a job ABOVE the target range. Mild: a stretch role is
# usually still worth seeing.
_ABOVE_TARGET_PENALTY: Final[int] = 18

# Ordered highest-first so more specific senior titles win.
_LEVEL_PATTERNS: Final[tuple[tuple[int, re.Pattern[str]], ...]] = (
    (
        SENIORITY_CLEVEL,
        re.compile(
            r"\b("
            r"ceo|cto|cfo|coo|cpo|cmo|cio|ciso|chief\s+\w+|"
            r"founder|co-?founder|owner"
            r")\b",
            re.IGNORECASE,
        ),
    ),
    (
        SENIORITY_VP,
        re.compile(
            r"\b("
            r"evp|svp|avp|vp\b|v\.p\.|"
            r"vice[\s-]?president|"
            r"head\s+of\b"
            r")",
            re.IGNORECASE,
        ),
    ),
    (
        SENIORITY_DIRECTOR,
        re.compile(
            r"\b("
            r"director|dir\b|"
            r"general\s+manager|\bgm\b"
            r")\b",
            re.IGNORECASE,
        ),
    ),
    (
        SENIORITY_MANAGER,
        re.compile(
            r"\b("
            r"manager|mgr\b|"
            r"people\s+manager|engineering\s+manager|"
            r"product\s+manager\b(?!.*\b(senior|staff|principal|group|director)\b)"
            r")\b",
            re.IGNORECASE,
        ),
    ),
    (
        SENIORITY_STAFF,
        re.compile(
            r"\b("
            r"staff|principal|distinguished|fellow|"
            r"architect\b|group\s+(?:product\s+)?(?:manager|pm)\b"
            r")\b",
            re.IGNORECASE,
        ),
    ),
    (
        SENIORITY_SENIOR,
        re.compile(
            r"\b("
            r"senior|sr\.?\b|lead\b|"
            r"ii{2,}|iii\b|iv\b"
            r")\b",
            re.IGNORECASE,
        ),
    ),
    (
        SENIORITY_ASSOCIATE,
        re.compile(
            r"\b("
            r"associate|asst\.?\b|assistant\b"
            r")\b",
            re.IGNORECASE,
        ),
    ),
    (
        SENIORITY_ENTRY,
        re.compile(
            r"\b("
            r"junior|jr\.?\b|entry[\s-]?level|graduate|new\s+grad|"
            r"apprentice"
            r")\b",
            re.IGNORECASE,
        ),
    ),
    (
        SENIORITY_INTERN,
        re.compile(
            r"\b("
            r"intern(?:ship)?|co-?op\b|trainee"
            r")\b",
            re.IGNORECASE,
        ),
    ),
)

# Titles that look like "Manager" but are IC tracks (e.g. Product Manager).
# When these match WITHOUT a leadership modifier, treat as mid/senior IC.
_IC_MANAGER_TITLES: Final[re.Pattern[str]] = re.compile(
    r"\b("
    r"(?:associate|senior|staff|principal|group)?\s*"
    r"(?:product|program|project|account|customer\s+success|community|"
    r"marketing|brand|growth|partnership|partner|channel|"
    r"technical\s+program|tpm)\s+manager"
    r"|product\s+marketing\s+manager"
    r")\b",
    re.IGNORECASE,
)

_IC_MANAGER_LEVEL_OVERRIDES: Final[tuple[tuple[re.Pattern[str], int], ...]] = (
    (re.compile(r"\b(group|principal|staff)\b", re.IGNORECASE), SENIORITY_STAFF),
    (re.compile(r"\b(senior|sr\.?|lead)\b", re.IGNORECASE), SENIORITY_SENIOR),
    (re.compile(r"\b(associate|junior|jr\.?|assistant)\b", re.IGNORECASE), SENIORITY_ASSOCIATE),
)


def classify_seniority_level(
    title: str | None,
    description_snippet: str | None = None,
) -> int | None:
    """Map a job/role title to a seniority ordinal, or None if unknown."""
    text: str = " ".join(
        part.strip()
        for part in (title or "", description_snippet or "")
        if part and part.strip()
    ).strip()
    if not text:
        return None

    # IC-track "… Manager" titles (Product Manager, Account Manager, etc.)
    # should not be treated as people-managers unless leadership words appear.
    if _IC_MANAGER_TITLES.search(text):
        leadership: re.Pattern[str] = re.compile(
            r"\b(director|vp\b|vice[\s-]?president|head\s+of|chief)\b",
            re.IGNORECASE,
        )
        if not leadership.search(text):
            for pattern, level in _IC_MANAGER_LEVEL_OVERRIDES:
                if pattern.search(text):
                    return level
            return SENIORITY_MID

    for level, pattern in _LEVEL_PATTERNS:
        if pattern.search(text):
            # "Engineering Manager" etc. are true managers — already handled
            # by SENIORITY_MANAGER pattern after IC override above.
            return level

    return None


def seniority_level_label(level: int | None) -> str:
    if level is None:
        return "Unknown"
    return SENIORITY_LEVEL_LABELS.get(level, "Unknown")


# Fragment separators for parsing a target range out of free text, e.g.
# "Staff / Principal Product Manager" or "Senior to Staff PM".
_FRAGMENT_SPLIT_RE: Final[re.Pattern[str]] = re.compile(
    r"\s*(?:[/,;|]|\bor\b|\bto\b|\band\b|\n)\s*",
    re.IGNORECASE,
)


def extract_target_seniority_range(text: str | None) -> tuple[int, int] | None:
    """Parse a target seniority range out of free-text preferences.

    Splits on separators so each fragment classifies independently — "Staff /
    Principal Product Manager" yields two Staff readings rather than one
    confused one. Returns (min, max) over everything recognized, or None.
    """
    if not text or not text.strip():
        return None

    levels: list[int] = []
    for fragment in _FRAGMENT_SPLIT_RE.split(text):
        cleaned: str = fragment.strip()
        if not cleaned:
            continue
        level: int | None = classify_seniority_level(cleaned)
        if level is not None:
            levels.append(level)

    if not levels:
        return None
    return min(levels), max(levels)


def seniority_range_score(
    job_level: int | None,
    target_min: int | None,
    target_max: int | None,
) -> int:
    """Score 0-100 how well a job's level sits against the target range.

    Unknown on either side → neutral. Inside the range → 100. Below the range
    is penalized steeply; above it only mildly, since a stretch role is still
    worth surfacing while an under-leveled one is not.
    """
    if job_level is None or target_min is None or target_max is None:
        return _NEUTRAL_SCORE

    low: int = min(target_min, target_max)
    high: int = max(target_min, target_max)

    if low <= job_level <= high:
        return 100
    if job_level < low:
        return max(0, min(100, 100 - _BELOW_TARGET_PENALTY * (low - job_level)))
    return max(0, min(100, 100 - _ABOVE_TARGET_PENALTY * (job_level - high)))


def seniority_range_label(target_min: int | None, target_max: int | None) -> str:
    if target_min is None or target_max is None:
        return "Unknown"
    low: int = min(target_min, target_max)
    high: int = max(target_min, target_max)
    if low == high:
        return seniority_level_label(low)
    return f"{seniority_level_label(low)}–{seniority_level_label(high)}"


def seniority_range_reason(
    job_level: int | None,
    target_min: int | None,
    target_max: int | None,
    score: int,
) -> str:
    job_label: str = seniority_level_label(job_level)
    target_label: str = seniority_range_label(target_min, target_max)
    if job_level is None or target_min is None or target_max is None:
        return (
            f"Seniority unknown (job={job_label}, target={target_label}); "
            f"neutral score {score}."
        )
    low: int = min(target_min, target_max)
    high: int = max(target_min, target_max)
    if low <= job_level <= high:
        return f"Job is {job_label}, within the {target_label} target."
    if job_level < low:
        return f"Job is {job_label}, below the {target_label} target (under-leveled)."
    return f"Job is {job_label}, above the {target_label} target (stretch)."
