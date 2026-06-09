"""Background scheduling for job discovery runs."""

from __future__ import annotations

import asyncio
import logging
import threading
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from contactsafe_server.db.connection import get_session_factory
from contactsafe_server.db.models import JobDiscoveryRun, User

logger: logging.Logger = logging.getLogger(__name__)

_active_job_discovery_user_ids: set[uuid.UUID] = set()
_scheduling_lock: threading.Lock = threading.Lock()
_periodic_task: asyncio.Task[None] | None = None

_DAILY_INTERVAL_SECONDS: int = 24 * 60 * 60


def schedule_job_discovery(user_id: uuid.UUID, run_id: uuid.UUID) -> bool:
    with _scheduling_lock:
        if user_id in _active_job_discovery_user_ids:
            return False
        _active_job_discovery_user_ids.add(user_id)
    asyncio.create_task(
        _run_job_discovery_task(user_id, run_id),
        name=f"job-discovery-{user_id}",
    )
    return True


def is_job_discovery_running(user_id: uuid.UUID) -> bool:
    with _scheduling_lock:
        return user_id in _active_job_discovery_user_ids


def release_job_discovery_lock(user_id: uuid.UUID) -> None:
    with _scheduling_lock:
        _active_job_discovery_user_ids.discard(user_id)


async def _run_job_discovery_task(user_id: uuid.UUID, run_id: uuid.UUID) -> None:
    from contactsafe_server.deps import build_app_context

    ctx = build_app_context()
    factory = get_session_factory(ctx.settings)
    try:
        async with factory() as db:
            from contactsafe_server.services.job_discovery_service import JobDiscoveryService

            service = JobDiscoveryService(db, ctx.settings)
            await service.run_discovery(user_id, run_id)
    except Exception as exc:
        logger.exception("Background job discovery failed for user %s", user_id)
        try:
            async with factory() as db:
                run: JobDiscoveryRun | None = await db.get(JobDiscoveryRun, run_id)
                if run is not None:
                    run.state = "failed"
                    run.error = str(exc)[:500]
                    run.completed_at = datetime.now(tz=UTC)
                    run.progress_message = None
                    await db.commit()
        except Exception:
            logger.exception("Failed to mark job discovery run %s as failed", run_id)
    finally:
        release_job_discovery_lock(user_id)


def start_periodic_job_discovery() -> None:
    global _periodic_task
    if _periodic_task is not None and not _periodic_task.done():
        return
    _periodic_task = asyncio.create_task(
        _periodic_job_discovery_loop(),
        name="job-discovery-periodic",
    )


async def _periodic_job_discovery_loop() -> None:
    from contactsafe_server.deps import build_app_context

    while True:
        try:
            await asyncio.sleep(_DAILY_INTERVAL_SECONDS)
            ctx = build_app_context()
            factory = get_session_factory(ctx.settings)
            async with factory() as db:
                result = await db.execute(
                    select(User.id).where(
                        User.job_monitor_enabled.is_(True),
                        User.job_monitor_list_id.is_not(None),
                    ),
                )
                user_ids: list[uuid.UUID] = list(result.scalars().all())
                for user_id in user_ids:
                    async with factory() as db:
                        from contactsafe_server.services.job_discovery_service import JobDiscoveryService

                        service = JobDiscoveryService(db, ctx.settings)
                        scheduled: bool = await service.maybe_start_scheduled_discovery(user_id)
                    if scheduled:
                        logger.info("Scheduled daily job discovery for user %s", user_id)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Periodic job discovery loop error")


async def schedule_initial_job_discovery_delay() -> None:
    """Run first periodic check after a short delay so the server can start."""
    await asyncio.sleep(60)
    start_periodic_job_discovery()
