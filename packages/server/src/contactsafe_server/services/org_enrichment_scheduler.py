"""Background scheduling for global org enrichment."""

from __future__ import annotations

import asyncio
import logging
import threading
import uuid

from contactsafe_server.db.connection import get_session_factory

logger: logging.Logger = logging.getLogger(__name__)

_global_enrichment_lock: threading.Lock = threading.Lock()
_global_enrichment_active: bool = False
_periodic_task: asyncio.Task[None] | None = None


def is_global_enrichment_active() -> bool:
    with _global_enrichment_lock:
        return _global_enrichment_active


def _set_global_enrichment_active(active: bool) -> None:
    global _global_enrichment_active
    with _global_enrichment_lock:
        _global_enrichment_active = active


async def _run_one_global_enrichment_scan() -> None:
    from contactsafe_server.config import get_settings
    from contactsafe_server.queue import enqueue_background_job

    if get_settings().use_arq_worker:
        await enqueue_background_job("global_org_enrichment_scan")
        return

    from contactsafe_server.deps import build_app_context
    from contactsafe_server.services.org_enrichment_service import OrgEnrichmentService

    ctx = build_app_context()
    factory = get_session_factory(ctx.settings)

    _set_global_enrichment_active(True)
    try:
        async with factory() as db:
            service = OrgEnrichmentService(db, ctx.settings)
            org_ids: list[uuid.UUID] = await service.collect_all_enrichable_org_ids()

        for org_id in org_ids:
            async with factory() as db:
                service = OrgEnrichmentService(db, ctx.settings)
                if await service.was_recently_enriched(org_id):
                    continue
                enrich_result = await service.enrich_org_global(org_id)
                if enrich_result.enriched:
                    logger.info(
                        "Globally enriched org %s (%d fields updated)",
                        org_id,
                        enrich_result.fields_updated,
                    )
                elif enrich_result.error is not None:
                    logger.warning(
                        "Global org enrichment failed for %s: %s",
                        org_id,
                        enrich_result.error,
                    )
            await asyncio.sleep(0.5)
    except Exception:
        logger.exception("Global org enrichment scan failed")
    finally:
        _set_global_enrichment_active(False)


async def _global_enrichment_loop() -> None:
    from contactsafe_server.deps import build_app_context

    ctx = build_app_context()
    poll_interval_seconds: int = (
        ctx.settings.org_enrichment_scan_poll_interval_minutes * 60
    )

    while True:
        try:
            await _run_one_global_enrichment_scan()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Global org enrichment loop error")
        await asyncio.sleep(poll_interval_seconds)


def start_global_org_enrichment_scanner() -> None:
    from contactsafe_server.config import get_settings

    if get_settings().use_arq_worker:
        return
    global _periodic_task
    if _periodic_task is not None and not _periodic_task.done():
        return
    _periodic_task = asyncio.create_task(
        _global_enrichment_loop(),
        name="global-org-enrichment-scan",
    )


async def schedule_initial_org_enrichment_delay() -> None:
    """Run first global org enrichment scan after a short delay."""
    from contactsafe_server.config import get_settings

    if get_settings().use_arq_worker:
        return
    await asyncio.sleep(60)
    start_global_org_enrichment_scanner()
