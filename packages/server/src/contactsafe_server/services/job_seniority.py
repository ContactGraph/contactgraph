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
_NEUTRAL_SCORE: Final[int] = 70
# Per-level penalty for under-qualification (job higher than user).
_UNDER_PENALTY: Final[int] = 22
# Per-level penalty for over-qualification (user higher than job) — milder.
_OVER_PENALTY: Final[int] = 12

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


def seniority_match_score(
    job_level: int | None,
    user_level: int | None,
) -> int:
    """Score 0-100 how well job seniority matches the user's level.

    Unknown on either side → neutral 70.
    Under-qualified (job > user) penalized more than over-qualified.
    """
    if job_level is None or user_level is None:
        return _NEUTRAL_SCORE

    delta: int = job_level - user_level
    if delta == 0:
        return 100
    if delta > 0:
        # Job is more senior than user → under-qualified.
        return max(0, min(100, 100 - _UNDER_PENALTY * delta))
    # User is more senior than job → over-qualified (milder).
    return max(0, min(100, 100 - _OVER_PENALTY * abs(delta)))


def seniority_match_reason(
    job_level: int | None,
    user_level: int | None,
    score: int,
) -> str:
    job_label: str = seniority_level_label(job_level)
    user_label: str = seniority_level_label(user_level)
    if job_level is None or user_level is None:
        return f"Seniority unknown (job={job_label}, user={user_label}); neutral score {score}."
    if job_level == user_level:
        return f"Level match: both {job_label}."
    if job_level > user_level:
        return f"Job is {job_label}; candidate is {user_label} (under-leveled)."
    return f"Job is {job_label}; candidate is {user_label} (over-leveled)."
