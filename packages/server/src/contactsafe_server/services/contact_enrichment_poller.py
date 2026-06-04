"""Background poller for per-contact enrichment queue items."""

from __future__ import annotations

import asyncio
import logging
import threading

from contactsafe_server.config import Settings, get_settings
from contactsafe_server.db.connection import get_session_factory
from contactsafe_server.db.models import EnrichmentQueueItem
from contactsafe_server.services.contact_enrichment_worker import ContactEnrichmentWorker
from contactsafe_server.services.enrichment_queue_service import EnrichmentQueueService

logger: logging.Logger = logging.getLogger(__name__)

_poller_task: asyncio.Task[None] | None = None
_active_worker_count: int = 0
_worker_lock: threading.Lock = threading.Lock()


def start_enrichment_poller(settings: Settings | None = None) -> None:
    global _poller_task
    if _poller_task is not None and not _poller_task.done():
        return
    resolved_settings: Settings = settings or get_settings()
    _poller_task = asyncio.create_task(
        _poll_loop(resolved_settings),
        name="enrichment-poller",
    )


def stop_enrichment_poller() -> None:
    global _poller_task
    if _poller_task is None:
        return
    _poller_task.cancel()
    _poller_task = None


def active_worker_count() -> int:
    with _worker_lock:
        return _active_worker_count


async def _poll_loop(settings: Settings) -> None:
    factory = get_session_factory(settings)
    interval: float = settings.enrichment_queue_poll_interval_seconds
    concurrency: int = settings.enrichment_worker_concurrency

    logger.info(
        "Enrichment poller started (concurrency=%s, interval=%ss)",
        concurrency,
        interval,
    )

    try:
        while True:
            workers_to_start: int = concurrency - active_worker_count()
            for _ in range(max(0, workers_to_start)):
                asyncio.create_task(
                    _run_one_worker(factory, settings),
                    name="enrichment-worker",
                )
            await asyncio.sleep(interval)
    except asyncio.CancelledError:
        logger.info("Enrichment poller stopped")
        raise


async def _run_one_worker(factory, settings: Settings) -> None:  # noqa: ANN001
    global _active_worker_count
    with _worker_lock:
        _active_worker_count += 1

    try:
        async with factory() as db:
            queue = EnrichmentQueueService(db, settings)
            item: EnrichmentQueueItem | None = await queue.claim_next_item()
            if item is None:
                await db.rollback()
                return

            await db.commit()

        async with factory() as db:
            worker = ContactEnrichmentWorker(db, settings)
            refreshed: EnrichmentQueueItem | None = await db.get(
                EnrichmentQueueItem, item.id
            )
            if refreshed is None:
                await db.rollback()
                return
            await worker.enrich_one(refreshed)
    except Exception:
        logger.exception("Enrichment worker task failed")
    finally:
        with _worker_lock:
            _active_worker_count -= 1
