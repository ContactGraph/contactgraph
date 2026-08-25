"""LLM-based job relevance scoring service."""

from __future__ import annotations

import logging
import re
import uuid
from datetime import UTC, datetime
from typing import Any, cast

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from contactsafe_server.config import Settings
from contactsafe_server.db.models import (
    EmploymentClaim,
    Org,
    OrgJob,
    Person,
    PersonAttributeClaim,
    User,
    UserJobRelevance,
)
from contactsafe_server.events import (
    ScoringCancelledEvent,
    ScoringCompleteEvent,
    ScoringProgressEvent,
    job_event_bus,
)
from contactsafe_server.services.openai_json import (
    content_from_chat_completion,
    parse_json_object,
)
from contactsafe_server.services.job_geocode import (
    geocode_location,
    location_match_reason,
    location_match_score,
)
from contactsafe_server.services.job_seniority import (
    classify_seniority_level,
    extract_target_seniority_range,
    seniority_range_reason,
    seniority_range_score,
)

logger: logging.Logger = logging.getLogger(__name__)

_BATCH_SIZE: int = 15
_MATCH_SCORE_RELEVANT_THRESHOLD: int = 35

SCORING_WEIGHT_KEYS: tuple[str, ...] = (
    "role",
    "qualification",
    "seniority",
    "location",
    "funding_stage",
)

DEFAULT_SCORING_WEIGHTS: dict[str, float] = {
    "role": 1.0,
    "qualification": 0.9,
    # Seniority is scored mechanically against an explicit target range, so it
    # is reliable enough to carry real weight. At 0.6 an under-leveled posting
    # could lose its whole seniority score and still clear the relevance bar.
    "seniority": 0.85,
    "location": 0.9,
    "funding_stage": 0.7,
}

_DIMENSION_LABELS: dict[str, str] = {
    "role": "role",
    "qualification": "qualification",
    "seniority": "seniority",
    "location": "location",
    "funding_stage": "funding stage",
}

_SYSTEM_PROMPT: str = """\
You are a strict job-match scoring engine. You will receive the candidate's professional \
profile and a batch of job postings. Evaluate each job on TWO separate dimensions. \
Seniority and location are scored separately by a non-LLM system — do NOT score them.

{preferences}

{profile}

For each job, provide two independent sub-scores (each 0-100):

1. **role_score** (job function alignment): Is this job in the SAME job function the \
candidate is targeting? This is a categorical match, not a similarity judgment.

HOW TO DETERMINE JOB FUNCTION (follow in order):
1. Read the job TITLE, department, AND description snippet together — titles alone \
are often ambiguous or misleading. Prefer the function implied by responsibilities \
and requirements over keyword matches in the title.
2. Use department only as a tiebreaker; department names are often misleading \
(e.g. "Product Success Engineering" is an engineering org, NOT product management).
3. Shared keywords (AI, cloud, platform, product) do NOT change the function.

Job functions are distinct career tracks:
- Engineering: software/hardware/release/QA/DevOps/SRE/ML/data engineering, \
"Director of Software Engineering", "Solutions Engineer", "Product Success Engineering"
- Product Management: "Product Manager", "Group PM", "Director of Product", "Head of Product"
- Product Design: "Product Designer", "UX Designer", "UI Designer", "Design Lead" — NOT product management
- Product Analytics / Data Analysis: "Product Analyst", "Data Analyst", "Business Analyst", \
"Analytics Manager" — NOT product management
- Product Marketing / Marketing: "Product Marketing Manager", "Product Marketer" — NOT product management
- Program / Project Management, Sales, Customer Success, Legal / Paralegal, etc.

COMMON MISTAKES TO AVOID:
- "Director of Software Engineering" → Engineering, even if dept says "Product Success Engineering"
- "Product Success Engineering" or "Solutions Engineering" → Engineering, NOT product management
- "Product Designer" or "UX Designer" → Product Design, NOT product management
- "Product Analyst" or "Data Analyst" → Product Analytics, NOT product management
- "Product Marketing Manager" → Marketing, NOT product management
- Candidate interest in AI/domain does NOT make an engineering role into product management

SCORING RULES for role_score:
- Same function as requested → 85-100 (e.g. "Product Manager" for a PM candidate)
- Very close variant within function → 65-84 (e.g. "Group PM" or "Product Lead")
- Adjacent with some overlap → 30-50 (e.g. "Technical Program Manager" for a PM candidate)
- Different function → 0-25 (ANY engineering, design, analytics, marketing, or legal title for a PM candidate)

Do NOT boost role_score because of shared domain, industry, or buzzwords. A mismatched \
title CAN still score high if the description/requirements clearly describe the target \
function (e.g. "Growth Lead" whose JD is product management).

2. **qualification_score**: Given the candidate's REAL experience, skills, and seniority \
in the profile, how realistic a fit are they for this job's stated requirements?
- Strong match to required skills/experience → 80-100
- Partial match; stretch but plausible → 50-79
- Clearly under-qualified (missing core skills/years) → 0-35
- Clearly over-qualified (mild penalty only) → 55-75
Base this on the job description requirements and the candidate profile, NOT on whether \
the title matches. A paralegal role for an experienced PM should score near 0 on \
qualification because the required skills do not overlap — but do NOT lower this score \
just because the function differs when the skills themselves transfer.

For each sub-score, provide a brief reason (1 sentence) explaining the score.

Respond with a JSON object containing a "results" array. Each element must have:
- "index": the 0-based index of the job in the input list
- "role_score": integer 0-100
- "role_reason": string (1 sentence)
- "qualification_score": integer 0-100
- "qualification_reason": string (1 sentence)

Example:
{{"results": [
  {{"index": 0, "role_score": 12, "role_reason": "Director of Software Engineering is an engineering leadership role, not product management.", "qualification_score": 70, "qualification_reason": "Strong leadership and platform experience would transfer, but core PM craft skills are not required."}},
  {{"index": 1, "role_score": 92, "role_reason": "Principal Product Manager matches the candidate's product management target.", "qualification_score": 88, "qualification_reason": "Background in B2B platform PM aligns with the JD requirements."}}
]}}
"""

