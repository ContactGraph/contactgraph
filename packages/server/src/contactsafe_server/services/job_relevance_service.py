"""LLM-based job relevance scoring service."""

from __future__ import annotations

import logging
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
from contactsafe_server.services.openai_json import (
    content_from_chat_completion,
    parse_json_object,
)

logger: logging.Logger = logging.getLogger(__name__)

_BATCH_SIZE: int = 15
_MATCH_SCORE_RELEVANT_THRESHOLD: int = 40

_SYSTEM_PROMPT: str = """\
You are a job-match scoring engine. You will receive the candidate's professional profile \
and a batch of job postings. Score each job on how well it matches the candidate.

Consider:
- Alignment between the candidate's experience/skills and the job requirements
- Seniority level match
- Industry/domain relevance
- Location/remote compatibility

{preferences}

{profile}

Respond with a JSON object containing a "results" array. Each element must have:
- "index": the 0-based index of the job in the input list
- "match_score": integer 0-100 (0 = completely irrelevant, 100 = perfect match)
- "reason": brief 5-15 word explanation of the score

Example response:
{{"results": [{{"index": 0, "match_score": 85, "reason": "Strong backend fit, Python expertise matches requirements"}}]}}
"""

_JOB_TEMPLATE: str = (
    "#{index}: title={title} | dept={department} | location={location} | "
    "remote={remote} | snippet={snippet}"
)


class JobRelevanceService:
    def __init__(self, db: AsyncSession, settings: Settings) -> None:
        self._db: AsyncSession = db
        self._settings: Settings = settings

    async def classify_jobs_for_user(self, user_id: uuid.UUID) -> int:
        """Score all unclassified active jobs for the user. Returns count scored."""
        user: User | None = await self._db.get(User, user_id)
        if user is None or not user.job_preferences_text:
            return 0

        preferences_section: str = self._build_preferences_section(user)
        profile_section: str = await self._build_profile_section(user)

        unclassified_jobs: list[OrgJob] = await self._get_unclassified_jobs(user_id)
        if not unclassified_jobs:
            return 0

        total_classified: int = 0
        for i in range(0, len(unclassified_jobs), _BATCH_SIZE):
            batch: list[OrgJob] = unclassified_jobs[i : i + _BATCH_SIZE]
            classified: int = await self._classify_batch(
                user_id, preferences_section, profile_section, batch,
            )
            total_classified += classified

        return total_classified

    @staticmethod
    def _build_preferences_section(user: User) -> str:
        parts: list[str] = []
        role_text: str = (user.job_preferences_text or "").strip()
        if role_text:
            parts.append(f"Role interests: {role_text}")

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
                    snippet=(job.description_snippet or "")[:200],
                ),
            )

        system_prompt: str = _SYSTEM_PROMPT.format(
            preferences=preferences_section,
            profile=profile_section,
        )
        user_content: str = "Score these jobs:\n\n" + "\n".join(job_descriptions)

        results: list[dict[str, Any]] = await self._call_openai(system_prompt, user_content)

        now: datetime = datetime.now(tz=UTC)
        classified: int = 0
        for item in results:
            idx: int = item.get("index", -1)
            if idx < 0 or idx >= len(jobs):
                continue
            job: OrgJob = jobs[idx]
            match_score: int = max(0, min(100, int(item.get("match_score", 50))))
            is_relevant: bool = match_score >= _MATCH_SCORE_RELEVANT_THRESHOLD
            reason: str | None = item.get("reason")

            relevance = UserJobRelevance(
                user_id=user_id,
                job_id=job.id,
                is_relevant=is_relevant,
                confidence=match_score / 100.0,
                match_score=match_score,
                reason=reason,
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
