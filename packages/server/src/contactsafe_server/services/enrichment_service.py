import logging
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from contactsafe_core.enums import EnrichmentRunState, SourceType, SyncState
from contactsafe_core.schemas import EnrichmentStatusResult, StartEnrichmentResult
from contactsafe_server.db.models import EnrichmentRun, Source, UserPersonObservation
from contactsafe_server.services.enrichment_scheduler import (
    is_enrichment_running,
    schedule_enrichment,
)

logger: logging.Logger = logging.getLogger(__name__)

_SYNCABLE_IMPORT_STATES: frozenset[str] = frozenset({
    SyncState.PARTIAL.value,
    SyncState.COMPLETE.value,
})


class EnrichmentService:
    def __init__(self, db: AsyncSession) -> None:
        self._db: AsyncSession = db

    async def start_enrichment(self, user_id: uuid.UUID) -> StartEnrichmentResult:
        if not await self._user_has_imported_contacts(user_id):
            return StartEnrichmentResult(
                run_id=None,
                scheduled=False,
                state=EnrichmentRunState.PENDING,
                message=(
                    "Import at least one data source before enriching. "
                    "Connect Gmail or upload contacts first."
                ),
            )

        latest: EnrichmentRun | None = await self._latest_run(user_id)
        if latest is not None:
            await self._recover_orphaned_run(latest)
            await self._db.refresh(latest)

        if latest is not None and latest.state == EnrichmentRunState.RUNNING.value:
            if is_enrichment_running(user_id):
                return StartEnrichmentResult(
                    run_id=latest.id,
                    scheduled=False,
                    state=EnrichmentRunState.RUNNING,
                    message="Enrichment is already running. Poll get_enrichment_status.",
                )
            await self._recover_orphaned_run(latest)
            await self._db.refresh(latest)

        if is_enrichment_running(user_id):
            return StartEnrichmentResult(
                run_id=latest.id if latest is not None else None,
                scheduled=False,
                state=EnrichmentRunState.RUNNING,
                message="Enrichment is already running. Poll get_enrichment_status.",
            )

        run = EnrichmentRun(
            user_id=user_id,
            state=EnrichmentRunState.PENDING.value,
        )
        self._db.add(run)
        await self._db.flush()

        if not schedule_enrichment(user_id, run.id):
            run.state = EnrichmentRunState.FAILED.value
            run.error = "Could not schedule enrichment task"
            run.completed_at = datetime.now(tz=UTC)
            await self._db.flush()
            return StartEnrichmentResult(
                run_id=run.id,
                scheduled=False,
                state=EnrichmentRunState.FAILED,
                message="Enrichment is already running for this user.",
            )

        return StartEnrichmentResult(
            run_id=run.id,
            scheduled=True,
            state=EnrichmentRunState.RUNNING,
            message=(
                "Enrichment started in the background. "
                "Poll get_enrichment_status until state is complete."
            ),
        )

    async def get_enrichment_status(self, user_id: uuid.UUID) -> EnrichmentStatusResult:
        run: EnrichmentRun | None = await self._latest_run(user_id)
        if run is None:
            return EnrichmentStatusResult(
                run_id=None,
                state=EnrichmentRunState.PENDING,
                contacts_total=0,
                contacts_enriched=0,
                started_at=None,
                completed_at=None,
                error=None,
                message="No enrichment has been run yet. Call start_enrichment to begin.",
            )

        await self._recover_orphaned_run(run)
        await self._db.refresh(run)

        return EnrichmentStatusResult(
            run_id=run.id,
            state=EnrichmentRunState(run.state),
            contacts_total=run.contacts_total,
            contacts_enriched=run.contacts_enriched,
            started_at=run.started_at,
            completed_at=run.completed_at,
            progress_message=run.progress_message,
            error=run.error,
            message=self._status_message(run),
        )

    async def _user_has_imported_contacts(self, user_id: uuid.UUID) -> bool:
        obs_count = await self._db.execute(
            select(UserPersonObservation.person_id)
            .where(UserPersonObservation.user_id == user_id)
            .limit(1)
        )
        if obs_count.first() is not None:
            return True

        result = await self._db.execute(
            select(Source).where(
                Source.user_id == user_id,
                Source.source_type != SourceType.GOOGLE_CONTACTS.value,
                Source.sync_state.in_(_SYNCABLE_IMPORT_STATES),
            )
        )
        return result.first() is not None

    async def _latest_run(self, user_id: uuid.UUID) -> EnrichmentRun | None:
        result = await self._db.execute(
            select(EnrichmentRun)
            .where(EnrichmentRun.user_id == user_id)
            .order_by(EnrichmentRun.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def _recover_orphaned_run(self, run: EnrichmentRun) -> None:
        if run.state != EnrichmentRunState.RUNNING.value:
            return
        if is_enrichment_running(run.user_id):
            return
        run.state = EnrichmentRunState.FAILED.value
        run.error = (
            run.error or "Enrichment was interrupted before it finished. Try again."
        )[:500]
        run.completed_at = datetime.now(tz=UTC)
        logger.warning("Recovered orphaned enrichment run %s", run.id)

    @staticmethod
    def _status_message(run: EnrichmentRun) -> str:
        state = EnrichmentRunState(run.state)
        if state == EnrichmentRunState.RUNNING:
            if run.contacts_total > 0:
                return (
                    f"Enriching contacts ({run.contacts_enriched}/{run.contacts_total})…"
                )
            return "Enrichment is running…"
        if state == EnrichmentRunState.COMPLETE:
            return f"Enrichment complete ({run.contacts_enriched} contacts enriched)."
        if state == EnrichmentRunState.FAILED:
            error: str = run.error or "Enrichment failed."
            if "sqlalchemy" in error.lower() or "asyncpg" in error.lower():
                return "Enrichment failed due to a server error. Try again."
            return error
        return "Enrichment is pending."
