"""Background scheduling for global job discovery."""

from __future__ import annotations

import asyncio
import logging
import threading
import uuid

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from contactsafe_server.db.connection import get_session_factory

logger: logging.Logger = logging.getLogger(__name__)

_global_scan_lock: threading.Lock = threading.Lock()
_global_scan_active: bool = False
_periodic_task: asyncio.Task[None] | None = None

_JOB_SCRAPE_LOCK_NAMESPACE: int = 0x635F_0002


def is_global_scan_active() -> bool:
    with _global_scan_lock:
        return _global_scan_active


def _set_global_scan_active(active: bool) -> None:
    global _global_scan_active
    with _global_scan_lock:
        _global_scan_active = active


async def _try_claim_org_scrape(db: AsyncSession, org_id: uuid.UUID) -> bool:
    """Try to acquire a transaction-scoped advisory lock for scraping this org.

    Returns True if the lock was acquired (no other instance is scraping it).
    The lock is automatically released when the transaction/session closes.
    """
    key2: int = org_id.int % (2**31)
    result = await db.execute(
        text("SELECT pg_try_advisory_xact_lock(:ns, :key)"),
        {"ns": _JOB_SCRAPE_LOCK_NAMESPACE, "key": key2},
    )
    return bool(result.scalar_one())


async def _run_one_global_scan() -> None:
    from contactsafe_server.deps import build_app_context
    from contactsafe_server.services.job_discovery_service import JobDiscoveryService

    ctx = build_app_context()
    factory = get_session_factory(ctx.settings)

    _set_global_scan_active(True)
    try:
        async with factory() as db:
            service = JobDiscoveryService(db, ctx.settings)
            org_ids: list[uuid.UUID] = await service.collect_all_monitored_org_ids()

        for org_id in org_ids:
            async with factory() as db:
                service = JobDiscoveryService(db, ctx.settings)
                if await service.was_recently_scraped(org_id):
                    continue
                if not await _try_claim_org_scrape(db, org_id):
                    logger.debug("Skipping org %s — another instance is scraping it", org_id)
                    continue
                scrape_result = await service.scrape_org_global(org_id)
                if scrape_result.scanned:
                    await service.classify_for_all_monitoring_users(org_id)
    except Exception:
        logger.exception("Global job scan failed")
    finally:
        _set_global_scan_active(False)


async def _global_scan_loop() -> None:
    from contactsafe_server.deps import build_app_context

    ctx = build_app_context()
    poll_interval_seconds: int = ctx.settings.job_scan_poll_interval_minutes * 60

    while True:
        try:
            await _run_one_global_scan()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Global scan loop error")
        await asyncio.sleep(poll_interval_seconds)


def start_global_job_scanner() -> None:
    global _periodic_task
    if _periodic_task is not None and not _periodic_task.done():
        return
    _periodic_task = asyncio.create_task(
        _global_scan_loop(),
        name="global-job-scan",
    )


async def schedule_initial_job_discovery_delay() -> None:
    """Run first global scan after a short delay so the server can start."""
    await asyncio.sleep(60)
    start_global_job_scanner()
