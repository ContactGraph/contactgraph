"""Aggregate worker and pipeline status for the admin dashboard."""

from __future__ import annotations

import pickletools
from collections import defaultdict
from datetime import UTC, datetime, timedelta

from contactsafe_core.contact_schemas import (
    AdminUserItem,
    AdminUsersResult,
    PipelineStatus,
    WorkerStatusResult,
)
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from contactsafe_server.config import Settings
from contactsafe_server.db.models import (
    JobScrapeRun,
    OrgEnrichmentScrapeRun,
    OrgJob,
    OrgListMembership,
    Person,
    RefreshToken,
    Source,
    User,
    UserJobRelevance,
    UserOrgObservation,
    UserPersonObservation,
)
from contactsafe_server.redis_state import get_redis_client, get_worker_last_run

_PIPELINE_FUNCTIONS: dict[str, set[str]] = {
    "org_enrichment": {"enrich_org", "enrich_user_orgs", "global_org_enrichment_scan"},
    "job_discovery": {"scrape_org_jobs", "global_job_scan"},
    "job_scoring": {"score_jobs_for_user"},
}


async def _count_arq_jobs() -> tuple[dict[str, int], dict[str, int], bool]:
    """Return queued counts, active counts, and redis connectivity per pipeline."""
    from contactsafe_server.config import get_settings

    queued: dict[str, int] = defaultdict(int)
    active: dict[str, int] = defaultdict(int)
    try:
        import redis.asyncio as aioredis

        client = aioredis.from_url(get_settings().redis_url, decode_responses=False)
        await client.ping()
    except Exception:
        return queued, active, False

    try:
        job_ids: list[bytes] = await client.zrange("arq:queue", 0, -1)
        for job_id_raw in job_ids:
            job_id: str = (
                job_id_raw.decode()
                if isinstance(job_id_raw, bytes)
                else str(job_id_raw)
            )
            raw: bytes | None = await client.get(f"arq:job:{job_id}")
            if raw is None:
                continue
            function_name: str | None = _function_name_from_job(raw)
            if function_name is None:
                continue
            pipeline: str | None = _pipeline_for_function(function_name)
            if pipeline is not None:
                queued[pipeline] += 1

        async for key in client.scan_iter(match="arq:in-progress:*"):
            raw_in_progress: bytes | None = await client.get(key)
            if raw_in_progress is None:
                continue
            function_name = _function_name_from_job(raw_in_progress)
            if function_name is None:
                continue
            pipeline = _pipeline_for_function(function_name)
            if pipeline is not None:
                active[pipeline] += 1
        await client.aclose()
    except Exception:
        pass

    return queued, active, True


def _function_name_from_job(raw: bytes) -> str | None:
    """Extract an arq function name without deserializing the pickle payload.

    arq's default job serializer stores jobs as pickled dictionaries containing an
    ``"f"`` key for the function name.  Calling ``pickle.loads`` on Redis data is
    unsafe because Redis contents are not trusted by the admin API process, so this
    parser only walks pickle opcodes and returns the string value for the first
    ``"f"`` key when the surrounding arq job shape is present.  ``pickletools``
    disassembles the byte stream without importing or constructing
    attacker-controlled objects.
    """
    saw_function_key: bool = False
    function_name: str | None = None
    string_opcodes: set[str] = {"BINUNICODE", "SHORT_BINUNICODE", "UNICODE"}
    memo_opcodes: set[str] = {"MEMOIZE", "PUT", "BINPUT", "LONG_BINPUT"}
    structural_after_value_opcodes: set[str] = {"SETITEM"}
    expected_next_keys: set[str] = {"a", "k", "et"}
    try:
        for opcode, arg, _pos in pickletools.genops(raw):
            if function_name is not None:
                if opcode.name in memo_opcodes | structural_after_value_opcodes:
                    continue
                if opcode.name in string_opcodes and arg in expected_next_keys:
                    return function_name
                return None
            if saw_function_key:
                if opcode.name in memo_opcodes:
                    continue
                if opcode.name in string_opcodes:
                    function_name = str(arg)
                    continue
                return None
            if opcode.name in string_opcodes and arg == "f":
                saw_function_key = True
    except Exception:
        return None
    return None


