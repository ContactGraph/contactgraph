import asyncio
import logging
import threading
import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from contactsafe_core.enums import EnrichmentRunState
from contactsafe_server.db.connection import get_session_factory
from contactsafe_server.db.models import EnrichmentRun
from contactsafe_server.services.enrichment_queue_service import EnrichmentQueueService

logger = logging.getLogger(__name__)

_active_enrichment_user_ids: set[uuid.UUID] = set()
_scheduling_lock: threading.Lock = threading.Lock()


def schedule_enrichment(user_id: uuid.UUID, run_id: uuid.UUID) -> bool:
    with _scheduling_lock:
        if user_id in _active_enrichment_user_ids:
            return False
        _active_enrichment_user_ids.add(user_id)
    asyncio.create_task(
        _run_enrichment_task(user_id, run_id),
        name=f"enrichment-{user_id}",
    )
    return True


def release_enrichment_lock(user_id: uuid.UUID) -> None:
    with _scheduling_lock:
        _active_enrichment_user_ids.discard(user_id)


def is_enrichment_running(user_id: uuid.UUID) -> bool:
    with _scheduling_lock:
        return user_id in _active_enrichment_user_ids


async def _mark_enrichment_failed(
    db: AsyncSession,
    run_id: uuid.UUID,
    error: str,
) -> None:
    run: EnrichmentRun | None = await db.get(EnrichmentRun, run_id)
    if run is None:
        return
    run.state = EnrichmentRunState.FAILED.value
    run.error = error[:500]
    run.completed_at = datetime.now(tz=UTC)
    await db.commit()


async def _run_enrichment_task(user_id: uuid.UUID, run_id: uuid.UUID) -> None:
    from contactsafe_server.deps import build_app_context

    ctx = build_app_context()
    factory = get_session_factory(ctx.settings)
    try:
        async with factory() as db:
            run: EnrichmentRun | None = await db.get(EnrichmentRun, run_id)
            if run is None:
                logger.warning("Enrichment run %s not found", run_id)
                return

            run.state = EnrichmentRunState.RUNNING.value
            run.started_at = datetime.now(tz=UTC)
            run.error = None
            run.progress_message = "Queuing contacts for enrichment…"
            await db.commit()

            queue_service = EnrichmentQueueService(db, ctx.settings)
            try:
                enqueued: int = await queue_service.enqueue_user_contacts(
                    user_id=user_id,
                    enrichment_run_id=run_id,
                )
                run.contacts_total = enqueued
                run.progress_message = f"Enriching {enqueued} contacts in the background…"
                if enqueued == 0:
                    run.state = EnrichmentRunState.COMPLETE.value
                    run.completed_at = datetime.now(tz=UTC)
                    run.progress_message = None
                await db.commit()
                logger.info(
                    "Enqueued %s contacts for enrichment run %s (user %s)",
                    enqueued,
                    run_id,
                    user_id,
                )
            except Exception as exc:
                logger.exception("Failed to enqueue enrichment for user %s", user_id)
                await db.rollback()
                run_refresh: EnrichmentRun | None = await db.get(EnrichmentRun, run_id)
                if run_refresh is not None:
                    run_refresh.state = EnrichmentRunState.FAILED.value
                    error_msg: str = str(exc)[:500]
                    run_refresh.error = error_msg
                    run_refresh.completed_at = datetime.now(tz=UTC)
                    run_refresh.progress_message = None
                    await db.commit()
    except Exception as exc:
        logger.exception("Background enrichment task failed for user %s", user_id)
        try:
            async with factory() as db:
                await _mark_enrichment_failed(db, run_id, str(exc))
        except Exception:
            logger.exception("Failed to mark enrichment run %s as failed", run_id)
    finally:
        release_enrichment_lock(user_id)
