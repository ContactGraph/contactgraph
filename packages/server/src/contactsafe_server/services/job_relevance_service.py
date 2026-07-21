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
from contactsafe_server.events import (
    ScoringCancelledEvent,
    ScoringCompleteEvent,
    ScoringProgressEvent,
    job_event_bus,
)
from contactsafe_server.db.models import (
    EmploymentClaim,
    Org,
    OrgJob,
    Person,
    PersonAttributeClaim,
    User,
    UserJobRelevance,
)
from contactsafe_server.services.openai_json import (
    content_from_chat_completion,
    parse_json_object,
)
from contactsafe_server.services.org_funding_stage import funding_stage_label

logger: logging.Logger = logging.getLogger(__name__)

_BATCH_SIZE: int = 15
_MATCH_SCORE_RELEVANT_THRESHOLD: int = 40
_STAGE_BOOST: int = 8

_ROLE_WEIGHT: float = 0.45
_QUALIFICATION_WEIGHT: float = 0.25
_SENIORITY_WEIGHT: float = 0.15
_LOCATION_WEIGHT: float = 0.15

_SYSTEM_PROMPT: str = """\
You are a strict job-match scoring engine. You will receive the candidate's professional \
profile and a batch of job postings. Evaluate each job on FOUR separate dimensions.

{preferences}

{profile}

For each job, provide four independent sub-scores (each 0-100):

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
the title matches. A paralegal role for an experienced PM should score near 0.

3. **seniority_score**: How well the seniority/level matches. Senior ↔ Senior is good (80-100). \
IC ↔ management mismatch or large level gaps should be penalized.

4. **location_score**: How well the location/remote setup matches the candidate's preferences. \
If the candidate wants remote and the job is remote, score 90-100. If commute preferences \
are stated, penalize jobs beyond the candidate's max commute distance.

For each sub-score, provide a brief reason (1 sentence) explaining the score.

Respond with a JSON object containing a "results" array. Each element must have:
- "index": the 0-based index of the job in the input list
- "role_score": integer 0-100
- "role_reason": string (1 sentence)
- "qualification_score": integer 0-100
- "qualification_reason": string (1 sentence)
- "seniority_score": integer 0-100
- "seniority_reason": string (1 sentence)
- "location_score": integer 0-100
- "location_reason": string (1 sentence)

Example:
{{"results": [
  {{"index": 0, "role_score": 12, "role_reason": "Director of Software Engineering is an engineering leadership role, not product management.", "qualification_score": 40, "qualification_reason": "Strong leadership experience but wrong function.", "seniority_score": 90, "seniority_reason": "Director level matches seniority.", "location_score": 60, "location_reason": "San Jose is within commute range but not ideal."}},
  {{"index": 1, "role_score": 92, "role_reason": "Principal Product Manager matches the candidate's product management target.", "qualification_score": 88, "qualification_reason": "Background in B2B platform PM aligns with the JD requirements.", "seniority_score": 88, "seniority_reason": "Principal level aligns with experience.", "location_score": 70, "location_reason": "Santa Clara is a reasonable commute."}}
]}}
"""

_JOB_TEMPLATE: str = (
    "#{index}: title={title} | dept={department} | location={location} | "
    "remote={remote} | snippet={snippet}"
)