def _pipeline_for_function(function_name: str) -> str | None:
    for pipeline, functions in _PIPELINE_FUNCTIONS.items():
        if function_name in functions:
            return pipeline
    return None


async def _worker_connected() -> bool:
    try:
        client = await get_redis_client()
        value: str | None = await client.get("arq:queue:health-check")
        return value is not None
    except Exception:
        return False


async def get_worker_status(db: AsyncSession, settings: Settings) -> WorkerStatusResult:
    queued_counts, active_counts, redis_connected = await _count_arq_jobs()
    worker_connected: bool = await _worker_connected() if redis_connected else False

    now: datetime = datetime.now(tz=UTC)
    cutoff_24h: datetime = now - timedelta(hours=24)
    scrape_cutoff: datetime = now - timedelta(hours=settings.job_scrape_cooldown_hours)
    enrich_cutoff: datetime = now - timedelta(days=settings.org_enrichment_cooldown_days)

    enrichable_orgs_result = await db.execute(
        select(func.count(func.distinct(Person.current_org_id))).where(
            Person.current_org_id.is_not(None),
        ),
    )
    enrichable_orgs_total: int = int(enrichable_orgs_result.scalar_one())

    enriched_orgs_result = await db.execute(
        select(func.count(func.distinct(OrgEnrichmentScrapeRun.org_id))).where(
            OrgEnrichmentScrapeRun.completed_at >= enrich_cutoff,
            OrgEnrichmentScrapeRun.error.is_(None),
        ),
    )
    enriched_orgs_processed: int = int(enriched_orgs_result.scalar_one())

    monitored_orgs_result = await db.execute(
        select(func.count(func.distinct(OrgListMembership.org_id))).join(
            User,
            User.job_monitor_list_id == OrgListMembership.org_list_id,
        ).where(
            User.job_monitor_enabled.is_(True),
            User.job_monitor_list_id.is_not(None),
        ),
    )
    monitored_orgs_total: int = int(monitored_orgs_result.scalar_one())

    scraped_orgs_result = await db.execute(
        select(func.count(func.distinct(JobScrapeRun.org_id))).where(
            JobScrapeRun.completed_at >= scrape_cutoff,
            JobScrapeRun.error.is_(None),
        ),
    )
    scraped_orgs_processed: int = int(scraped_orgs_result.scalar_one())

    active_jobs_result = await db.execute(
        select(func.count()).select_from(OrgJob).where(OrgJob.is_active.is_(True)),
    )
    active_jobs_total: int = int(active_jobs_result.scalar_one())

    scored_jobs_result = await db.execute(
        select(func.count(func.distinct(UserJobRelevance.job_id))),
    )
    scored_jobs_processed: int = int(scored_jobs_result.scalar_one())

    enrich_completed_24h_result = await db.execute(
        select(func.count()).select_from(OrgEnrichmentScrapeRun).where(
            OrgEnrichmentScrapeRun.completed_at >= cutoff_24h,
            OrgEnrichmentScrapeRun.error.is_(None),
        ),
    )
    enrich_failed_24h_result = await db.execute(
        select(func.count()).select_from(OrgEnrichmentScrapeRun).where(
            OrgEnrichmentScrapeRun.completed_at >= cutoff_24h,
            OrgEnrichmentScrapeRun.error.is_not(None),
        ),
    )
    scrape_completed_24h_result = await db.execute(
        select(func.count()).select_from(JobScrapeRun).where(
            JobScrapeRun.completed_at >= cutoff_24h,
            JobScrapeRun.error.is_(None),
        ),
    )
    scrape_failed_24h_result = await db.execute(
        select(func.count()).select_from(JobScrapeRun).where(
            JobScrapeRun.completed_at >= cutoff_24h,
            JobScrapeRun.error.is_not(None),
        ),
    )

    pipelines: list[PipelineStatus] = []
    for name, items_processed, items_total, completed_24h, failed_24h, last_run_key in (
        (
            "org_enrichment",
            enriched_orgs_processed,
            enrichable_orgs_total,
            int(enrich_completed_24h_result.scalar_one()),
            int(enrich_failed_24h_result.scalar_one()),
            "org_enrichment",
        ),
        (
            "job_discovery",
            scraped_orgs_processed,
            monitored_orgs_total,
            int(scrape_completed_24h_result.scalar_one()),
            int(scrape_failed_24h_result.scalar_one()),
            "job_discovery",
        ),
        (
            "job_scoring",
            scored_jobs_processed,
            active_jobs_total,
            scored_jobs_processed,
            0,
            "job_scoring",
        ),
    ):
        last_run_at_raw, last_run_duration_ms = await get_worker_last_run(last_run_key)
        last_run_at: datetime | None = None
        if last_run_at_raw is not None:
            try:
                last_run_at = datetime.fromisoformat(last_run_at_raw)
            except ValueError:
                last_run_at = None

        pipelines.append(
            PipelineStatus(
                name=name,
                queued=queued_counts.get(name, 0),
                active=active_counts.get(name, 0),
                completed_24h=completed_24h,
                failed_24h=failed_24h,
                last_run_at=last_run_at,
                last_run_duration_ms=last_run_duration_ms,
                items_processed=items_processed,
                items_total=items_total,
            ),
        )

    if not settings.use_arq_worker:
        message = "arq worker disabled; using in-process asyncio tasks."
    elif not redis_connected:
        message = "Redis is not reachable."
    elif not worker_connected:
        message = "No arq worker detected."
    else:
        message = "OK"

    return WorkerStatusResult(
        pipelines=pipelines,
        worker_connected=worker_connected,
        redis_connected=redis_connected,
        message=message,
    )


