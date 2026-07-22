"""arq worker entrypoint for background org enrichment, job discovery, and scoring."""

from __future__ import annotations

import logging
import time
import uuid
from datetime import UTC, datetime
from typing import Any

from arq import cron
from arq.connections import RedisSettings

from contactsafe_server.config import Settings, get_settings
from contactsafe_server.db.connection import get_session_factory, init_db, shutdown_db
from contactsafe_server.db.models import OrgEnrichmentRun
from contactsafe_server.graph_event_publishers import publish_org_enrichment_failed
from contactsafe_server.job_event_publishers import publish_scan_progress_for_users
from contactsafe_server.queue import redis_settings_from_config
from contactsafe_server.redis_state import (
    record_worker_run,
    set_worker_flag,
)

logger: logging.Logger = logging.getLogger(__name__)


async def startup(ctx: dict[str, Any]) -> None:
    settings: Settings = get_settings()
    await init_db(settings)
    ctx["settings"] = settings
    ctx["session_factory"] = get_session_factory(settings)
    logger.info("arq worker started")


async def shutdown(ctx: dict[str, Any]) -> None:
    await shutdown_db()
    from contactsafe_server.queue import close_arq_pool
    from contactsafe_server.redis_state import close_redis_client

    await close_arq_pool()
    await close_redis_client()
    logger.info("arq worker stopped")


async def score_jobs_for_user(
    ctx: dict[str, Any],
    user_id: str,
    *,
    reclassify: bool = False,
) -> int:
    settings: Settings = ctx["settings"]
    factory = ctx["session_factory"]
    uid: uuid.UUID = uuid.UUID(user_id)
    started: float = time.monotonic()

    async with factory() as db:
        from contactsafe_server.services.job_relevance_service import JobRelevanceService

        svc = JobRelevanceService(db, settings)
        if reclassify:
            count: int = await svc.reclassify_all(uid)
        else:
            count = await svc.classify_jobs_for_user(uid)

    duration_ms: int = int((time.monotonic() - started) * 1000)
    await record_worker_run("job_scoring", duration_ms=duration_ms, settings=settings)
    return count


async def backfill_job_attributes(
    ctx: dict[str, Any],
    *,
    offset: int = 0,
    limit: int = 200,
) -> dict[str, int]:
    """Apply mechanical seniority + geocode to a page of org_jobs."""
    settings: Settings = ctx["settings"]
    factory = ctx["session_factory"]
    started: float = time.monotonic()

    from sqlalchemy import select

    from contactsafe_server.db.models import OrgJob
    from contactsafe_server.services.job_attributes import apply_job_attributes

    async with factory() as db:
        jobs: list[OrgJob] = list(
            (
                await db.execute(
                    select(OrgJob)
                    .order_by(OrgJob.created_at.desc())
                    .offset(max(0, offset))
                    .limit(max(1, limit)),
                )
            ).scalars().all(),
        )
        for job in jobs:
            apply_job_attributes(job)
        await db.commit()

    duration_ms: int = int((time.monotonic() - started) * 1000)
    await record_worker_run(
        "backfill_job_attributes",
        duration_ms=duration_ms,
        settings=settings,
    )
    return {"processed": len(jobs), "offset": offset, "limit": limit}


async def scrape_org_jobs(
    ctx: dict[str, Any],
    org_id: str,
    *,
    force: bool = False,
    trigger_user_id: str | None = None,
) -> dict[str, object]:
    settings: Settings = ctx["settings"]
    factory = ctx["session_factory"]
    redis = ctx["redis"]
    oid: uuid.UUID = uuid.UUID(org_id)
    started: float = time.monotonic()

    from contactsafe_server.services.job_discovery_service import JobDiscoveryService

    async with factory() as db:
        service = JobDiscoveryService(db, settings)
        if not force and await service.was_recently_scraped(oid):
            return {"skipped": True, "reason": "cooldown"}

        from contactsafe_server.db.models import Org

        org: Org | None = await db.get(Org, oid)
        org_name: str | None = org.canonical_name if org is not None else None
        user_ids: list[uuid.UUID] = await service.users_monitoring_org(oid)
        if user_ids:
            publish_scan_progress_for_users(
                user_ids,
                scanning_active=True,
                current_org_name=org_name,
            )

        result = await service.scrape_org_global(oid, force=force)

        if result.scanned and user_ids:
            publish_scan_progress_for_users(
                user_ids,
                scanning_active=True,
                current_org_name=org_name,
            )

        if result.new_jobs > 0:
            if trigger_user_id is not None:
                await redis.enqueue_job(
                    "score_jobs_for_user",
                    trigger_user_id,
                    _job_id=f"score-user-{trigger_user_id}",
                )
            else:
                for uid in user_ids:
                    await redis.enqueue_job(
                        "score_jobs_for_user",
                        str(uid),
                        _job_id=f"score-user-{uid}",
                    )

    duration_ms: int = int((time.monotonic() - started) * 1000)
    await record_worker_run("job_discovery", duration_ms=duration_ms, settings=settings)
    return {
        "jobs_found": result.jobs_found,
        "new_jobs": result.new_jobs,
        "scanned": result.scanned,
        "source": result.source,
        "error": result.error,
    }


