"""LLM-based job relevance classification service."""

from __future__ import annotations

import json
import logging
import uuid
from datetime import UTC, datetime
from typing import Any, cast

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from contactsafe_server.config import Settings
from contactsafe_server.db.models import OrgJob, User, UserJobRelevance
from contactsafe_server.services.openai_json import (
    content_from_chat_completion,
    parse_json_object,
)

logger: logging.Logger = logging.getLogger(__name__)

_BATCH_SIZE: int = 15

_SYSTEM_PROMPT: str = """\
You are a job relevance classifier. The user has described what kinds of roles they are \
interested in. You will receive a batch of job postings and must classify each one as \
relevant or not relevant to the user's stated interests.

IMPORTANT: Err on the side of marking jobs as relevant. When in doubt, mark as relevant. \
It is much worse to miss a desired job than to show an undesirable one.

User's job preferences:
{preferences}

Respond with a JSON object containing a "results" array. Each element must have:
- "index": the 0-based index of the job in the input list
- "relevant": boolean (true if the job matches their interests)
- "confidence": float 0.0-1.0 (how confident you are)
- "reason": brief 5-10 word explanation

Example response:
{{"results": [{{"index": 0, "relevant": true, "confidence": 0.9, "reason": "Backend engineering role in Python"}}]}}
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
        """Classify all unclassified active jobs for the user. Returns count classified."""
        user: User | None = await self._db.get(User, user_id)
        if user is None or not user.job_preferences_text:
            return 0

        preferences: str = user.job_preferences_text.strip()
        if not preferences:
            return 0

        unclassified_jobs: list[OrgJob] = await self._get_unclassified_jobs(user_id)
        if not unclassified_jobs:
            return 0

        total_classified: int = 0
        for i in range(0, len(unclassified_jobs), _BATCH_SIZE):
            batch: list[OrgJob] = unclassified_jobs[i : i + _BATCH_SIZE]
            classified: int = await self._classify_batch(user_id, preferences, batch)
            total_classified += classified

        return total_classified

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
        preferences: str,
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

        system_prompt: str = _SYSTEM_PROMPT.format(preferences=preferences)
        user_content: str = "Classify these jobs:\n\n" + "\n".join(job_descriptions)

        results: list[dict[str, Any]] = await self._call_openai(system_prompt, user_content)

        now: datetime = datetime.now(tz=UTC)
        classified: int = 0
        for item in results:
            idx: int = item.get("index", -1)
            if idx < 0 or idx >= len(jobs):
                continue
            job: OrgJob = jobs[idx]
            is_relevant: bool = bool(item.get("relevant", True))
            confidence: float = float(item.get("confidence", 0.5))
            reason: str | None = item.get("reason")

            relevance = UserJobRelevance(
                user_id=user_id,
                job_id=job.id,
                is_relevant=is_relevant,
                confidence=confidence,
                reason=reason if is_relevant else None,
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