async def get_admin_users(db: AsyncSession) -> AdminUsersResult:
    """Return summary of all users for the admin dashboard."""

    users_result = await db.execute(select(User).order_by(User.created_at.asc()))
    users: list[User] = list(users_result.scalars().all())

    if not users:
        return AdminUsersResult(users=[], message="No users found")

    user_ids: list[Any] = [u.id for u in users]

    # Source types per user
    sources_result = await db.execute(
        select(Source.user_id, Source.source_type).where(Source.user_id.in_(user_ids))
    )
    user_sources: dict[Any, set[str]] = defaultdict(set)
    for row in sources_result:
        user_sources[row.user_id].add(row.source_type)

    # Person counts per user
    person_counts_result = await db.execute(
        select(UserPersonObservation.user_id, func.count())
        .where(UserPersonObservation.user_id.in_(user_ids))
        .group_by(UserPersonObservation.user_id)
    )
    person_counts: dict[Any, int] = dict(person_counts_result.all())

    # Org counts per user
    org_counts_result = await db.execute(
        select(UserOrgObservation.user_id, func.count())
        .where(UserOrgObservation.user_id.in_(user_ids))
        .group_by(UserOrgObservation.user_id)
    )
    org_counts: dict[Any, int] = dict(org_counts_result.all())

    # Last activity: most recent refresh token creation as proxy for last visit
    last_activity_result = await db.execute(
        select(RefreshToken.user_id, func.max(RefreshToken.created_at))
        .where(RefreshToken.user_id.in_(user_ids))
        .group_by(RefreshToken.user_id)
    )
    last_activity: dict[Any, datetime] = dict(last_activity_result.all())

    items: list[AdminUserItem] = []
    for user in users:
        sources_set: set[str] = user_sources.get(user.id, set())
        has_vcf: bool = "phone_contacts_upload" in sources_set
        has_linkedin: bool = bool(
            sources_set & {"linkedin_connections_upload", "linkedin_profile_upload"}
        )
        last_seen: datetime | None = last_activity.get(user.id) or user.updated_at

        items.append(
            AdminUserItem(
                user_id=str(user.id),
                email=user.email,
                display_name=user.display_name or user.google_profile_name,
                has_vcf=has_vcf,
                has_linkedin=has_linkedin,
                person_count=person_counts.get(user.id, 0),
                org_count=org_counts.get(user.id, 0),
                first_seen_at=user.created_at,
                last_seen_at=last_seen,
            )
        )

    return AdminUsersResult(users=items)