async def enrich_org(ctx: dict[str, Any], org_id: str) -> dict[str, object]:
    settings: Settings = ctx["settings"]
    factory = ctx["session_factory"]
    oid: uuid.UUID = uuid.UUID(org_id)
    started: float = time.monotonic()

    from contactsafe_server.services.org_enrichment_service import OrgEnrichmentService

    async with factory() as db:
        service = OrgEnrichmentService(db, settings)
        if await service.was_recently_enriched(oid):
            return {"skipped": True, "reason": "cooldown"}
        enrich_result = await service.enrich_org_global(oid)

    duration_ms: int = int((time.monotonic() - started) * 1000)
    await record_worker_run("org_enrichment", duration_ms=duration_ms, settings=settings)
    return {
        "enriched": enrich_result.enriched,
        "fields_updated": enrich_result.fields_updated,
        "error": enrich_result.error,
    }


async def enrich_user_orgs(ctx: dict[str, Any], user_id: str, run_id: str) -> None:
    settings: Settings = ctx["settings"]
    factory = ctx["session_factory"]
    uid: uuid.UUID = uuid.UUID(user_id)
    rid: uuid.UUID = uuid.UUID(run_id)

    from contactsafe_server.services.org_enrichment_service import OrgEnrichmentService

    try:
        async with factory() as db:
            service = OrgEnrichmentService(db, settings)
            await service.enrich_orgs(uid, rid)
    except Exception as exc:
        logger.exception("User org enrichment failed for user %s", user_id)
        try:
            async with factory() as db:
                run: OrgEnrichmentRun | None = await db.get(OrgEnrichmentRun, rid)
                if run is not None:
                    run.state = "failed"
                    run.error = str(exc)[:500]
                    run.completed_at = datetime.now(tz=UTC)
                    run.progress_message = None
                    await db.commit()
                    publish_org_enrichment_failed(
                        uid,
                        orgs_enriched=run.orgs_enriched,
                        orgs_total=run.orgs_total,
                        error=run.error,
                    )
        except Exception:
            logger.exception("Failed to mark org enrichment run %s as failed", run_id)


async def global_job_scan(ctx: dict[str, Any]) -> None:
    settings: Settings = ctx["settings"]
    factory = ctx["session_factory"]
    redis = ctx["redis"]
    started: float = time.monotonic()

    from contactsafe_server.services.job_discovery_service import JobDiscoveryService

    await set_worker_flag("global_job_scan", True, settings=settings)
    monitoring_user_ids: list[uuid.UUID] = []
    try:
        async with factory() as db:
            service = JobDiscoveryService(db, settings)
            org_ids: list[uuid.UUID] = await service.collect_orgs_needing_scrape()
            monitoring_user_ids = await service.collect_all_monitoring_user_ids()

        if monitoring_user_ids:
            publish_scan_progress_for_users(
                monitoring_user_ids,
                scanning_active=True,
            )

        for org_id in org_ids:
            await redis.enqueue_job(
                "scrape_org_jobs",
                str(org_id),
                _job_id=f"scrape-org-{org_id}",
            )
    except Exception:
        logger.exception("Global job scan enqueue failed")
    finally:
        await set_worker_flag("global_job_scan", False, settings=settings)
        if monitoring_user_ids:
            publish_scan_progress_for_users(
                monitoring_user_ids,
                scanning_active=False,
            )
        duration_ms: int = int((time.monotonic() - started) * 1000)
        await record_worker_run("job_discovery_scan", duration_ms=duration_ms, settings=settings)


