"""Enqueue and manage per-contact enrichment queue items."""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from contactsafe_core.enums import EnrichmentQueueStatus, EnrichmentRunState
from contactsafe_server.config import Settings
from contactsafe_server.db.models import (
    EnrichmentQueueItem,
    EnrichmentRun,
    Person,
    UserPersonObservation,
)
from contactsafe_server.services.enrichment_strategies.base import (
    DEFAULT_ENRICHMENT_STRATEGIES,
    compute_enqueue_priority,
)

logger: logging.Logger = logging.getLogger(__name__)

_ACTIVE_STATUSES: frozenset[str] = frozenset({
    EnrichmentQueueStatus.PENDING.value,
    EnrichmentQueueStatus.IN_PROGRESS.value,
    EnrichmentQueueStatus.DEFERRED.value,
})


class EnrichmentQueueService:
    def __init__(self, db: AsyncSession, settings: Settings) -> None:
        self._db: AsyncSession = db
        self._settings: Settings = settings

    async def enqueue_enrichment(
        self,
        *,
        person_id: uuid.UUID,
        trigger_user_id: uuid.UUID,
        priority: int | None = None,
        enrichment_run_id: uuid.UUID | None = None,
        manual_boost: int = 0,
    ) -> EnrichmentQueueItem:
        resolved_priority: int = priority
        if resolved_priority is None:
            obs: UserPersonObservation | None = await self._load_observation(
                trigger_user_id, person_id
            )
            resolved_priority = compute_enqueue_priority(obs, manual_boost=manual_boost)

        strategies: list[str] = list(DEFAULT_ENRICHMENT_STRATEGIES)
        result = await self._db.execute(
            select(EnrichmentQueueItem).where(
                EnrichmentQueueItem.person_id == person_id
            )
        )
        existing: EnrichmentQueueItem | None = result.scalar_one_or_none()

        if existing is not None:
            if existing.status in _ACTIVE_STATUSES:
                if resolved_priority > existing.priority:
                    existing.priority = resolved_priority
                if enrichment_run_id is not None:
                    existing.enrichment_run_id = enrichment_run_id
                if existing.status == EnrichmentQueueStatus.DEFERRED.value:
                    existing.status = EnrichmentQueueStatus.PENDING.value
                    existing.next_attempt_after = None
                await self._db.flush()
                return existing

            existing.status = EnrichmentQueueStatus.PENDING.value
            existing.priority = max(existing.priority, resolved_priority)
            existing.trigger_user_id = trigger_user_id
            existing.enrichment_run_id = enrichment_run_id
            existing.strategies_attempted = []
            existing.strategies_remaining = strategies
            existing.result_confidence = 0.0
            existing.attempts_count = 0
            existing.last_attempted_at = None
            existing.next_attempt_after = None
            existing.error = None
            await self._db.flush()
            return existing

        item = EnrichmentQueueItem(
            person_id=person_id,
            trigger_user_id=trigger_user_id,
            enrichment_run_id=enrichment_run_id,
            priority=resolved_priority,
            status=EnrichmentQueueStatus.PENDING.value,
            strategies_attempted=[],
            strategies_remaining=strategies,
        )
        self._db.add(item)
        await self._db.flush()
        return item

    async def enqueue_user_contacts(
        self,
        *,
        user_id: uuid.UUID,
        enrichment_run_id: uuid.UUID | None = None,
    ) -> int:
        result = await self._db.execute(
            select(Person, UserPersonObservation)
            .join(
                UserPersonObservation,
                (UserPersonObservation.person_id == Person.id)
                & (UserPersonObservation.user_id == user_id),
            )
            .where(
                UserPersonObservation.is_automated.is_(False),
                UserPersonObservation.is_broadcast.is_(False),
            )
        )
        rows: list[tuple[Person, UserPersonObservation]] = list(result.all())
        count: int = 0
        for person, obs in rows:
            if not person.primary_email:
                continue
            await self.enqueue_enrichment(
                person_id=person.id,
                trigger_user_id=user_id,
                priority=compute_enqueue_priority(obs),
                enrichment_run_id=enrichment_run_id,
            )
            count += 1
        return count

    async def claim_next_item(self) -> EnrichmentQueueItem | None:
        now: datetime = datetime.now(tz=UTC)
        stmt = (
            select(EnrichmentQueueItem)
            .where(
                EnrichmentQueueItem.status == EnrichmentQueueStatus.PENDING.value,
                (
                    EnrichmentQueueItem.next_attempt_after.is_(None)
                    | (EnrichmentQueueItem.next_attempt_after <= now)
                ),
            )
            .order_by(
                EnrichmentQueueItem.priority.desc(),
                EnrichmentQueueItem.created_at.asc(),
            )
            .limit(1)
            .with_for_update(skip_locked=True)
        )
        result = await self._db.execute(stmt)
        item: EnrichmentQueueItem | None = result.scalar_one_or_none()
        if item is None:
            return None

        item.status = EnrichmentQueueStatus.IN_PROGRESS.value
        item.attempts_count += 1
        item.last_attempted_at = now
        await self._db.flush()
        return item

    async def mark_complete(
        self,
        item: EnrichmentQueueItem,
        *,
        confidence: float,
    ) -> None:
        item.status = EnrichmentQueueStatus.COMPLETE.value
        item.result_confidence = confidence
        item.error = None
        item.next_attempt_after = None
        await self._db.flush()
        if item.enrichment_run_id is not None:
            await self._update_run_progress(item.enrichment_run_id)

    async def mark_deferred(
        self,
        item: EnrichmentQueueItem,
        *,
        error: str,
    ) -> None:
        if item.attempts_count >= self._settings.enrichment_max_retries:
            await self.mark_failed(item, error=error)
            return

        backoff_seconds: int = self._settings.enrichment_backoff_base_seconds * (
            item.attempts_count ** 2
        )
        item.status = EnrichmentQueueStatus.DEFERRED.value
        item.error = error[:500]
        item.next_attempt_after = datetime.now(tz=UTC) + timedelta(seconds=backoff_seconds)
        await self._db.flush()

    async def mark_failed(
        self,
        item: EnrichmentQueueItem,
        *,
        error: str,
    ) -> None:
        item.status = EnrichmentQueueStatus.FAILED.value
        item.error = error[:500]
        await self._db.flush()
        if item.enrichment_run_id is not None:
            await self._update_run_progress(item.enrichment_run_id)

    async def get_contact_status(
        self,
        *,
        user_id: uuid.UUID,
        person_id: uuid.UUID,
    ) -> EnrichmentQueueItem | None:
        result = await self._db.execute(
            select(EnrichmentQueueItem).where(
                EnrichmentQueueItem.person_id == person_id,
                EnrichmentQueueItem.trigger_user_id == user_id,
            )
        )
        return result.scalar_one_or_none()

    async def list_user_queue_status(
        self,
        user_id: uuid.UUID,
        *,
        limit: int = 100,
    ) -> list[EnrichmentQueueItem]:
        result = await self._db.execute(
            select(EnrichmentQueueItem)
            .where(EnrichmentQueueItem.trigger_user_id == user_id)
            .order_by(EnrichmentQueueItem.updated_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def count_pending_for_run(self, run_id: uuid.UUID) -> int:
        result = await self._db.execute(
            select(func.count())
            .select_from(EnrichmentQueueItem)
            .where(
                EnrichmentQueueItem.enrichment_run_id == run_id,
                EnrichmentQueueItem.status.in_([
                    EnrichmentQueueStatus.PENDING.value,
                    EnrichmentQueueStatus.IN_PROGRESS.value,
                    EnrichmentQueueStatus.DEFERRED.value,
                ]),
            )
        )
        return int(result.scalar_one())

    async def count_completed_for_run(self, run_id: uuid.UUID) -> int:
        result = await self._db.execute(
            select(func.count())
            .select_from(EnrichmentQueueItem)
            .where(
                EnrichmentQueueItem.enrichment_run_id == run_id,
                EnrichmentQueueItem.status == EnrichmentQueueStatus.COMPLETE.value,
            )
        )
        return int(result.scalar_one())

    async def _update_run_progress(self, run_id: uuid.UUID) -> None:
        run: EnrichmentRun | None = await self._db.get(EnrichmentRun, run_id)
        if run is None:
            return

        completed: int = await self.count_completed_for_run(run_id)
        pending: int = await self.count_pending_for_run(run_id)
        run.contacts_enriched = completed

        if pending == 0 and run.state == EnrichmentRunState.RUNNING.value:
            run.state = EnrichmentRunState.COMPLETE.value
            run.completed_at = datetime.now(tz=UTC)
            run.progress_message = None
        await self._db.flush()

    async def _load_observation(
        self,
        user_id: uuid.UUID,
        person_id: uuid.UUID,
    ) -> UserPersonObservation | None:
        result = await self._db.execute(
            select(UserPersonObservation).where(
                UserPersonObservation.user_id == user_id,
                UserPersonObservation.person_id == person_id,
            )
        )
        return result.scalar_one_or_none()


async def enqueue_enrichment(
    db: AsyncSession,
    settings: Settings,
    *,
    person_id: uuid.UUID,
    trigger_user_id: uuid.UUID,
    priority: int | None = None,
    enrichment_run_id: uuid.UUID | None = None,
) -> EnrichmentQueueItem:
    service = EnrichmentQueueService(db, settings)
    return await service.enqueue_enrichment(
        person_id=person_id,
        trigger_user_id=trigger_user_id,
        priority=priority,
        enrichment_run_id=enrichment_run_id,
    )
