"""Discover and persist open jobs for target organizations."""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import UTC, datetime
from typing import Literal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from contactsafe_core.contact_schemas import (
    FlatJobListResult,
    JobDetailResult,
    JobDiscoveryStatusResult,
    JobMonitorConfigResult,
    ListOrgJobsResult,
    OrgJobItem,
    OrgJobsByCompany,
    OrgPersonSummary,
    SetJobMonitorConfigRequest,
    StartJobDiscoveryResult,
    StartSingleOrgDiscoveryResult,
)
from contactsafe_server.config import Settings
from contactsafe_server.events import (
    DiscoveryCancelledEvent,
    DiscoveryCompleteEvent,
    DiscoveryProgressEvent,
    job_event_bus,
)
from contactsafe_server.db.models import (
    JobDiscoveryRun,
    JobScrapeRun,
    Org,
    OrgJob,
    OrgList,
    OrgListMembership,
    Person,
    User,
    UserJobRelevance,
    UserPersonObservation,
)
from contactsafe_server.services.ats_detection import apply_ats_detection_to_org
from contactsafe_server.services.ats_job_clients import AtsJobClient
from contactsafe_server.services.job_discovery_scheduler import (
    release_job_discovery_lock,
    schedule_job_discovery,
)
from contactsafe_server.services.job_discovery_types import DiscoveredJob
from contactsafe_server.services.theirstack_client import TheirStackClient

logger: logging.Logger = logging.getLogger(__name__)


def _publish_discovery_progress(
    user_id: uuid.UUID,
    *,
    orgs_processed: int,
    orgs_total: int,
    jobs_found: int,
    new_jobs: int,
    progress_message: str | None,
) -> None:
    event: DiscoveryProgressEvent = {
        "type": "discovery_progress",
        "orgs_processed": orgs_processed,
        "orgs_total": orgs_total,
        "jobs_found": jobs_found,
        "new_jobs": new_jobs,
        "progress_message": progress_message,
    }
    job_event_bus.publish(user_id, event)


def _publish_discovery_complete(
    user_id: uuid.UUID,
    *,
    jobs_found: int,
    new_jobs: int,
) -> None:
    event: DiscoveryCompleteEvent = {
        "type": "discovery_complete",
        "jobs_found": jobs_found,
        "new_jobs": new_jobs,
    }
    job_event_bus.publish(user_id, event)


def _publish_discovery_cancelled(user_id: uuid.UUID) -> None:
    event: DiscoveryCancelledEvent = {"type": "discovery_cancelled"}
    job_event_bus.publish(user_id, event)

JobDiscoveryState = Literal["pending", "running", "complete", "failed"]

_LAYER1_PROVIDERS: frozenset[str] = frozenset({"greenhouse", "lever", "ashby"})