async def send_job_digests(ctx: dict[str, Any]) -> None:
    settings: Settings = ctx["settings"]
    factory = ctx["session_factory"]
    redis = ctx["redis"]
    started: float = time.monotonic()

    from contactsafe_server.deps import build_jwt_service
    from contactsafe_server.services.job_digest_service import JobDigestService

    try:
        async with factory() as db:
            service = JobDigestService(
                db,
                settings,
                jwt_service=build_jwt_service(settings),
            )
            user_ids: list[uuid.UUID] = await service.collect_users_due()

        for user_id in user_ids:
            await redis.enqueue_job(
                "send_job_digest_for_user",
                str(user_id),
                _job_id=f"digest-user-{user_id}",
            )
    except Exception:
        logger.exception("Job digest enqueue failed")
    finally:
        duration_ms: int = int((time.monotonic() - started) * 1000)
        await record_worker_run("job_digest_scan", duration_ms=duration_ms, settings=settings)


async def send_job_digest_for_user(ctx: dict[str, Any], user_id: str) -> dict[str, object]:
    settings: Settings = ctx["settings"]
    factory = ctx["session_factory"]
    uid: uuid.UUID = uuid.UUID(user_id)
    started: float = time.monotonic()

    from contactsafe_server.deps import build_jwt_service
    from contactsafe_server.services.job_digest_service import JobDigestService

    async with factory() as db:
        service = JobDigestService(
            db,
            settings,
            jwt_service=build_jwt_service(settings),
        )
        result = await service.send_digest_for_user(uid)

    duration_ms: int = int((time.monotonic() - started) * 1000)
    await record_worker_run("job_digest_send", duration_ms=duration_ms, settings=settings)
    return {
        "sent": result.sent,
        "job_count": result.job_count,
        "message": result.message,
    }


async def global_org_enrichment_scan(ctx: dict[str, Any]) -> None:
    settings: Settings = ctx["settings"]
    factory = ctx["session_factory"]
    redis = ctx["redis"]
    started: float = time.monotonic()

    from contactsafe_server.services.org_enrichment_service import OrgEnrichmentService

    await set_worker_flag("global_org_enrichment", True, settings=settings)
    try:
        async with factory() as db:
            service = OrgEnrichmentService(db, settings)
            org_ids: list[uuid.UUID] = await service.collect_orgs_needing_enrichment()

        for org_id in org_ids:
            await redis.enqueue_job(
                "enrich_org",
                str(org_id),
                _job_id=f"enrich-org-{org_id}",
            )
    except Exception:
        logger.exception("Global org enrichment enqueue failed")
    finally:
        await set_worker_flag("global_org_enrichment", False, settings=settings)
        duration_ms: int = int((time.monotonic() - started) * 1000)
        await record_worker_run("org_enrichment_scan", duration_ms=duration_ms, settings=settings)


def _job_scan_cron_minutes(settings: Settings) -> set[int]:
    interval: int = max(1, settings.job_scan_poll_interval_minutes)
    return set(range(0, 60, interval))


def _org_enrichment_cron_minutes(settings: Settings) -> set[int]:
    interval: int = max(1, settings.org_enrichment_scan_poll_interval_minutes)
    return set(range(2, 60, interval))


class WorkerSettings:
    functions = [
        score_jobs_for_user,
        backfill_job_attributes,
        scrape_org_jobs,
        enrich_org,
        enrich_user_orgs,
        global_job_scan,
        send_job_digests,
        send_job_digest_for_user,
        global_org_enrichment_scan,
    ]

    redis_settings: RedisSettings = redis_settings_from_config()
    on_startup = startup
    on_shutdown = shutdown
    max_jobs: int = get_settings().arq_max_jobs
    job_timeout: int = get_settings().arq_job_timeout_seconds
    health_check_interval: int = 60
    cron_jobs = [
        cron(
            global_job_scan,
            minute=_job_scan_cron_minutes(get_settings()),
            run_at_startup=True,
            unique=True,
        ),
        cron(
            send_job_digests,
            minute={15},
            unique=True,
        ),
        cron(
            global_org_enrichment_scan,
            minute=_org_enrichment_cron_minutes(get_settings()),
            run_at_startup=True,
            unique=True,
        ),
    ]


def run() -> None:
    from arq import run_worker

    run_worker(WorkerSettings)
