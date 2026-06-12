"""Background scheduling for global job discovery."""

from __future__ import annotations

import asyncio
import logging
import threading
import uuid

from contactsafe_server.db.connection import get_session_factory

logger: logging.Logger = logging.getLogger(__name__)

_global_scan_lock: threading.Lock = threading.Lock()
_global_scan_active: bool = False
_periodic_task: asyncio.Task[None] | None = None


def is_global_scan_active() -> bool:
    with _global_scan_lock:
        return _global_scan_active


def _set_global_scan_active(active: bool) -> None:
    global _global_scan_active
    with _global_scan_lock:
        _global_scan_active = active


async def _run_one_global_scan() -> None:
    from contactsafe_server.deps import build_app_context
    from contactsafe_server.job_event_publishers import publish_scan_progress_for_users
    from contactsafe_server.services.job_discovery_service import JobDiscoveryService

    ctx = build_app_context()
    factory = get_session_factory(ctx.settings)

    _set_global_scan_active(True)
    monitoring_user_ids: list[uuid.UUID] = []
    try:
        async with factory() as db:
            service = JobDiscoveryService(db, ctx.settings)
            org_ids: list[uuid.UUID] = await service.collect_all_monitored_org_ids()
            monitoring_user_ids = await service.collect_all_monitoring_user_ids()

        if monitoring_user_ids:
            publish_scan_progress_for_users(
                monitoring_user_ids,
                scanning_active=True,
            )

        for org_id in org_ids:
            async with factory() as db:
                service = JobDiscoveryService(db, ctx.settings)
                if await service.was_recently_scraped(org_id):
                    continue
                scrape_result = await service.scrape_org_global(org_id)
                if scrape_result.scanned:
                    user_ids: list[uuid.UUID] = await service.users_monitoring_org(org_id)
                    if user_ids:
                        publish_scan_progress_for_users(
                            user_ids,
                            scanning_active=True,
                        )
                    await service.classify_for_all_monitoring_users(org_id)
    except Exception:
        logger.exception("Global job scan failed")
    finally:
        _set_global_scan_active(False)
        if monitoring_user_ids:
            publish_scan_progress_for_users(
                monitoring_user_ids,
                scanning_active=False,
            )


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