_JOB_TEMPLATE: str = (
    "#{index}: title={title} | dept={department} | location={location} | "
    "remote={remote} | snippet={snippet}"
)

_PM_PREFERENCE_RE: re.Pattern[str] = re.compile(
    r"\b("
    r"product manager|product management|pm|"
    r"head of product|product lead(?:ership)?|"
    r"director[, ]+(?:of )?product|vp[, ]+(?:of )?product|"
    r"chief product officer|cpo"
    r")\b",
    re.IGNORECASE,
)
_PM_TITLE_RE: re.Pattern[str] = re.compile(
    r"\b("
    r"product manager|product management|group product manager|"
    r"principal product manager|senior product manager|associate product manager|"
    r"product lead|"
    # "Head of Product" is a PM title; "Head of Product Design" is not, so the
    # leadership forms must not swallow a trailing vertical.
    r"(?:director[, ]+(?:of )?|head of |vp[, ]+(?:of )?)product"
    r"(?!\s+(?:operations|ops|design|marketing|analytics|engineering|success))"
    r")\b",
    re.IGNORECASE,
)
_ENGINEERING_TITLE_RE: re.Pattern[str] = re.compile(
    r"\b("
    r"software engineer(?:ing)?|(?:^|[\W_])engineer(?:ing)?|developer|devops|sre|"
    r"architect|release engineer|qa engineer|hardware engineer|"
    r"ml engineer|machine learning engineer|data engineer|"
    r"technical marketing engineer|solutions engineer|sales engineer|"
    r"product success engineer(?:ing)?|field engineer|systems engineer|"
    r"director[, ]+(?:of )?(?:software )?engineer"
    r")\b",
    re.IGNORECASE,
)
_MARKETING_TITLE_RE: re.Pattern[str] = re.compile(
    r"\b("
    r"marketing|product marketer|brand\b|demand gen(?:eration)?|"
    r"growth marketer|content strategist|communications"
    r")\b",
    re.IGNORECASE,
)
# Broad on purpose: "Product Design Manager", "Senior Designer" and
# "UX Researcher" are all design-track roles that the old product-designer-only
# pattern let through. Genuine PM titles short-circuit before this runs.
_DESIGN_TITLE_RE: re.Pattern[str] = re.compile(
    r"\b("
    r"designer|product design|content design|design system|"
    r"ux\b|ui\b|user experience|interaction design|visual design|"
    r"design lead|design manager|design director|director[, ]+(?:of )?design|"
    r"head of design|vp[, ]+(?:of )?design|"
    r"ux research(?:er)?|user research(?:er)?|design research(?:er)?"
    r")\b",
    re.IGNORECASE,
)
_ANALYST_TITLE_RE: re.Pattern[str] = re.compile(
    r"\b("
    r"analyst|analytics|data scientist|research scientist|"
    r"business intelligence|\bbi\b"
    r")\b",
    re.IGNORECASE,
)
# Program/project management is the classic "product-adjacent" near miss.
_PROGRAM_TITLE_RE: re.Pattern[str] = re.compile(
    r"\b("
    r"program manager|project manager|programme manager|"
    r"technical program manager|\btpm\b|scrum master|"
    r"chief of staff|business operations|\bbizops\b|"
    r"product operations|product ops"
    r")\b",
    re.IGNORECASE,
)
_LEGAL_TITLE_RE: re.Pattern[str] = re.compile(
    r"\b(paralegal|attorney|lawyer|legal counsel|legal assistant)\b",
    re.IGNORECASE,
)


