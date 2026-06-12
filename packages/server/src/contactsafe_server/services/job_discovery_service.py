"""Discover and persist open jobs for target organizations."""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from contactsafe_core.contact_schemas import (
    FlatJobListResult,
    JobDetailResult,
    JobMonitorConfigResult,
    JobScanStatusResult,
    ListOrgJobsResult,
    OrgJobItem,
    OrgJobsByCompany,
    OrgPersonSummary,
    SetJobMonitorConfigRequest,
    StartSingleOrgDiscoveryResult,
)
from contactsafe_server.config import Settings
from contactsafe_server.db.models import (
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
from contactsafe_server.services.job_discovery_scheduler import is_global_scan_active
from contactsafe_server.services.job_discovery_types import DiscoveredJob
from contactsafe_server.services.theirstack_client import TheirStackClient

logger: logging.Logger = logging.getLogger(__name__)

_LAYER1_PROVIDERS: frozenset[str] = frozenset({"greenhouse", "lever", "ashby"})


class ScrapeOrgResult:
    __slots__ = ("jobs_found", "new_jobs", "source", "error", "scanned")

    def __init__(
        self,
        *,
        jobs_found: int,
        new_jobs: int,
        source: str,
        error: str | None,
        scanned: bool,
    ) -> None:
        self.jobs_found: int = jobs_found
        self.new_jobs: int = new_jobs
        self.source: str = source
        self.error: str | None = error
        self.scanned: bool = scanned


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

    async def get_scan_status(self, user_id: uuid.UUID) -> JobScanStatusResult:
        org_ids: list[uuid.UUID] = await self._list_monitored_org_ids(user_id)
        total: int = len(org_ids)
        if total == 0:
            return JobScanStatusResult(
                scanned=0,
                total=0,
                scanning_active=False,
                message="No companies selected for job monitoring.",
            )

        cutoff: datetime = datetime.now(tz=UTC) - timedelta(
            hours=self._settings.job_scrape_cooldown_hours,
        )
        scanned_result = await self._db.execute(
            select(func.count(func.distinct(JobScrapeRun.org_id))).where(
                JobScrapeRun.org_id.in_(org_ids),
                JobScrapeRun.completed_at >= cutoff,
                JobScrapeRun.error.is_(None),
            ),
        )
        scanned: int = int(scanned_result.scalar_one())
        scanning_active: bool = scanned < total or await is_global_scan_active_async()

        if scanned >= total:
            message = f"{scanned} of {total} companies scanned today."
        elif scanning_active:
            message = (
                f"{scanned} of {total} companies scanned today — scanning in progress."
            )
        else:
            message = f"{scanned} of {total} companies scanned today."

        return JobScanStatusResult(
            scanned=scanned,
            total=total,
            scanning_active=scanning_active,
            message=message,
        )

    async def collect_all_monitored_org_ids(self) -> list[uuid.UUID]:
        result = await self._db.execute(
            select(OrgListMembership.org_id)
            .join(User, User.job_monitor_list_id == OrgListMembership.org_list_id)
            .where(
                User.job_monitor_enabled.is_(True),
                User.job_monitor_list_id.is_not(None),
            )
            .distinct(),
        )
        return list(result.scalars().all())

    async def collect_orgs_needing_scrape(self) -> list[uuid.UUID]:
        """Monitored orgs outside the job-scrape cooldown window."""
        org_ids: list[uuid.UUID] = await self.collect_all_monitored_org_ids()
        needing: list[uuid.UUID] = []
        for org_id in org_ids:
            if not await self.was_recently_scraped(org_id):
                needing.append(org_id)
        return needing

    async def collect_all_monitoring_user_ids(self) -> list[uuid.UUID]:
        result = await self._db.execute(
            select(User.id).where(
                User.job_monitor_enabled.is_(True),
                User.job_monitor_list_id.is_not(None),
            ),
        )
        return list(result.scalars().all())

    async def was_recently_scraped(self, org_id: uuid.UUID) -> bool:
        cutoff: datetime = datetime.now(tz=UTC) - timedelta(
            hours=self._settings.job_scrape_cooldown_hours,
        )
        result = await self._db.execute(
            select(JobScrapeRun.id)
            .where(
                JobScrapeRun.org_id == org_id,
                JobScrapeRun.completed_at >= cutoff,
                JobScrapeRun.error.is_(None),
            )
            .limit(1),
        )
        return result.scalar_one_or_none() is not None

    async def scrape_org_global(
        self,
        org_id: uuid.UUID,
        *,
        force: bool = False,
    ) -> ScrapeOrgResult:
        """Scrape one org and record a JobScrapeRun."""
        if not force and await self.was_recently_scraped(org_id):
            return ScrapeOrgResult(
                jobs_found=0,
                new_jobs=0,
                source="none",
                error=None,
                scanned=False,
            )

        org: Org | None = await self._db.get(Org, org_id)
        if org is None:
            return ScrapeOrgResult(
                jobs_found=0,
                new_jobs=0,
                source="none",
                error=None,
                scanned=False,
            )

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

        await self._db.commit()
        return ScrapeOrgResult(
            jobs_found=found,
            new_jobs=new_count,
            source=source,
            error=error,
            scanned=actually_scanned,
        )

    async def classify_for_all_monitoring_users(self, org_id: uuid.UUID) -> None:
        from contactsafe_server.config import get_settings
        from contactsafe_server.queue import enqueue_background_job

        user_ids: list[uuid.UUID] = await self.users_monitoring_org(org_id)
        if get_settings().use_arq_worker:
            for user_id in user_ids:
                await enqueue_background_job(
                    "score_jobs_for_user",
                    str(user_id),
                    _job_id=f"score-user-{user_id}",
                )
            return
        for user_id in user_ids:
            await self._classify_new_jobs(user_id)

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

    async def discover_single_org(
        self,
        user_id: uuid.UUID,
        org_id: uuid.UUID,
    ) -> StartSingleOrgDiscoveryResult:
        """Run discovery for a single org (backgrounded when arq is enabled)."""
        from contactsafe_server.config import get_settings
        from contactsafe_server.queue import enqueue_background_job

        org: Org | None = await self._db.get(Org, org_id)
        if org is None:
            return StartSingleOrgDiscoveryResult(
                scheduled=False, message="Organization not found.",
            )

        if get_settings().use_arq_worker:
            job_id: str | None = await enqueue_background_job(
                "scrape_org_jobs",
                str(org_id),
                force=True,
                trigger_user_id=str(user_id),
                _job_id=f"scrape-org-{org_id}",
            )
            if job_id is None:
                return StartSingleOrgDiscoveryResult(
                    scheduled=False,
                    message="Could not schedule job discovery.",
                )
            return StartSingleOrgDiscoveryResult(
                scheduled=True,
                message=f"Job discovery scheduled for {org.canonical_name}.",
            )

        result: ScrapeOrgResult = await self.scrape_org_global(org_id, force=True)
        if not result.scanned:
            return StartSingleOrgDiscoveryResult(
                scheduled=False,
                message=(
                    f"No supported careers page found for {org.canonical_name}. "
                    "Add a Greenhouse, Lever, or Ashby careers URL to scan."
                ),
            )

        from contactsafe_server.job_event_publishers import publish_scan_progress

        publish_scan_progress(user_id, scanning_active=False)

        if result.new_jobs > 0:
            await self._classify_new_jobs(user_id)

        if result.error:
            return StartSingleOrgDiscoveryResult(
                scheduled=True,
                jobs_found=result.jobs_found,
                new_jobs=result.new_jobs,
                message=f"Discovery completed with error: {result.error}",
            )
        return StartSingleOrgDiscoveryResult(
            scheduled=True,
            jobs_found=result.jobs_found,
            new_jobs=result.new_jobs,
            message=(
                f"Found {result.jobs_found} jobs ({result.new_jobs} new) "
                f"for {org.canonical_name}."
            ),
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
            try:
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
                await self._db.flush()
                return True
            except IntegrityError:
                await self._db.rollback()
                result = await self._db.execute(
                    select(OrgJob).where(
                        OrgJob.org_id == org_id,
                        OrgJob.external_job_id == discovered.external_job_id,
                        OrgJob.source == discovered.source,
                    ),
                )
                existing = result.scalar_one()

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

    async def users_monitoring_org(self, org_id: uuid.UUID) -> list[uuid.UUID]:
        result = await self._db.execute(
            select(User.id)
            .join(
                OrgListMembership,
                OrgListMembership.org_list_id == User.job_monitor_list_id,
            )
            .where(
                OrgListMembership.org_id == org_id,
                User.job_monitor_enabled.is_(True),
                User.job_monitor_list_id.is_not(None),
            ),
        )
        return list(result.scalars().all())
