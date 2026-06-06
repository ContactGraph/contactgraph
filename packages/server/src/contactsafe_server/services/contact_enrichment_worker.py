"""Process a single enrichment queue item through the strategy pipeline."""

from __future__ import annotations

import logging
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from contactsafe_server.config import Settings
from contactsafe_server.db.models import (
    EnrichmentQueueItem,
    Person,
    PersonAlias,
    UserPersonObservation,
)
from contactsafe_server.services.contact_enrichment_engine import ContactEnrichmentEngine
from contactsafe_server.services.enrichment_queue_service import EnrichmentQueueService
from contactsafe_server.services.enrichment_strategies.base import compute_enrichment_confidence
from contactsafe_server.services.person_profile_recompute import PersonProfileRecompute
from contactsafe_server.services.user_org_observation_service import rebuild_user_org_observations

logger: logging.Logger = logging.getLogger(__name__)


class ContactEnrichmentWorker:
    def __init__(self, db: AsyncSession, settings: Settings) -> None:
        self._db: AsyncSession = db
        self._settings: Settings = settings
        self._engine: ContactEnrichmentEngine = ContactEnrichmentEngine(db, settings)
        self._queue: EnrichmentQueueService = EnrichmentQueueService(db, settings)
        self._recompute: PersonProfileRecompute = PersonProfileRecompute(db)

    async def enrich_one(self, item: EnrichmentQueueItem) -> None:
        person: Person | None = await self._db.get(Person, item.person_id)
        if person is None:
            await self._queue.mark_failed(item, error="person_not_found")
            await self._db.commit()
            return

        obs: UserPersonObservation | None = await self._load_observation(
            item.trigger_user_id,
            item.person_id,
        )
        if obs is None:
            await self._queue.mark_failed(item, error="observation_not_found")
            await self._db.commit()
            return

        if obs.is_automated or obs.is_broadcast:
            await self._queue.mark_complete(item, confidence=0.0)
            await self._db.commit()
            return

        context = await self._engine.load_user_context(item.trigger_user_id)
        accumulator = await self._engine.build_accumulator(person, obs)

        remaining: list[str] = list(item.strategies_remaining or [])
        attempted: list[str] = list(item.strategies_attempted or [])
        max_strategies: int = self._settings.enrichment_max_strategies_per_contact
        strategies_run: int = 0

        try:
            while remaining and strategies_run < max_strategies:
                strategy: str = remaining.pop(0)
                attempted.append(strategy)
                strategies_run += 1

                async with self._db.begin_nested():
                    await self._engine.run_strategy(
                        strategy,
                        person=person,
                        obs=obs,
                        accumulator=accumulator,
                        user_id=item.trigger_user_id,
                        context=context,
                    )

                await self._recompute.recompute_persons([person.id])
                await self._db.refresh(person)

                linkedin_url: str | None = await self._load_person_linkedin_url(person.id)
                confidence = compute_enrichment_confidence(
                    person,
                    linkedin_url=linkedin_url,
                )
                item.result_confidence = confidence.score
                item.strategies_attempted = attempted
                item.strategies_remaining = remaining

                if confidence.score >= self._settings.enrichment_confidence_threshold:
                    break

            await rebuild_user_org_observations(self._db, item.trigger_user_id)
            linkedin_url_final: str | None = await self._load_person_linkedin_url(person.id)
            final_confidence = compute_enrichment_confidence(
                person,
                linkedin_url=linkedin_url_final,
            )
            item.strategies_attempted = attempted
            item.strategies_remaining = remaining
            await self._queue.mark_complete(item, confidence=final_confidence.score)
            await self._db.commit()
            logger.info(
                "Enriched person %s confidence=%.2f strategies=%s",
                person.id,
                final_confidence.score,
                attempted,
            )
        except Exception as exc:
            logger.exception("Enrichment worker failed for person %s", person.id)
            await self._db.rollback()
            refreshed: EnrichmentQueueItem | None = await self._db.get(
                EnrichmentQueueItem, item.id
            )
            if refreshed is not None:
                refreshed.strategies_attempted = attempted
                refreshed.strategies_remaining = remaining
                await self._queue.mark_deferred(refreshed, error=str(exc))
            await self._db.commit()

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

    async def _load_person_linkedin_url(self, person_id: uuid.UUID) -> str | None:
        result = await self._db.execute(
            select(PersonAlias.value).where(
                PersonAlias.person_id == person_id,
                PersonAlias.kind == "linkedin_url",
            ).limit(1)
        )
        return result.scalar_one_or_none()