_scoring_cancelled: set[uuid.UUID] = set()
_scoring_progress: dict[uuid.UUID, tuple[int, int]] = {}


def _use_redis_state() -> bool:
    from contactsafe_server.config import get_settings

    return get_settings().use_arq_worker


def cancel_scoring(user_id: uuid.UUID) -> None:
    """Signal the scoring loop to stop for this user."""
    _scoring_cancelled.add(user_id)
    if _use_redis_state():
        import asyncio

        from contactsafe_server.redis_state import set_scoring_cancelled

        try:
            loop: asyncio.AbstractEventLoop = asyncio.get_running_loop()
            loop.create_task(set_scoring_cancelled(user_id))
        except RuntimeError:
            pass


def get_scoring_progress(user_id: uuid.UUID) -> tuple[int, int] | None:
    if _use_redis_state():
        import asyncio

        from contactsafe_server.redis_state import get_scoring_progress_redis

        try:
            loop: asyncio.AbstractEventLoop = asyncio.get_running_loop()
            if loop.is_running():
                future = asyncio.ensure_future(get_scoring_progress_redis(user_id))
                if future.done():
                    return future.result()
        except RuntimeError:
            pass
    return _scoring_progress.get(user_id)


async def get_scoring_progress_async(user_id: uuid.UUID) -> tuple[int, int] | None:
    if _use_redis_state():
        from contactsafe_server.redis_state import get_scoring_progress_redis

        return await get_scoring_progress_redis(user_id)
    return _scoring_progress.get(user_id)


async def _is_scoring_cancelled(user_id: uuid.UUID) -> bool:
    if _use_redis_state():
        from contactsafe_server.redis_state import is_scoring_cancelled_redis

        if await is_scoring_cancelled_redis(user_id):
            return True
    return user_id in _scoring_cancelled


async def _set_progress(user_id: uuid.UUID, scored: int, total: int) -> None:
    _scoring_progress[user_id] = (scored, total)
    if _use_redis_state():
        from contactsafe_server.redis_state import set_scoring_progress

        await set_scoring_progress(user_id, scored, total)


async def _clear_progress(user_id: uuid.UUID) -> None:
    _scoring_progress.pop(user_id, None)
    if _use_redis_state():
        from contactsafe_server.redis_state import clear_scoring_progress

        await clear_scoring_progress(user_id)
        from contactsafe_server.redis_state import clear_scoring_cancelled

        await clear_scoring_cancelled(user_id)


def _publish_scoring_progress(user_id: uuid.UUID, scored: int, total: int) -> None:
    event: ScoringProgressEvent = {
        "type": "scoring_progress",
        "scored": scored,
        "total": total,
    }
    job_event_bus.publish(user_id, event)


def _publish_scoring_complete(user_id: uuid.UUID, scored: int, total: int) -> None:
    event: ScoringCompleteEvent = {
        "type": "scoring_complete",
        "scored": scored,
        "total": total,
    }
    job_event_bus.publish(user_id, event)


def _publish_scoring_cancelled(user_id: uuid.UUID, scored: int, total: int) -> None:
    event: ScoringCancelledEvent = {
        "type": "scoring_cancelled",
        "scored": scored,
        "total": total,
    }
    job_event_bus.publish(user_id, event)


# (pattern, cap, label) — checked in order against title + department.
_MISMATCH_FUNCTIONS: tuple[tuple[re.Pattern[str], int, str], ...] = (
    (_ENGINEERING_TITLE_RE, 15, "engineering"),
    (_DESIGN_TITLE_RE, 15, "product design"),
    (_LEGAL_TITLE_RE, 10, "a legal role"),
    (_MARKETING_TITLE_RE, 20, "marketing"),
    (_ANALYST_TITLE_RE, 20, "analytics"),
    (_PROGRAM_TITLE_RE, 25, "program/project management"),
)


def _cap_role_score_for_function_mismatch(
    preferences_text: str | None,
    job: OrgJob,
    role_score: int,
    role_reason: str | None,
) -> tuple[int, str | None]:
    """Cap inflated role scores when the title clearly mismatches PM preferences."""
    if preferences_text is None or not _PM_PREFERENCE_RE.search(preferences_text):
        return role_score, role_reason

    title: str = job.title
    if _PM_TITLE_RE.search(title):
        return role_score, role_reason

    haystack: str = f"{title} {job.department or ''}"
    for pattern, cap, label in _MISMATCH_FUNCTIONS:
        # Never cap a vertical the candidate is themselves targeting — someone
        # who asked for "Head of Product Design" matches the PM preference
        # pattern but is not asking us to bury design roles.
        if pattern.search(preferences_text):
            continue
        if not pattern.search(haystack):
            continue
        capped: int = min(role_score, cap)
        if capped < role_score:
            return capped, f"The job title indicates {label}, not product management."
    return role_score, role_reason