class JobDiscoveryService:
    def __init__(self, db: AsyncSession, settings: Settings) -> None:
        self._db: AsyncSession = db
        self._settings: Settings = settings
        self._ats_client: AtsJobClient = AtsJobClient(
            timeout_seconds=settings.job_discovery_request_timeout_seconds,
        )
        self._theirstack: TheirStackClient = TheirStackClient(settings)

    async def get_monitor_config(self, user_id: uuid.UUID) -> JobMonitorConfigResult:
        user: User | None = await self._db.get(User, user_id)
        if user is None:
            return JobMonitorConfigResult(
                enabled=False,
                list_id=None,
                list_name=None,
                message="User not found.",
            )
        list_name: str | None = None
        if user.job_monitor_list_id is not None:
            org_list: OrgList | None = await self._db.get(OrgList, user.job_monitor_list_id)
            if org_list is not None:
                list_name = org_list.name
        return JobMonitorConfigResult(
            enabled=user.job_monitor_enabled,
            list_id=user.job_monitor_list_id,
            list_name=list_name,
            message="Job monitor configuration loaded.",
        )

    async def set_monitor_config(
        self,
        user_id: uuid.UUID,
        body: SetJobMonitorConfigRequest,
    ) -> JobMonitorConfigResult:
        user: User | None = await self._db.get(User, user_id)
        if user is None:
            raise ValueError("User not found.")

        if body.list_id is not None:
            org_list: OrgList | None = await self._db.get(OrgList, body.list_id)
            if org_list is None or org_list.user_id != user_id:
                raise ValueError("Organization list not found.")
            user.job_monitor_list_id = body.list_id
        elif body.enabled is False:
            user.job_monitor_list_id = None

        if body.enabled is not None:
            user.job_monitor_enabled = body.enabled

        if user.job_monitor_enabled and user.job_monitor_list_id is None:
            raise ValueError("Select an organization list before enabling monitoring.")

        await self._db.flush()
        return await self.get_monitor_config(user_id)

    async def start_discovery(self, user_id: uuid.UUID) -> StartJobDiscoveryResult:
        if await self._has_running_run(user_id):
            return StartJobDiscoveryResult(
                scheduled=False,
                state="running",
                message="Job discovery is already running.",
            )

        org_ids: list[uuid.UUID] = await self._list_monitored_org_ids(user_id)
        if not org_ids:
            return StartJobDiscoveryResult(
                scheduled=False,
                state="complete",
                message="No organizations to scan. Select a target list with companies.",
            )

        run = JobDiscoveryRun(
            user_id=user_id,
            state="running",
            started_at=datetime.now(tz=UTC),
            orgs_total=len(org_ids),
            orgs_processed=0,
            progress_message="Starting job discovery…",
        )
        self._db.add(run)
        await self._db.flush()

        if not schedule_job_discovery(user_id, run.id):
            run.state = "failed"
            run.error = "Could not schedule job discovery task"
            run.completed_at = datetime.now(tz=UTC)
            await self._db.commit()
            return StartJobDiscoveryResult(
                scheduled=False,
                state="failed",
                message="Job discovery is already running.",
            )

        await self._db.commit()
        _publish_discovery_progress(
            user_id,
            orgs_processed=0,
            orgs_total=len(org_ids),
            jobs_found=0,
            new_jobs=0,
            progress_message=run.progress_message,
        )
        return StartJobDiscoveryResult(
            scheduled=True,
            state="running",
            message="Job discovery started in the background.",
        )

    async def get_status(self, user_id: uuid.UUID) -> JobDiscoveryStatusResult:
        run: JobDiscoveryRun | None = await self._latest_run(user_id)
        if run is None:
            return JobDiscoveryStatusResult(
                state="pending",
                orgs_total=0,
                orgs_processed=0,
                jobs_found=0,
                new_jobs=0,
                progress_message=None,
                error=None,
                message="No job discovery runs yet.",
            )
        state: JobDiscoveryState = run.state  # type: ignore[assignment]
        return JobDiscoveryStatusResult(
            state=state,
            orgs_total=run.orgs_total,
            orgs_processed=run.orgs_processed,
            jobs_found=run.jobs_found,
            new_jobs=run.new_jobs,
            progress_message=run.progress_message,
            error=run.error,
            message=self._status_message(state, run),
        )

    async def list_jobs_for_user(
        self,
        user_id: uuid.UUID,
        *,
        active_only: bool = True,
        relevant_only: bool = False,
    ) -> ListOrgJobsResult:
        org_ids: list[uuid.UUID] = await self._list_monitored_org_ids(user_id)
        if not org_ids:
            return ListOrgJobsResult(companies=[], total_jobs=0, total_relevant=0, message="No monitored organizations.")

        orgs_result = await self._db.execute(
            select(Org).where(Org.id.in_(org_ids)).order_by(Org.canonical_name.asc()),
        )
        orgs: list[Org] = list(orgs_result.scalars().all())

        jobs_query = select(OrgJob).where(OrgJob.org_id.in_(org_ids))
        if active_only:
            jobs_query = jobs_query.where(OrgJob.is_active.is_(True))
        jobs_query = jobs_query.order_by(OrgJob.posted_at.desc().nullslast(), OrgJob.title.asc())
        jobs_result = await self._db.execute(jobs_query)
        jobs: list[OrgJob] = list(jobs_result.scalars().all())

        relevance_result = await self._db.execute(
            select(UserJobRelevance).where(UserJobRelevance.user_id == user_id),
        )
        relevance_map: dict[uuid.UUID, UserJobRelevance] = {
            r.job_id: r for r in relevance_result.scalars().all()
        }

        jobs_by_org: dict[uuid.UUID, list[OrgJob]] = {}
        for job in jobs:
            jobs_by_org.setdefault(job.org_id, []).append(job)

        last_checked_subq = (
            select(
                JobScrapeRun.org_id,
                func.max(JobScrapeRun.completed_at).label("last_checked_at"),
            )
            .where(JobScrapeRun.org_id.in_(org_ids))
            .group_by(JobScrapeRun.org_id)
        )
        last_checked_result = await self._db.execute(last_checked_subq)
        last_checked_map: dict[uuid.UUID, datetime] = {
            row.org_id: row.last_checked_at
            for row in last_checked_result.all()
            if row.last_checked_at is not None
        }

        companies: list[OrgJobsByCompany] = []
        total_jobs: int = 0
        total_relevant: int = 0
        for org in orgs:
            org_jobs: list[OrgJob] = jobs_by_org.get(org.id, [])

            job_items: list[OrgJobItem] = []
            for job in org_jobs:
                rel: UserJobRelevance | None = relevance_map.get(job.id)
                is_relevant: bool | None = rel.is_relevant if rel else None
                reason: str | None = rel.reason if rel and rel.is_relevant else None

                if relevant_only and is_relevant is False:
                    continue

                if is_relevant is True:
                    total_relevant += 1

                job_items.append(
                    OrgJobItem(
                        job_id=job.id,
                        external_job_id=job.external_job_id,
                        source=job.source,
                        title=job.title,
                        org_primary_domain=org.primary_domain,
                        location=job.location,
                        department=job.department,
                        url=job.url,
                        description_snippet=job.description_snippet,
                        salary_min=job.salary_min,
                        salary_max=job.salary_max,
                        remote_status=job.remote_status,
                        posted_at=job.posted_at,
                        first_seen_at=job.first_seen_at,
                        last_seen_at=job.last_seen_at,
                        is_active=job.is_active,
                        is_relevant=is_relevant,
                        relevance_reason=reason,
                    )
                )

            total_jobs += len(job_items)
            companies.append(
                OrgJobsByCompany(
                    org_id=org.id,
                    org_name=org.canonical_name,
                    primary_domain=org.primary_domain,
                    description=org.description,
                    last_checked_at=last_checked_map.get(org.id),
                    jobs=job_items,
                ),
            )

        message: str = (
            f"Found {total_jobs} open job(s) across {len(companies)} company(ies)."
            if total_jobs > 0
            else "No open jobs found yet. Run job discovery from Setup."
        )
        return ListOrgJobsResult(companies=companies, total_jobs=total_jobs, total_relevant=total_relevant, message=message)

    async def list_flat_jobs_for_user(
        self,
        user_id: uuid.UUID,
        *,
        active_only: bool = True,
    ) -> FlatJobListResult:
        org_ids: list[uuid.UUID] = await self._list_monitored_org_ids(user_id)
        if not org_ids:
            return FlatJobListResult(jobs=[], total_jobs=0, total_relevant=0, message="No monitored organizations.")

        orgs_result = await self._db.execute(
            select(Org).where(Org.id.in_(org_ids)),
        )
        orgs: list[Org] = list(orgs_result.scalars().all())
        org_name_map: dict[uuid.UUID, str] = {
            org.id: org.canonical_name for org in orgs
        }
        org_domain_map: dict[uuid.UUID, str | None] = {
            org.id: org.primary_domain for org in orgs
        }

        jobs_query = select(OrgJob).where(OrgJob.org_id.in_(org_ids))
        if active_only:
            jobs_query = jobs_query.where(OrgJob.is_active.is_(True))
        jobs_result = await self._db.execute(jobs_query)
        jobs: list[OrgJob] = list(jobs_result.scalars().all())

        relevance_result = await self._db.execute(
            select(UserJobRelevance).where(UserJobRelevance.user_id == user_id),
        )
        relevance_map: dict[uuid.UUID, UserJobRelevance] = {
            r.job_id: r for r in relevance_result.scalars().all()
        }

        unique_org_ids: list[uuid.UUID] = list({job.org_id for job in jobs})
        contact_summaries: dict[uuid.UUID, tuple[str, int]] = (
            await self._load_user_contact_summaries_by_org(user_id, unique_org_ids)
        )

        job_items: list[OrgJobItem] = []
        total_relevant: int = 0
        for job in jobs:
            rel: UserJobRelevance | None = relevance_map.get(job.id)
            is_relevant: bool | None = rel.is_relevant if rel else None
            match_score: int | None = rel.match_score if rel else None
            reason: str | None = rel.reason if rel else None

            if is_relevant is True:
                total_relevant += 1

            contact_summary: tuple[str, int] | None = contact_summaries.get(job.org_id)
            primary_contact_name: str | None = contact_summary[0] if contact_summary else None
            contact_count: int = contact_summary[1] if contact_summary else 0

            job_items.append(
                OrgJobItem(
                    job_id=job.id,
                    external_job_id=job.external_job_id,
                    source=job.source,
                    title=job.title,
                    org_name=org_name_map.get(job.org_id),
                    org_id=job.org_id,
                    org_primary_domain=org_domain_map.get(job.org_id),
                    location=job.location,
                    department=job.department,
                    url=job.url,
                    description_snippet=job.description_snippet,
                    salary_min=job.salary_min,
                    salary_max=job.salary_max,
                    remote_status=job.remote_status,
                    posted_at=job.posted_at,
                    first_seen_at=job.first_seen_at,
                    last_seen_at=job.last_seen_at,
                    is_active=job.is_active,
                    is_relevant=is_relevant,
                    match_score=match_score,
                    relevance_reason=reason,
                    role_score=rel.role_score if rel else None,
                    role_reason=rel.role_reason if rel else None,
                    seniority_score=rel.seniority_score if rel else None,
                    seniority_reason=rel.seniority_reason if rel else None,
                    location_score=rel.location_score if rel else None,
                    location_reason=rel.location_reason if rel else None,
                    contact_count=contact_count,
                    primary_contact_name=primary_contact_name,
                )
            )

        job_items.sort(
            key=lambda j: (j.match_score if j.match_score is not None else -1),
            reverse=True,
        )

        message: str = (
            f"Found {len(job_items)} open job(s)."
            if job_items
            else "No open jobs found yet."
        )
        return FlatJobListResult(
            jobs=job_items,
            total_jobs=len(job_items),
            total_relevant=total_relevant,
            message=message,
        )

    async def get_job_detail(
        self,
        user_id: uuid.UUID,
        job_id: uuid.UUID,
    ) -> JobDetailResult | None:
        job: OrgJob | None = await self._db.get(OrgJob, job_id)
        if job is None:
            return None

        org: Org | None = await self._db.get(Org, job.org_id)

        rel_result = await self._db.execute(
            select(UserJobRelevance).where(
                UserJobRelevance.user_id == user_id,
                UserJobRelevance.job_id == job_id,
            ),
        )
        rel: UserJobRelevance | None = rel_result.scalar_one_or_none()

        contact_summaries: dict[uuid.UUID, tuple[str, int]] = (
            await self._load_user_contact_summaries_by_org(user_id, [job.org_id])
        )
        contact_summary: tuple[str, int] | None = contact_summaries.get(job.org_id)
        primary_contact_name: str | None = contact_summary[0] if contact_summary else None
        contact_count: int = contact_summary[1] if contact_summary else 0

        people_result = await self._db.execute(
            select(Person)
            .join(
                UserPersonObservation,
                (UserPersonObservation.person_id == Person.id)
                & (UserPersonObservation.user_id == user_id),
            )
            .where(Person.current_org_id == job.org_id)
            .order_by(Person.canonical_name.asc())
            .limit(20),
        )
        contacts: list[OrgPersonSummary] = [
            OrgPersonSummary(
                person_id=p.id,
                display_name=p.canonical_name,
                primary_email=p.primary_email,
                current_role=p.current_role,
            )
            for p in people_result.scalars().all()
        ]

        item = OrgJobItem(
            job_id=job.id,
            external_job_id=job.external_job_id,
            source=job.source,
            title=job.title,
            org_name=org.canonical_name if org else None,
            org_id=job.org_id,
            org_primary_domain=org.primary_domain if org else None,
            location=job.location,
            department=job.department,
            url=job.url,
            description_snippet=job.description_snippet,
            salary_min=job.salary_min,
            salary_max=job.salary_max,
            remote_status=job.remote_status,
            posted_at=job.posted_at,
            first_seen_at=job.first_seen_at,
            last_seen_at=job.last_seen_at,
            is_active=job.is_active,
            is_relevant=rel.is_relevant if rel else None,
            match_score=rel.match_score if rel else None,
            relevance_reason=rel.reason if rel else None,
            role_score=rel.role_score if rel else None,
            role_reason=rel.role_reason if rel else None,
            seniority_score=rel.seniority_score if rel else None,
            seniority_reason=rel.seniority_reason if rel else None,
            location_score=rel.location_score if rel else None,
            location_reason=rel.location_reason if rel else None,
            contact_count=contact_count,
            primary_contact_name=primary_contact_name,
        )

        return JobDetailResult(
            job=item,
            org_description=org.description if org else None,
            org_primary_domain=org.primary_domain if org else None,
            contacts=contacts,
            contact_count=len(contacts),
            message=f"Job detail for {job.title}.",
        )

    async def run_discovery(self, user_id: uuid.UUID, run_id: uuid.UUID) -> None:
        run: JobDiscoveryRun | None = await self._db.get(JobDiscoveryRun, run_id)
        if run is None or run.user_id != user_id:
            return

        org_ids: list[uuid.UUID] = await self._list_monitored_org_ids(user_id)
        run.orgs_total = len(org_ids)
        run.state = "running"
        run.started_at = datetime.now(tz=UTC)
        run.progress_message = "Scanning organizations…"
        await self._db.commit()
        _publish_discovery_progress(
            user_id,
            orgs_processed=0,
            orgs_total=len(org_ids),
            jobs_found=0,
            new_jobs=0,
            progress_message=run.progress_message,
        )

        total_jobs_found: int = 0
        total_new_jobs: int = 0
        processed: int = 0
        skipped: int = 0

        for org_id in org_ids:
            await self._db.refresh(run)
            if run.state == "cancelled":
                _publish_discovery_cancelled(user_id)
                return

            org: Org | None = await self._db.get(Org, org_id)
            if org is None:
                processed += 1
                continue

            apply_ats_detection_to_org(org)
            found, new_count, source, error = await self._discover_jobs_for_org(org)

            if source == "theirstack":
                await asyncio.sleep(7.0)

            actually_scanned: bool = source != "none" or error is not None
            if actually_scanned:
                scrape_run = JobScrapeRun(
                    org_id=org.id,
                    source=source,
                    started_at=datetime.now(tz=UTC),
                    completed_at=datetime.now(tz=UTC),
                    jobs_found=found,
                    new_jobs=new_count,
                    error=error,
                )
                self._db.add(scrape_run)
            else:
                skipped += 1

            total_jobs_found += found
            total_new_jobs += new_count
            processed += 1
            run.orgs_processed = processed
            run.jobs_found = total_jobs_found
            run.new_jobs = total_new_jobs
            scanned_count: int = processed - skipped
            if skipped > 0:
                run.progress_message = (
                    f"Scanned {scanned_count}/{run.orgs_total} companies "
                    f"({skipped} skipped — no supported careers page)…"
                )
            else:
                run.progress_message = f"Scanned {processed}/{run.orgs_total} companies…"
            await self._db.commit()
            _publish_discovery_progress(
                user_id,
                orgs_processed=processed,
                orgs_total=run.orgs_total,
                jobs_found=total_jobs_found,
                new_jobs=total_new_jobs,
                progress_message=run.progress_message,
            )

            if new_count > 0:
                await self._classify_new_jobs(user_id)

        run.state = "complete"
        run.completed_at = datetime.now(tz=UTC)
        run.progress_message = None
        run.error = None
        await self._db.commit()
        _publish_discovery_complete(
            user_id,
            jobs_found=total_jobs_found,
            new_jobs=total_new_jobs,
        )

    async def discover_single_org(
        self,
        user_id: uuid.UUID,
        org_id: uuid.UUID,
    ) -> StartSingleOrgDiscoveryResult:
        """Run discovery for a single org synchronously (not backgrounded)."""
        org: Org | None = await self._db.get(Org, org_id)
        if org is None:
            return StartSingleOrgDiscoveryResult(
                scheduled=False, message="Organization not found.",
            )

        apply_ats_detection_to_org(org)
        found, new_count, source, error = await self._discover_jobs_for_org(org)

        actually_scanned: bool = source != "none" or error is not None
        if actually_scanned:
            scrape_run = JobScrapeRun(
                org_id=org.id,
                source=source,
                started_at=datetime.now(tz=UTC),
                completed_at=datetime.now(tz=UTC),
                jobs_found=found,
                new_jobs=new_count,
                error=error,
            )
            self._db.add(scrape_run)
            await self._db.commit()
        else:
            await self._db.commit()
            return StartSingleOrgDiscoveryResult(
                scheduled=False,
                message=(
                    f"No supported careers page found for {org.canonical_name}. "
                    "Add a Greenhouse, Lever, or Ashby careers URL to scan."
                ),
            )

        if new_count > 0:
            await self._classify_new_jobs(user_id)

        if error:
            return StartSingleOrgDiscoveryResult(
                scheduled=True,
                jobs_found=found,
                new_jobs=new_count,
                message=f"Discovery completed with error: {error}",
            )
        return StartSingleOrgDiscoveryResult(
            scheduled=True,
            jobs_found=found,
            new_jobs=new_count,
            message=f"Found {found} jobs ({new_count} new) for {org.canonical_name}.",
        )

    async def upsert_discovered_job(
        self,
        org_id: uuid.UUID,
        discovered: DiscoveredJob,
    ) -> bool:
        """Insert or update a job. Returns True if this is a newly seen job."""
        now: datetime = datetime.now(tz=UTC)
        result = await self._db.execute(
            select(OrgJob).where(
                OrgJob.org_id == org_id,
                OrgJob.external_job_id == discovered.external_job_id,
                OrgJob.source == discovered.source,
            ),
        )
        existing: OrgJob | None = result.scalar_one_or_none()
        if existing is None:
            self._db.add(
                OrgJob(
                    org_id=org_id,
                    external_job_id=discovered.external_job_id,
                    source=discovered.source,
                    title=discovered.title,
                    location=discovered.location,
                    department=discovered.department,
                    url=discovered.url,
                    description_snippet=discovered.description_snippet,
                    salary_min=discovered.salary_min,
                    salary_max=discovered.salary_max,
                    remote_status=discovered.remote_status,
                    posted_at=discovered.posted_at,
                    first_seen_at=now,
                    last_seen_at=now,
                    is_active=True,
                ),
            )
            return True

        existing.title = discovered.title
        existing.location = discovered.location
        existing.department = discovered.department
        existing.url = discovered.url
        existing.description_snippet = discovered.description_snippet
        existing.salary_min = discovered.salary_min
        existing.salary_max = discovered.salary_max
        existing.remote_status = discovered.remote_status
        if discovered.posted_at is not None:
            existing.posted_at = discovered.posted_at
        existing.last_seen_at = now
        existing.is_active = True
        return False

    async def _discover_jobs_for_org(
        self,
        org: Org,
    ) -> tuple[int, int, str, str | None]:
        discovered_jobs: list[DiscoveredJob] = []
        source: str = "none"
        error: str | None = None

        provider: str | None = org.ats_provider
        token: str | None = org.ats_board_token
        successful_source: str | None = None
        if provider in _LAYER1_PROVIDERS and token:
            source = provider
            try:
                discovered_jobs = await self._ats_client.fetch_jobs(
                    provider=provider,  # type: ignore[arg-type]
                    board_token=token,
                )
                successful_source = provider
            except Exception as exc:
                error = str(exc)[:500]
                logger.exception("ATS fetch failed for org %s", org.id)

        if not discovered_jobs and self._theirstack.is_configured():
            source = "theirstack"
            try:
                discovered_jobs = await self._theirstack.search_jobs_for_org(org)
                successful_source = "theirstack"
            except Exception as exc:
                error = str(exc)[:500]
                logger.exception("TheirStack fetch failed for org %s", org.id)

        if successful_source is None:
            return 0, 0, source, error

        if not discovered_jobs:
            await self._mark_stale_jobs_inactive(org.id, successful_source)
            return 0, 0, successful_source, error

        new_count: int = 0
        seen_keys: set[tuple[str, str]] = set()
        for job in discovered_jobs:
            seen_keys.add((job.external_job_id, job.source))
            is_new: bool = await self.upsert_discovered_job(org.id, job)
            if is_new:
                new_count += 1

        await self._deactivate_missing_jobs(org.id, seen_keys)
        return len(discovered_jobs), new_count, successful_source, error

    async def _deactivate_missing_jobs(
        self,
        org_id: uuid.UUID,
        seen_keys: set[tuple[str, str]],
    ) -> None:
        result = await self._db.execute(
            select(OrgJob).where(OrgJob.org_id == org_id, OrgJob.is_active.is_(True)),
        )
        for job in result.scalars().all():
            key: tuple[str, str] = (job.external_job_id, job.source)
            if key not in seen_keys:
                job.is_active = False

    async def _mark_stale_jobs_inactive(self, org_id: uuid.UUID, source: str) -> None:
        result = await self._db.execute(
            select(OrgJob).where(
                OrgJob.org_id == org_id,
                OrgJob.source == source,
                OrgJob.is_active.is_(True),
            ),
        )
        for job in result.scalars().all():
            job.is_active = False

    async def _classify_new_jobs(self, user_id: uuid.UUID) -> None:
        """Run LLM classification on any unclassified jobs after discovery."""
        try:
            from contactsafe_server.services.job_relevance_service import (
                JobRelevanceService,
            )

            svc = JobRelevanceService(self._db, self._settings)
            count: int = await svc.classify_jobs_for_user(user_id)
            if count > 0:
                logger.info("Classified %d jobs for user %s", count, user_id)
        except Exception:
            logger.exception("Job classification failed for user %s", user_id)

    async def _load_user_contact_summaries_by_org(
        self,
        user_id: uuid.UUID,
        org_ids: list[uuid.UUID],
    ) -> dict[uuid.UUID, tuple[str, int]]:
        if not org_ids:
            return {}

        result = await self._db.execute(
            select(Person.current_org_id, Person.canonical_name)
            .join(
                UserPersonObservation,
                (UserPersonObservation.person_id == Person.id)
                & (UserPersonObservation.user_id == user_id),
            )
            .where(Person.current_org_id.in_(org_ids))
            .order_by(Person.current_org_id, Person.canonical_name.asc()),
        )

        summaries: dict[uuid.UUID, tuple[str, int]] = {}
        org_id: uuid.UUID | None
        name: str
        for org_id, name in result.all():
            if org_id is None:
                continue
            if org_id not in summaries:
                summaries[org_id] = (name, 1)
            else:
                first_name, count = summaries[org_id]
                summaries[org_id] = (first_name, count + 1)
        return summaries

    async def _list_monitored_org_ids(self, user_id: uuid.UUID) -> list[uuid.UUID]:
        user: User | None = await self._db.get(User, user_id)
        if user is None or user.job_monitor_list_id is None:
            return []
        result = await self._db.execute(
            select(OrgListMembership.org_id).where(
                OrgListMembership.org_list_id == user.job_monitor_list_id,
            ),
        )
        return list(result.scalars().all())

    async def _has_running_run(self, user_id: uuid.UUID) -> bool:
        result = await self._db.execute(
            select(JobDiscoveryRun.id).where(
                JobDiscoveryRun.user_id == user_id,
                JobDiscoveryRun.state == "running",
            ),
        )
        return result.scalar_one_or_none() is not None

    async def cancel_discovery(self, user_id: uuid.UUID) -> None:
        """Mark the current running discovery as cancelled."""
        result = await self._db.execute(
            select(JobDiscoveryRun).where(
                JobDiscoveryRun.user_id == user_id,
                JobDiscoveryRun.state == "running",
            ),
        )
        run: JobDiscoveryRun | None = result.scalar_one_or_none()
        if run is not None:
            run.state = "cancelled"
            run.completed_at = datetime.now(tz=UTC)
            run.progress_message = None
            run.error = "Cancelled by user."
            await self._db.commit()
            _publish_discovery_cancelled(user_id)
        release_job_discovery_lock(user_id)

    async def _latest_run(self, user_id: uuid.UUID) -> JobDiscoveryRun | None:
        result = await self._db.execute(
            select(JobDiscoveryRun)
            .where(JobDiscoveryRun.user_id == user_id)
            .order_by(JobDiscoveryRun.created_at.desc())
            .limit(1),
        )
        return result.scalar_one_or_none()

    @staticmethod
    def _status_message(state: JobDiscoveryState, run: JobDiscoveryRun) -> str:
        if state == "running":
            return (
                f"Scanning companies ({run.orgs_processed}/{run.orgs_total}). "
                f"{run.jobs_found} jobs found so far."
            )
        if state == "complete":
            return (
                f"Discovery complete. {run.jobs_found} jobs found "
                f"({run.new_jobs} new)."
            )
        if state == "failed":
            return run.error or "Job discovery failed."
        if state == "cancelled":
            return "Job discovery was cancelled."
        return "Job discovery pending."

    async def maybe_start_scheduled_discovery(self, user_id: uuid.UUID) -> bool:
        if await self._has_running_run(user_id):
            return False
        org_ids: list[uuid.UUID] = await self._list_monitored_org_ids(user_id)
        if not org_ids:
            return False
        run = JobDiscoveryRun(
            user_id=user_id,
            state="running",
            started_at=datetime.now(tz=UTC),
            orgs_total=len(org_ids),
            orgs_processed=0,
            progress_message="Scheduled scan…",
        )
        self._db.add(run)
        await self._db.flush()
        run_id: uuid.UUID = run.id
        await self._db.commit()
        return schedule_job_discovery(user_id, run_id)