_PM_PREFERENCE_RE: re.Pattern[str] = re.compile(
    r"\b(product manager|product management|pm)\b",
    re.IGNORECASE,
)
_PM_TITLE_RE: re.Pattern[str] = re.compile(
    r"\b("
    r"product manager|product management|group product manager|"
    r"principal product manager|senior product manager|associate product manager|"
    r"director[, ]+ product|head of product|product lead|vp[, ]+ product"
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
    r"\b(product marketing|marketing manager|product marketer)\b",
    re.IGNORECASE,
)
_DESIGN_TITLE_RE: re.Pattern[str] = re.compile(
    r"\b("
    r"product designer|ux designer|ui designer|ux/ui designer|"
    r"interaction designer|visual designer|design lead|head of design"
    r")\b",
    re.IGNORECASE,
)
_ANALYST_TITLE_RE: re.Pattern[str] = re.compile(
    r"\b("
    r"product analyst|data analyst|business analyst|analytics manager|"
    r"insights analyst|research analyst"
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
    if _ENGINEERING_TITLE_RE.search(haystack):
        capped: int = min(role_score, 15)
        if capped < role_score:
            return capped, (
                "The job title indicates engineering, not product management."
            )
    if _MARKETING_TITLE_RE.search(haystack):
        capped = min(role_score, 20)
        if capped < role_score:
            return capped, (
                "The job title indicates marketing, not product management."
            )
    if _DESIGN_TITLE_RE.search(haystack):
        capped = min(role_score, 15)
        if capped < role_score:
            return capped, (
                "The job title indicates product design, not product management."
            )
    if _ANALYST_TITLE_RE.search(haystack):
        capped = min(role_score, 20)
        if capped < role_score:
            return capped, (
                "The job title indicates analytics, not product management."
            )
    if _LEGAL_TITLE_RE.search(haystack):
        capped = min(role_score, 10)
        if capped < role_score:
            return capped, (
                "The job title indicates a legal role, not product management."
            )
    return role_score, role_reason


def _apply_funding_stage_boost(
    match_score: int,
    reason: str,
    *,
    org_funding_stage: str | None,
    preferred_funding_stages: list[str] | None,
) -> tuple[int, str]:
    """Positive-only stage nudge when the org stage is in the user's preferences."""
    if not preferred_funding_stages:
        return match_score, reason
    if org_funding_stage is None or org_funding_stage not in preferred_funding_stages:
        return match_score, reason
    boosted: int = min(100, match_score + _STAGE_BOOST)
    stage_note: str = f"{funding_stage_label(org_funding_stage)} matches your stage preference"
    if reason:
        return boosted, f"{reason} | {stage_note}"
    return boosted, stage_note


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

        unclassified_jobs: list[OrgJob] = await self._get_unclassified_jobs(user_id)
        if not unclassified_jobs:
            return 0

        total_jobs: int = len(unclassified_jobs)
        await _set_progress(user_id, 0, total_jobs)
        _publish_scoring_progress(user_id, scored=0, total=total_jobs)

        total_classified: int = 0
        cancelled: bool = False
        preferences_text: str | None = effective_role_text
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
                    preferred_funding_stages=(
                        list(user.preferred_funding_stages)
                        if user.preferred_funding_stages
                        else None
                    ),
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
        if loc_pref == "remote":
            parts.append("Location: REMOTE ONLY. Penalize any job requiring in-person attendance unless also listed as remote.")
        elif loc_pref == "in_person" and loc_city:
            parts.append(
                f"Location: Must be in or near {loc_city}. Penalize remote-only jobs and jobs far from {loc_city}."
            )
        elif loc_pref == "either" and loc_city:
            parts.append(
                f"Location: Prefers remote OR in/near {loc_city}. Penalize jobs requiring in-person far from {loc_city}."
            )
        elif loc_city:
            parts.append(f"Location: Prefers jobs near {loc_city} or remote.")

        commute_max: int | None = user.job_commute_max_minutes
        commute_note: str | None = user.job_commute_note
        if commute_max is not None and loc_city:
            parts.append(
                f"Commute: Maximum {commute_max} minutes from {loc_city}. "
                "Penalize jobs located significantly beyond this commute distance."
            )
        if commute_note:
            parts.append(f"Commute flexibility: {commute_note}")

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

    async def _classify_batch(
        self,
        user_id: uuid.UUID,
        preferences_section: str,
        profile_section: str,
        jobs: list[OrgJob],
        *,
        preferences_text: str | None = None,
        preferred_funding_stages: list[str] | None = None,
    ) -> int:
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
            seniority_score: int = max(0, min(100, int(item.get("seniority_score", 50))))
            location_score: int = max(0, min(100, int(item.get("location_score", 50))))

            role_reason: str | None = item.get("role_reason")
            role_score, role_reason = _cap_role_score_for_function_mismatch(
                preferences_text,
                job,
                role_score,
                role_reason,
            )

            match_score: int = round(
                role_score * _ROLE_WEIGHT
                + qualification_score * _QUALIFICATION_WEIGHT
                + seniority_score * _SENIORITY_WEIGHT
                + location_score * _LOCATION_WEIGHT,
            )
            match_score = max(0, min(100, match_score))

            qualification_reason: str | None = item.get("qualification_reason")
            seniority_reason: str | None = item.get("seniority_reason")
            location_reason: str | None = item.get("location_reason")

            reason: str = " | ".join(
                filter(
                    None,
                    [
                        role_reason,
                        qualification_reason,
                        seniority_reason,
                        location_reason,
                    ],
                ),
            )

            match_score, reason = _apply_funding_stage_boost(
                match_score,
                reason,
                org_funding_stage=org_stage_map.get(job.org_id),
                preferred_funding_stages=preferred_funding_stages,
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