def resolve_scoring_weights(raw: dict[str, object] | None) -> dict[str, float]:
    """Merge stored weights over defaults and clamp each to [0, 1]."""
    resolved: dict[str, float] = dict(DEFAULT_SCORING_WEIGHTS)
    if raw is None:
        return resolved
    for key in SCORING_WEIGHT_KEYS:
        value: object | None = raw.get(key)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            resolved[key] = max(0.0, min(1.0, float(value)))
    return resolved


def _dimension_factor(score_0_100: int, weight: float) -> float:
    s: float = max(0.0, min(1.0, score_0_100 / 100.0))
    w: float = max(0.0, min(1.0, weight))
    return 1.0 - w * (1.0 - s)


def stage_match_factor(
    *,
    org_funding_stage: str | None,
    preferred_funding_stages: list[str] | None,
    weight: float,
) -> float:
    """Return the funding-stage knock-out factor (1.0 = neutral)."""
    if not preferred_funding_stages:
        return 1.0
    if org_funding_stage is None or org_funding_stage == "unknown":
        return 1.0
    s_stage: float = 1.0 if org_funding_stage in preferred_funding_stages else 0.0
    return _dimension_factor(int(round(s_stage * 100)), weight)


def compute_match_score(
    *,
    role_score: int,
    qualification_score: int,
    seniority_score: int,
    location_score: int,
    weights: dict[str, float],
    stage_factor: float,
) -> tuple[int, str | None]:
    """Conjunctive noisy-AND match score.

    match = 100 · Π_i (1 − wᵢ·(1 − sᵢ))

    Returns (match_score, limiting_factor_note).
    """
    factors: dict[str, float] = {
        "role": _dimension_factor(role_score, weights.get("role", 1.0)),
        "qualification": _dimension_factor(
            qualification_score,
            weights.get("qualification", 0.9),
        ),
        "seniority": _dimension_factor(seniority_score, weights.get("seniority", 0.6)),
        "location": _dimension_factor(location_score, weights.get("location", 0.9)),
        "funding_stage": max(0.0, min(1.0, stage_factor)),
    }
    product: float = 1.0
    for factor in factors.values():
        product *= factor
    match_score: int = max(0, min(100, round(product * 100)))

    limiting_key: str = min(factors, key=lambda k: factors[k])
    limiting_note: str | None = None
    if factors[limiting_key] < 0.95:
        limiting_note = f"Limited by {_DIMENSION_LABELS[limiting_key]} fit"
    return match_score, limiting_note


class JobRelevanceService:
    def __init__(self, db: AsyncSession, settings: Settings) -> None:
        self._db: AsyncSession = db
        self._settings: Settings = settings

    async def classify_jobs_for_user(self, user_id: uuid.UUID) -> int:
        """Score all unclassified active jobs for the user. Returns count scored."""
        _scoring_cancelled.discard(user_id)

        user: User | None = await self._db.get(User, user_id)
        if user is None:
            return 0

        effective_role_text: str | None = self._effective_role_text(user)
        if effective_role_text is None and user.person_id is None:
            return 0

        preferences_section: str = self._build_preferences_section(user)
        profile_section: str = await self._build_profile_section(user)
        target_min: int | None
        target_max: int | None
        target_min, target_max = await self.resolve_target_seniority_range(user)
        user_lat: float | None
        user_lng: float | None
        user_lat, user_lng = self._resolve_user_geocode(user)

        unclassified_jobs: list[OrgJob] = await self._get_unclassified_jobs(user_id)
        if not unclassified_jobs:
            return 0

        total_jobs: int = len(unclassified_jobs)
        await _set_progress(user_id, 0, total_jobs)
        _publish_scoring_progress(user_id, scored=0, total=total_jobs)

        total_classified: int = 0
        cancelled: bool = False
        preferences_text: str | None = effective_role_text
        weights: dict[str, float] = resolve_scoring_weights(user.job_scoring_weights)
        preferred_funding_stages: list[str] | None = (
            list(user.preferred_funding_stages)
            if user.preferred_funding_stages
            else None
        )
        try:
            for i in range(0, len(unclassified_jobs), _BATCH_SIZE):
                if await _is_scoring_cancelled(user_id):
                    logger.info(
                        "Scoring cancelled for user %s after %d jobs",
                        user_id,
                        total_classified,
                    )
                    _scoring_cancelled.discard(user_id)
                    cancelled = True
                    break
                batch: list[OrgJob] = unclassified_jobs[i : i + _BATCH_SIZE]
                classified: int = await self._classify_batch(
                    user_id,
                    preferences_section,
                    profile_section,
                    batch,
                    preferences_text=preferences_text,
                    preferred_funding_stages=preferred_funding_stages,
                    weights=weights,
                    target_min=target_min,
                    target_max=target_max,
                    user_lat=user_lat,
                    user_lng=user_lng,
                    user_location_pref=user.job_location_pref,
                    user_commute_max_minutes=user.job_commute_max_minutes,
                )
                total_classified += classified
                await _set_progress(user_id, total_classified, total_jobs)
                _publish_scoring_progress(
                    user_id,
                    scored=total_classified,
                    total=total_jobs,
                )

            if cancelled:
                _publish_scoring_cancelled(
                    user_id,
                    scored=total_classified,
                    total=total_jobs,
                )
            else:
                _publish_scoring_complete(
                    user_id,
                    scored=total_classified,
                    total=total_jobs,
                )

            return total_classified
        finally:
            await _clear_progress(user_id)

    @staticmethod
    def _effective_role_text(user: User) -> str | None:
        """Prefer explicit preferences; fall back to profile-derived suggestions."""
        explicit: str = (user.job_preferences_text or "").strip()
        if explicit:
            return explicit
        suggested: str = (user.job_suggested_roles or "").strip()
        if suggested:
            return suggested
        return None

    @staticmethod
    def _build_preferences_section(user: User) -> str:
        parts: list[str] = []
        explicit_text: str = (user.job_preferences_text or "").strip()
        suggested_text: str = (user.job_suggested_roles or "").strip()
        if explicit_text:
            parts.append(f"Target role / job function: {explicit_text}")
            parts.append(
                "Only score role_score above 65 if the job is clearly in this same function "
                "(judged from title + description). "
                "Engineering, design, analytics, marketing, and sales titles must score ≤25 unless "
                "they are explicit product management titles (or the JD clearly describes PM work)."
            )
        elif suggested_text:
            parts.append(
                "Target directions (inferred from candidate profile). The candidate is "
                "open to SEVERAL distinct directions listed below; treat them "
                "independently — a job is a strong match if it clearly fits ANY ONE of "
                f"them, and role_score should reflect the best-matching direction:\n{suggested_text}"
            )
            parts.append(
                "The candidate did not type an explicit target. Match on responsibilities "
                "and requirements, not title keywords alone. Do not penalize a job just "
                "because it fits only one of the directions."
            )
        else:
            parts.append(
                "Target role / job function: Infer from the CANDIDATE PROFILE below. "
                "Match jobs to the candidate's demonstrated career track and recent experience."
            )

        loc_pref: str | None = user.job_location_pref
        loc_city: str | None = user.job_location_city
        # Location is scored mechanically — keep a brief note for context only.
        if loc_pref == "remote":
            parts.append("Location preference: remote only (scored mechanically).")
        elif loc_pref == "in_person" and loc_city:
            parts.append(
                f"Location preference: in/near {loc_city} (scored mechanically)."
            )
        elif loc_pref == "either" and loc_city:
            parts.append(
                f"Location preference: remote or in/near {loc_city} (scored mechanically)."
            )
        elif loc_city:
            parts.append(
                f"Location preference: near {loc_city} or remote (scored mechanically)."
            )

        pref_text: str = "\n".join(parts) if parts else "No specific preferences stated."
        return f"CANDIDATE PREFERENCES:\n{pref_text}"

    async def _build_profile_section(self, user: User) -> str:
        if user.person_id is None:
            return "CANDIDATE PROFILE:\nNo profile available."

        person: Person | None = await self._db.get(Person, user.person_id)
        if person is None:
            return "CANDIDATE PROFILE:\nNo profile available."

        parts: list[str] = []

        if person.canonical_name:
            parts.append(f"Name: {person.canonical_name}")
        if person.current_role:
            parts.append(f"Current role: {person.current_role}")
        if person.bio_summary:
            parts.append(f"Summary: {person.bio_summary}")

        headline_result = await self._db.execute(
            select(PersonAttributeClaim.value).where(
                PersonAttributeClaim.person_id == user.person_id,
                PersonAttributeClaim.kind == "headline",
            ).limit(1),
        )
        headline: str | None = headline_result.scalar_one_or_none()
        if headline:
            parts.append(f"Headline: {headline}")

        emp_result = await self._db.execute(
            select(EmploymentClaim, Org.canonical_name).join(
                Org, EmploymentClaim.org_id == Org.id,
            ).where(
                EmploymentClaim.person_id == user.person_id,
            ).order_by(
                EmploymentClaim.is_current.desc(),
                EmploymentClaim.started_at.desc().nullslast(),
            ).limit(10),
        )
        experiences: list[str] = []
        for emp, org_name in emp_result.all():
            role: str = emp.role_title or "Unknown role"
            period: str = ""
            if emp.started_at:
                start: str = emp.started_at.strftime("%Y")
                end: str = emp.ended_at.strftime("%Y") if emp.ended_at else "present"
                period = f" ({start}–{end})"
            current_marker: str = " [current]" if emp.is_current else ""
            experiences.append(f"- {role} at {org_name}{period}{current_marker}")
        if experiences:
            parts.append("Experience:\n" + "\n".join(experiences))

        skills_result = await self._db.execute(
            select(PersonAttributeClaim.value).where(
                PersonAttributeClaim.person_id == user.person_id,
                PersonAttributeClaim.kind == "skill",
            ).limit(30),
        )
        skills: list[str] = [row[0] for row in skills_result.all()]
        if skills:
            parts.append(f"Skills: {', '.join(skills)}")

        edu_result = await self._db.execute(
            select(PersonAttributeClaim.value).where(
                PersonAttributeClaim.person_id == user.person_id,
                PersonAttributeClaim.kind == "education",
            ).limit(5),
        )
        education: list[str] = [row[0] for row in edu_result.all()]
        if education:
            parts.append("Education:\n" + "\n".join(f"- {e}" for e in education))

        if not parts:
            return "CANDIDATE PROFILE:\nNo profile available."

        return "CANDIDATE PROFILE:\n" + "\n".join(parts)

    async def _get_unclassified_jobs(self, user_id: uuid.UUID) -> list[OrgJob]:
        already_classified = (
            select(UserJobRelevance.job_id).where(UserJobRelevance.user_id == user_id)
        )
        result = await self._db.execute(
            select(OrgJob)
            .where(
                OrgJob.is_active.is_(True),
                OrgJob.id.not_in(already_classified),
            )
            .order_by(OrgJob.created_at.desc())
            .limit(500),
        )
        return list(result.scalars().all())

    async def resolve_target_seniority_range(
        self,
        user: User,
    ) -> tuple[int | None, int | None]:
        """Resolve the seniority band the user is actually shopping for.

        Precedence: the explicit control, then what they typed, then the roles
        we suggested, then their current title. Deliberately NOT the max over
        their whole history — an old "Head of Product" would otherwise make
        every Staff PM posting look under-leveled.
        """
        explicit_min: int | None = user.job_target_seniority_min
        explicit_max: int | None = user.job_target_seniority_max
        if explicit_min is not None or explicit_max is not None:
            low: int = explicit_min if explicit_min is not None else explicit_max  # type: ignore[assignment]
            high: int = explicit_max if explicit_max is not None else explicit_min  # type: ignore[assignment]
            return min(low, high), max(low, high)

        for text in (user.job_preferences_text, user.job_suggested_roles):
            parsed: tuple[int, int] | None = extract_target_seniority_range(text)
            if parsed is not None:
                return parsed

        if user.person_id is not None:
            person: Person | None = await self._db.get(Person, user.person_id)
            current_titles: list[str] = []
            if person is not None and person.current_role:
                current_titles.append(person.current_role)
            headline_result = await self._db.execute(
                select(PersonAttributeClaim.value)
                .where(
                    PersonAttributeClaim.person_id == user.person_id,
                    PersonAttributeClaim.kind == "headline",
                )
                .limit(1),
            )
            headline: str | None = headline_result.scalar_one_or_none()
            if headline:
                current_titles.append(headline)
            emp_result = await self._db.execute(
                select(EmploymentClaim.role_title)
                .where(
                    EmploymentClaim.person_id == user.person_id,
                    EmploymentClaim.role_title.is_not(None),
                    EmploymentClaim.is_current.is_(True),
                )
                .order_by(EmploymentClaim.started_at.desc().nullslast())
                .limit(1),
            )
            for (role_title,) in emp_result.all():
                if role_title:
                    current_titles.append(role_title)

            for title in current_titles:
                level: int | None = classify_seniority_level(title)
                if level is not None:
                    # Someone at level L is shopping at L or a step up, not down.
                    return level, level + 1

        return None, None

    @staticmethod
    def _resolve_user_geocode(user: User) -> tuple[float | None, float | None]:
        geo: tuple[float, float, str] | None = geocode_location(user.job_location_city)
        if geo is None:
            return None, None
        return geo[0], geo[1]

    @staticmethod
    def _mechanical_seniority_location(
        job: OrgJob,
        *,
        target_min: int | None,
        target_max: int | None,
        user_lat: float | None,
        user_lng: float | None,
        user_location_pref: str | None,
        user_commute_max_minutes: int | None,
    ) -> tuple[int, str, int, str]:
        job_level: int | None = job.seniority_level
        if job_level is None:
            job_level = classify_seniority_level(job.title, job.description_snippet)
        seniority_score: int = seniority_range_score(job_level, target_min, target_max)
        seniority_reason: str = seniority_range_reason(
            job_level,
            target_min,
            target_max,
            seniority_score,
        )

        job_lat: float | None = job.location_lat
        job_lng: float | None = job.location_lng
        job_normalized: str | None = job.location_normalized
        if job_lat is None or job_lng is None:
            geo: tuple[float, float, str] | None = geocode_location(job.location)
            if geo is not None:
                job_lat, job_lng, job_normalized = geo

        location_score: int = location_match_score(
            job_lat=job_lat,
            job_lng=job_lng,
            job_remote_status=job.remote_status,
            job_location=job.location,
            user_lat=user_lat,
            user_lng=user_lng,
            user_pref=user_location_pref,
            commute_max_minutes=user_commute_max_minutes,
        )
        location_reason: str = location_match_reason(
            score=location_score,
            job_lat=job_lat,
            job_lng=job_lng,
            job_remote_status=job.remote_status,
            job_location=job.location,
            job_location_normalized=job_normalized,
            user_lat=user_lat,
            user_lng=user_lng,
            user_pref=user_location_pref,
            commute_max_minutes=user_commute_max_minutes,
        )
        return seniority_score, seniority_reason, location_score, location_reason

    async def _classify_batch(
        self,
        user_id: uuid.UUID,
        preferences_section: str,
        profile_section: str,
        jobs: list[OrgJob],
        *,
        preferences_text: str | None = None,
        preferred_funding_stages: list[str] | None = None,
        weights: dict[str, float] | None = None,
        target_min: int | None = None,
        target_max: int | None = None,
        user_lat: float | None = None,
        user_lng: float | None = None,
        user_location_pref: str | None = None,
        user_commute_max_minutes: int | None = None,
    ) -> int:
        resolved_weights: dict[str, float] = (
            weights if weights is not None else dict(DEFAULT_SCORING_WEIGHTS)
        )
        job_descriptions: list[str] = []
        for idx, job in enumerate(jobs):
            job_descriptions.append(
                _JOB_TEMPLATE.format(
                    index=idx,
                    title=job.title,
                    department=job.department or "N/A",
                    location=job.location or "N/A",
                    remote=job.remote_status or "N/A",
                    snippet=(job.description_snippet or "")[:500],
                ),
            )

        system_prompt: str = _SYSTEM_PROMPT.format(
            preferences=preferences_section,
            profile=profile_section,
        )
        user_content: str = "Score these jobs:\n\n" + "\n".join(job_descriptions)

        results: list[dict[str, Any]] = await self._call_openai(system_prompt, user_content)

        org_ids: list[uuid.UUID] = list({job.org_id for job in jobs})
        org_stage_map: dict[uuid.UUID, str | None] = {}
        if org_ids:
            org_result = await self._db.execute(
                select(Org.id, Org.funding_stage).where(Org.id.in_(org_ids)),
            )
            org_stage_map = {row.id: row.funding_stage for row in org_result.all()}

        now: datetime = datetime.now(tz=UTC)
        classified: int = 0
        for item in results:
            idx: int = item.get("index", -1)
            if idx < 0 or idx >= len(jobs):
                continue
            job: OrgJob = jobs[idx]

            role_score: int = max(0, min(100, int(item.get("role_score", 50))))
            qualification_score: int = max(
                0,
                min(100, int(item.get("qualification_score", 50))),
            )

            role_reason: str | None = item.get("role_reason")
            role_score, role_reason = _cap_role_score_for_function_mismatch(
                preferences_text,
                job,
                role_score,
                role_reason,
            )

            (
                seniority_score,
                seniority_reason,
                location_score,
                location_reason,
            ) = self._mechanical_seniority_location(
                job,
                target_min=target_min,
                target_max=target_max,
                user_lat=user_lat,
                user_lng=user_lng,
                user_location_pref=user_location_pref,
                user_commute_max_minutes=user_commute_max_minutes,
            )

            stage_factor: float = stage_match_factor(
                org_funding_stage=org_stage_map.get(job.org_id),
                preferred_funding_stages=preferred_funding_stages,
                weight=resolved_weights.get("funding_stage", 0.7),
            )
            match_score, limiting_note = compute_match_score(
                role_score=role_score,
                qualification_score=qualification_score,
                seniority_score=seniority_score,
                location_score=location_score,
                weights=resolved_weights,
                stage_factor=stage_factor,
            )

            qualification_reason: str | None = item.get("qualification_reason")

            reason: str = " | ".join(
                filter(
                    None,
                    [
                        role_reason,
                        qualification_reason,
                        seniority_reason,
                        location_reason,
                        limiting_note,
                    ],
                ),
            )
            is_relevant: bool = match_score >= _MATCH_SCORE_RELEVANT_THRESHOLD

            relevance = UserJobRelevance(
                user_id=user_id,
                job_id=job.id,
                is_relevant=is_relevant,
                confidence=match_score / 100.0,
                match_score=match_score,
                reason=reason or None,
                role_score=role_score,
                role_reason=role_reason,
                location_score=location_score,
                location_reason=location_reason,
                seniority_score=seniority_score,
                seniority_reason=seniority_reason,
                qualification_score=qualification_score,
                qualification_reason=qualification_reason,
                classified_at=now,
            )
            self._db.add(relevance)
            classified += 1

        await self._db.commit()
        return classified

    async def reclassify_all(self, user_id: uuid.UUID) -> int:
        """Delete existing classifications and re-classify all active jobs."""
        from sqlalchemy import delete

        await self._db.execute(
            delete(UserJobRelevance).where(UserJobRelevance.user_id == user_id),
        )
        await self._db.commit()
        return await self.classify_jobs_for_user(user_id)

    async def rescore_existing_matches(self, user_id: uuid.UUID) -> int:
        """Recompute seniority/location/match from stored role+qualification.

        Used when weights, funding stages, or location prefs change — no LLM.
        The function-mismatch cap is re-applied to the stored role score so that
        tightened mismatch rules reach already-scored jobs without a re-run; the
        cap only ever lowers a score, so this is idempotent.
        """
        user: User | None = await self._db.get(User, user_id)
        if user is None:
            return 0

        preferences_text: str | None = self._effective_role_text(user)
        weights: dict[str, float] = resolve_scoring_weights(user.job_scoring_weights)
        preferred_funding_stages: list[str] | None = (
            list(user.preferred_funding_stages)
            if user.preferred_funding_stages
            else None
        )
        target_min: int | None
        target_max: int | None
        target_min, target_max = await self.resolve_target_seniority_range(user)
        user_lat: float | None
        user_lng: float | None
        user_lat, user_lng = self._resolve_user_geocode(user)

        rows_result = await self._db.execute(
            select(UserJobRelevance, OrgJob)
            .join(OrgJob, OrgJob.id == UserJobRelevance.job_id)
            .where(UserJobRelevance.user_id == user_id),
        )
        rows: list[tuple[UserJobRelevance, OrgJob]] = list(rows_result.all())
        if not rows:
            return 0

        org_ids: list[uuid.UUID] = list({job.org_id for _, job in rows})
        org_result = await self._db.execute(
            select(Org.id, Org.funding_stage).where(Org.id.in_(org_ids)),
        )
        org_stage_map: dict[uuid.UUID, str | None] = {
            row.id: row.funding_stage for row in org_result.all()
        }

        updated: int = 0
        for relevance, job in rows:
            if (
                relevance.role_score is None
                or relevance.qualification_score is None
            ):
                continue

            role_score: int
            role_reason: str | None
            role_score, role_reason = _cap_role_score_for_function_mismatch(
                preferences_text,
                job,
                relevance.role_score,
                relevance.role_reason,
            )

            (
                seniority_score,
                seniority_reason,
                location_score,
                location_reason,
            ) = self._mechanical_seniority_location(
                job,
                target_min=target_min,
                target_max=target_max,
                user_lat=user_lat,
                user_lng=user_lng,
                user_location_pref=user.job_location_pref,
                user_commute_max_minutes=user.job_commute_max_minutes,
            )

            stage_factor: float = stage_match_factor(
                org_funding_stage=org_stage_map.get(job.org_id),
                preferred_funding_stages=preferred_funding_stages,
                weight=weights.get("funding_stage", 0.7),
            )
            match_score, limiting_note = compute_match_score(
                role_score=role_score,
                qualification_score=relevance.qualification_score,
                seniority_score=seniority_score,
                location_score=location_score,
                weights=weights,
                stage_factor=stage_factor,
            )
            reason: str = " | ".join(
                filter(
                    None,
                    [
                        role_reason,
                        relevance.qualification_reason,
                        seniority_reason,
                        location_reason,
                        limiting_note,
                    ],
                ),
            )
            relevance.role_score = role_score
            relevance.role_reason = role_reason
            relevance.seniority_score = seniority_score
            relevance.seniority_reason = seniority_reason
            relevance.location_score = location_score
            relevance.location_reason = location_reason
            relevance.match_score = match_score
            relevance.is_relevant = match_score >= _MATCH_SCORE_RELEVANT_THRESHOLD
            relevance.confidence = match_score / 100.0
            relevance.reason = reason or None
            updated += 1

        await self._db.commit()
        return updated

    async def _call_openai(
        self,
        system_prompt: str,
        user_content: str,
    ) -> list[dict[str, Any]]:
        api_key: str | None = self._settings.openai_api_key
        if not api_key:
            logger.warning("No OpenAI API key configured; skipping classification")
            return []

        payload: dict[str, object] = {
            "model": "gpt-4o-mini",
            "temperature": 0,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
        }
        try:
            async with httpx.AsyncClient(timeout=60.0) as http:
                response = await http.post(
                    f"{self._settings.openai_base_url.rstrip('/')}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )
                response.raise_for_status()
                raw_content: str = content_from_chat_completion(
                    cast(dict[str, object], response.json()),
                )
                data: dict[str, object] = parse_json_object(raw_content)
                results_raw: object = data.get("results", [])
                if not isinstance(results_raw, list):
                    return []
                return cast(list[dict[str, Any]], results_raw)
        except Exception:
            logger.exception("OpenAI classification call failed")
            return []
