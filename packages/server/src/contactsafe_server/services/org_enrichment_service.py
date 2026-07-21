"""Background org enrichment using Exa search."""

from __future__ import annotations

import asyncio
import logging
import re
import threading
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal
from urllib.parse import urlparse

from sqlalchemy import exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from contactsafe_core.contact_schemas import (
    CancelOrgEnrichmentResult,
    EnrichOrgsResult,
    OrgEnrichmentStatusResult,
)
from contactsafe_server.config import Settings
from contactsafe_server.db.models import (
    Org,
    OrgEnrichmentRun,
    OrgEnrichmentScrapeRun,
    OrgListMembership,
    Person,
    PersonAlias,
    User,
    UserPersonObservation,
)
from contactsafe_server.graph_event_publishers import (
    publish_org_enrichment_complete,
    publish_org_enrichment_failed,
    publish_org_enrichment_progress,
)
from contactsafe_server.services.contacts_service import PHONE_RELATIONSHIP
from contactsafe_server.services.exa_client import ExaClient
from contactsafe_server.services.org_company_size import (
    ParsedCompanySize,
    headcount_to_linkedin_band,
)
from contactsafe_server.services.org_industry_taxonomy import (
    build_company_summary_query,
    exa_company_summary_schema,
    infer_industry_tags_from_text,
    parse_structured_company_summary,
)
from contactsafe_server.services.ats_detection import apply_ats_detection_to_org
from contactsafe_server.services.strong_tie_matcher import LINKEDIN_CONNECTIONS_RELATIONSHIP
from contactsafe_server.services.web_search_types import WebSearchHit

logger: logging.Logger = logging.getLogger(__name__)

OrgEnrichmentState = Literal["pending", "running", "complete", "failed"]

_LINKEDIN_COMPANY_RE: re.Pattern[str] = re.compile(
    r"^https?://(?:[a-z]+\.)?linkedin\.com/company/[^/?#]+",
    flags=re.IGNORECASE,
)
_CAREERS_PATH_RE: re.Pattern[str] = re.compile(
    r"/(?:careers|jobs|join-us|openings|work-with-us)(?:/|$)",
    flags=re.IGNORECASE,
)
_SKIP_DOMAINS: frozenset[str] = frozenset(
    {
        "linkedin.com",
        "facebook.com",
        "twitter.com",
        "x.com",
        "instagram.com",
        "youtube.com",
        "wikipedia.org",
        "crunchbase.com",
        "glassdoor.com",
        "indeed.com",
        "google.com",
        "bing.com",
    }
)

_scheduling_lock: threading.Lock = threading.Lock()
_active_org_enrichment_user_ids: set[uuid.UUID] = set()


class EnrichOrgResult:
    __slots__ = ("fields_updated", "source", "error", "enriched")

    def __init__(
        self,
        *,
        fields_updated: int,
        source: str,
        error: str | None,
        enriched: bool,
    ) -> None:
        self.fields_updated: int = fields_updated
        self.source: str = source
        self.error: str | None = error
        self.enriched: bool = enriched


@dataclass(frozen=True, slots=True)
class _OrgEnrichmentSnapshot:
    primary_domain: str | None
    description: str | None
    careers_url: str | None
    linkedin_url: str | None
    categories: tuple[str, ...]
    employee_count: int | None
    company_size_band: str | None
    funding_stage: str | None
    ats_provider: str | None
    ats_board_token: str | None


class OrgEnrichmentService:
    def __init__(self, db: AsyncSession, settings: Settings) -> None:
        self._db: AsyncSession = db
        self._settings: Settings = settings
        self._exa: ExaClient = ExaClient(settings)

    async def start_enrichment(self, user_id: uuid.UUID) -> EnrichOrgsResult:
        if not self._settings.exa_api_key:
            return EnrichOrgsResult(
                scheduled=False,
                state="failed",
                message="Exa API key is not configured.",
            )

        if await self._has_running_run(user_id):
            return EnrichOrgsResult(
                scheduled=False,
                state="running",
                message="Company enrichment is already running.",
            )

        unenriched_org_ids: list[uuid.UUID] = await self._list_unenriched_user_org_ids(
            user_id
        )
        total_orgs: int = await self._count_user_orgs(user_id)
        if total_orgs == 0:
            return EnrichOrgsResult(
                scheduled=False,
                state="complete",
                message="No organizations to enrich yet.",
            )
        if not unenriched_org_ids:
            return EnrichOrgsResult(
                scheduled=False,
                state="complete",
                message="All organizations are already enriched.",
            )

        run = OrgEnrichmentRun(
            user_id=user_id,
            state="running",
            started_at=datetime.now(tz=UTC),
            orgs_total=len(unenriched_org_ids),
            orgs_enriched=0,
            progress_message=self._progress_message(0, len(unenriched_org_ids)),
        )
        self._db.add(run)
        await self._db.flush()

        if not schedule_org_enrichment(user_id, run.id):
            run.state = "failed"
            run.error = "Could not schedule company enrichment task"
            run.completed_at = datetime.now(tz=UTC)
            await self._db.commit()
            return EnrichOrgsResult(
                scheduled=False,
                state="failed",
                message="Company enrichment is already running.",
            )

        await self._db.commit()
        publish_org_enrichment_progress(
            user_id,
            orgs_enriched=0,
            orgs_total=len(unenriched_org_ids),
            progress_message=run.progress_message,
        )
        return EnrichOrgsResult(
            scheduled=True,
            state="running",
            message="Company enrichment started in the background.",
        )

    _STALE_RUN_THRESHOLD: timedelta = timedelta(minutes=5)

    async def _recover_stale_run(self, run: OrgEnrichmentRun) -> None:
        """Mark a run as failed if the background task appears to have crashed."""
        if run.state != "running":
            return
        stale_cutoff: datetime = datetime.now(tz=UTC) - self._STALE_RUN_THRESHOLD
        if run.updated_at > stale_cutoff:
            return
        logger.warning(
            "Recovering stale enrichment run %s (last updated %s)",
            run.id,
            run.updated_at.isoformat(),
        )
        run.state = "failed"
        run.error = "Enrichment task stopped unexpectedly. You can retry."
        run.completed_at = datetime.now(tz=UTC)
        run.progress_message = None
        await self._db.commit()
        publish_org_enrichment_failed(
            run.user_id,
            orgs_enriched=run.orgs_enriched,
            orgs_total=run.orgs_total,
            error=run.error,
        )

    async def get_status(self, user_id: uuid.UUID) -> OrgEnrichmentStatusResult:
        run: OrgEnrichmentRun | None = await self._latest_run(user_id)
        orgs_total: int = await self._count_user_orgs(user_id)
        orgs_enriched: int = await self._count_enriched_orgs(user_id)

        if run is not None:
            if run.state == "running":
                await self._recover_stale_run(run)
            state: OrgEnrichmentState = run.state  # type: ignore[assignment]
            return OrgEnrichmentStatusResult(
                state=state,
                orgs_total=max(run.orgs_total, orgs_total),
                orgs_enriched=run.orgs_enriched if run.state == "running" else max(run.orgs_enriched, orgs_enriched),
                progress_message=run.progress_message,
                error=run.error,
                message=self._status_message(state, run.orgs_enriched, run.orgs_total),
            )

        if orgs_total == 0:
            return OrgEnrichmentStatusResult(
                state="pending",
                orgs_total=0,
                orgs_enriched=0,
                progress_message=None,
                error=None,
                message="No organizations to enrich yet.",
            )

        idle_state: OrgEnrichmentState = (
            "complete" if orgs_enriched >= orgs_total else "pending"
        )
        return OrgEnrichmentStatusResult(
            state=idle_state,
            orgs_total=orgs_total,
            orgs_enriched=orgs_enriched,
            progress_message=None,
            error=None,
            message=self._status_message(idle_state, orgs_enriched, orgs_total),
        )

    async def cancel_enrichment(self, user_id: uuid.UUID) -> CancelOrgEnrichmentResult:
        run: OrgEnrichmentRun | None = await self._latest_run(user_id)
        if run is None or run.state != "running":
            return CancelOrgEnrichmentResult(
                cancelled=False,
                message="No enrichment in progress.",
            )

        run.state = "failed"
        run.error = "Enrichment cancelled by user."
        run.completed_at = datetime.now(tz=UTC)
        run.progress_message = None
        await self._db.commit()
        publish_org_enrichment_failed(
            user_id,
            orgs_enriched=run.orgs_enriched,
            orgs_total=run.orgs_total,
            error=run.error,
        )
        return CancelOrgEnrichmentResult(
            cancelled=True,
            message="Enrichment cancelled.",
        )

    async def enrich_orgs(self, user_id: uuid.UUID, run_id: uuid.UUID) -> None:
        run: OrgEnrichmentRun | None = await self._db.get(OrgEnrichmentRun, run_id)
        if run is None:
            logger.warning("Org enrichment run %s not found", run_id)
            return

        org_ids: list[uuid.UUID] = await self._list_unenriched_user_org_ids(user_id)
        run.orgs_total = len(org_ids)
        run.orgs_enriched = 0
        run.progress_message = self._progress_message(0, run.orgs_total)
        await self._db.commit()
        publish_org_enrichment_progress(
            user_id,
            orgs_enriched=0,
            orgs_total=run.orgs_total,
            progress_message=run.progress_message,
        )

        for index, org_id in enumerate(org_ids, start=1):
            run = await self._db.get(OrgEnrichmentRun, run_id)
            if run is None or run.state != "running":
                return

            org: Org | None = await self._db.get(Org, org_id)
            org_name: str = org.canonical_name if org is not None else str(org_id)

            try:
                enrich_result: EnrichOrgResult = await self.enrich_org_global(org_id)
                run = await self._db.get(OrgEnrichmentRun, run_id)
                if run is None or run.state != "running":
                    return
                run.orgs_enriched = index
                run.progress_message = self._progress_message(
                    run.orgs_enriched,
                    run.orgs_total,
                )
                await self._db.commit()
                publish_org_enrichment_progress(
                    user_id,
                    orgs_enriched=run.orgs_enriched,
                    orgs_total=run.orgs_total,
                    progress_message=run.progress_message,
                )
                logger.info(
                    "Org enrichment progress: %d/%d (%s, enriched=%s)",
                    run.orgs_enriched,
                    run.orgs_total,
                    org_name,
                    enrich_result.enriched,
                )
            except Exception:
                logger.exception("Failed to enrich org %s (%s)", org_id, org_name)
                await self._db.rollback()
                run = await self._db.get(OrgEnrichmentRun, run_id)
                if run is None or run.state != "running":
                    return
            await asyncio.sleep(0.5)

        run = await self._db.get(OrgEnrichmentRun, run_id)
        if run is None or run.state != "running":
            return
        run.state = "complete"
        run.completed_at = datetime.now(tz=UTC)
        run.progress_message = None
        await self._db.commit()
        publish_org_enrichment_complete(
            user_id,
            orgs_enriched=run.orgs_enriched,
            orgs_total=run.orgs_total,
        )

    async def _collect_monitored_org_ids(self) -> set[uuid.UUID]:
        """Orgs on any enabled user's job-monitor list (includes contact-less watches)."""
        result = await self._db.execute(
            select(OrgListMembership.org_id)
            .join(User, User.job_monitor_list_id == OrgListMembership.org_list_id)
            .where(
                User.job_monitor_enabled.is_(True),
                User.job_monitor_list_id.is_not(None),
            )
            .distinct(),
        )
        return set(result.scalars().all())

    async def collect_all_enrichable_org_ids(self) -> list[uuid.UUID]:
        person_linked = await self._db.execute(
            select(Org.id)
            .join(Person, Person.current_org_id == Org.id)
            .group_by(Org.id),
        )
        org_ids: set[uuid.UUID] = set(person_linked.scalars().all())
        org_ids |= await self._collect_monitored_org_ids()
        if not org_ids:
            return []
        ordered = await self._db.execute(
            select(Org.id)
            .where(Org.id.in_(org_ids))
            .order_by(Org.canonical_name.asc()),
        )
        return list(ordered.scalars().all())

    async def collect_orgs_needing_enrichment(self) -> list[uuid.UUID]:
        """Person-linked or monitored orgs outside the enrichment cooldown window."""
        cutoff: datetime = datetime.now(tz=UTC) - timedelta(
            days=self._settings.org_enrichment_cooldown_days,
        )
        recently_enriched = (
            select(OrgEnrichmentScrapeRun.org_id)
            .where(
                OrgEnrichmentScrapeRun.completed_at >= cutoff,
                OrgEnrichmentScrapeRun.error.is_(None),
            )
            .distinct()
        )
        person_linked = await self._db.execute(
            select(Org.id)
            .join(Person, Person.current_org_id == Org.id)
            .where(Org.id.not_in(recently_enriched))
            .group_by(Org.id),
        )
        org_ids: set[uuid.UUID] = set(person_linked.scalars().all())
        monitored: set[uuid.UUID] = await self._collect_monitored_org_ids()
        if monitored:
            recently_ids = await self._db.execute(recently_enriched)
            recently_set: set[uuid.UUID] = set(recently_ids.scalars().all())
            org_ids |= monitored - recently_set
        if not org_ids:
            return []
        ordered = await self._db.execute(
            select(Org.id)
            .where(Org.id.in_(org_ids))
            .order_by(Org.canonical_name.asc()),
        )
        return list(ordered.scalars().all())

    async def was_recently_enriched(self, org_id: uuid.UUID) -> bool:
        cutoff: datetime = datetime.now(tz=UTC) - timedelta(
            days=self._settings.org_enrichment_cooldown_days,
        )
        result = await self._db.execute(
            select(OrgEnrichmentScrapeRun.id)
            .where(
                OrgEnrichmentScrapeRun.org_id == org_id,
                OrgEnrichmentScrapeRun.completed_at >= cutoff,
                OrgEnrichmentScrapeRun.error.is_(None),
            )
            .limit(1),
        )
        if result.scalar_one_or_none() is not None:
            return True

        org: Org | None = await self._db.get(Org, org_id)
        if org is None:
            return False
        enriched_at_raw: object | None = (org.attributes or {}).get("exa_enriched_at")
        if not isinstance(enriched_at_raw, str):
            return False
        try:
            enriched_at: datetime = datetime.fromisoformat(enriched_at_raw)
        except ValueError:
            return False
        if enriched_at.tzinfo is None:
            enriched_at = enriched_at.replace(tzinfo=UTC)
        return enriched_at >= cutoff

    async def enrich_org_global(
        self,
        org_id: uuid.UUID,
        *,
        force: bool = False,
    ) -> EnrichOrgResult:
        """Enrich one org and record an OrgEnrichmentScrapeRun."""
        if not self._settings.exa_api_key:
            return EnrichOrgResult(
                fields_updated=0,
                source="none",
                error="Exa API key is not configured.",
                enriched=False,
            )

        if not force and await self.was_recently_enriched(org_id):
            return EnrichOrgResult(
                fields_updated=0,
                source="none",
                error=None,
                enriched=False,
            )

        org: Org | None = await self._db.get(Org, org_id)
        if org is None:
            return EnrichOrgResult(
                fields_updated=0,
                source="none",
                error=None,
                enriched=False,
            )

        started_at: datetime = datetime.now(tz=UTC)
        source: str = "exa"
        error: str | None = None
        fields_updated: int = 0

        try:
            fields_updated = await self._enrich_one_org(org)
        except Exception as exc:
            error = str(exc)[:500]
            logger.exception("Org enrichment failed for org %s", org_id)

        actually_enriched: bool = error is None
        if actually_enriched or error is not None:
            scrape_run = OrgEnrichmentScrapeRun(
                org_id=org.id,
                source=source,
                started_at=started_at,
                completed_at=datetime.now(tz=UTC),
                fields_updated=fields_updated,
                error=error,
            )
            self._db.add(scrape_run)

        await self._db.commit()
        return EnrichOrgResult(
            fields_updated=fields_updated,
            source=source,
            error=error,
            enriched=actually_enriched,
        )

    async def _enrich_one_org(self, org: Org) -> int:
        before: _OrgEnrichmentSnapshot = _org_enrichment_snapshot(org)
        summary_query: str = build_company_summary_query(org.canonical_name)
        company_hits, careers_hits = await asyncio.gather(
            self._exa.search_company_enrichment(
                query=f'"{org.canonical_name}" company',
                summary_query=summary_query,
                summary_schema=exa_company_summary_schema(),
                num_results=5,
            ),
            self._exa.search_raw(
                query=f'"{org.canonical_name}" careers jobs',
                num_results=5,
            ),
        )

        parsed = parse_org_enrichment_hits(
            company_name=org.canonical_name,
            company_hits=company_hits,
            careers_hits=careers_hits,
        )

        if parsed.primary_domain is not None:
            org.primary_domain = parsed.primary_domain
        if parsed.description is not None:
            org.description = parsed.description
        if parsed.careers_url is not None:
            org.careers_url = parsed.careers_url
        apply_ats_detection_to_org(org)
        if parsed.linkedin_url is not None:
            org.linkedin_url = parsed.linkedin_url
        if parsed.categories:
            org.categories = parsed.categories
        if parsed.employee_count is not None:
            org.employee_count = parsed.employee_count
        if parsed.company_size_band is not None:
            org.company_size_band = parsed.company_size_band
        if parsed.funding_stage is not None:
            org.funding_stage = parsed.funding_stage

        attributes: dict[str, object] = dict(org.attributes or {})
        attributes["exa_enriched_at"] = datetime.now(tz=UTC).isoformat()
        org.attributes = attributes
        after: _OrgEnrichmentSnapshot = _org_enrichment_snapshot(org)
        return _count_snapshot_changes(before, after)

    async def _list_unenriched_user_org_ids(self, user_id: uuid.UUID) -> list[uuid.UUID]:
        org_ids: list[uuid.UUID] = await self._list_user_org_ids(user_id)
        unenriched_org_ids: list[uuid.UUID] = []
        for org_id in org_ids:
            if not await self.was_recently_enriched(org_id):
                unenriched_org_ids.append(org_id)
        return unenriched_org_ids

    async def _list_user_org_ids(self, user_id: uuid.UUID) -> list[uuid.UUID]:
        result = await self._db.execute(
            select(Org.id)
            .join(Person, Person.current_org_id == Org.id)
            .where(*self._strong_tie_person_filter(user_id))
            .group_by(Org.id)
            .order_by(Org.canonical_name.asc())
        )
        return [row[0] for row in result.all()]

    async def _count_user_orgs(self, user_id: uuid.UUID) -> int:
        result = await self._db.execute(
            select(Org.id)
            .join(Person, Person.current_org_id == Org.id)
            .where(*self._strong_tie_person_filter(user_id))
            .group_by(Org.id)
        )
        return len(result.all())

    async def _count_enriched_orgs(self, user_id: uuid.UUID) -> int:
        org_ids: list[uuid.UUID] = await self._list_user_org_ids(user_id)
        enriched_count: int = 0
        for org_id in org_ids:
            if await self.was_recently_enriched(org_id):
                enriched_count += 1
        return enriched_count

    @staticmethod
    def _strong_tie_person_filter(user_id: uuid.UUID):  # noqa: ANN205
        return (
            exists(
                select(UserPersonObservation.person_id).where(
                    UserPersonObservation.user_id == user_id,
                    UserPersonObservation.person_id == Person.id,
                    UserPersonObservation.relationship_types.any(PHONE_RELATIONSHIP),
                ).correlate(Person)
            ),
            exists(
                select(UserPersonObservation.person_id).where(
                    UserPersonObservation.user_id == user_id,
                    UserPersonObservation.person_id == Person.id,
                    UserPersonObservation.relationship_types.any(
                        LINKEDIN_CONNECTIONS_RELATIONSHIP,
                    ),
                ).correlate(Person)
            ),
            exists(
                select(PersonAlias.person_id).where(
                    PersonAlias.person_id == Person.id,
                    PersonAlias.kind == "linkedin_url",
                ).correlate(Person)
            ),
        )

    async def _latest_run(self, user_id: uuid.UUID) -> OrgEnrichmentRun | None:
        result = await self._db.execute(
            select(OrgEnrichmentRun)
            .where(OrgEnrichmentRun.user_id == user_id)
            .order_by(OrgEnrichmentRun.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def _has_running_run(self, user_id: uuid.UUID) -> bool:
        run: OrgEnrichmentRun | None = await self._latest_run(user_id)
        if run is None or run.state != "running":
            return False
        await self._recover_stale_run(run)
        return run.state == "running"

    @staticmethod
    def _progress_message(orgs_enriched: int, orgs_total: int) -> str:
        return f"Enriched {orgs_enriched} of {orgs_total} companies"

    @staticmethod
    def _status_message(
        state: OrgEnrichmentState,
        orgs_enriched: int,
        orgs_total: int,
    ) -> str:
        if state == "running":
            return f"Enriching companies ({orgs_enriched}/{orgs_total})…"
        if state == "complete":
            return f"Company enrichment complete ({orgs_enriched}/{orgs_total})."
        if state == "failed":
            return "Company enrichment failed."
        if orgs_total == 0:
            return "No organizations to enrich yet."
        if orgs_enriched >= orgs_total:
            return f"{orgs_enriched}/{orgs_total} companies enriched."
        return f"{orgs_enriched}/{orgs_total} companies enriched so far."


@dataclass(frozen=True, slots=True)
class ParsedOrgEnrichment:
    primary_domain: str | None
    description: str | None
    careers_url: str | None
    linkedin_url: str | None
    categories: list[str]
    employee_count: int | None
    company_size_band: str | None
    funding_stage: str | None


def parse_org_enrichment_hits(
    *,
    company_name: str,
    company_hits: list[WebSearchHit],
    careers_hits: list[WebSearchHit],
) -> ParsedOrgEnrichment:
    linkedin_url: str | None = _pick_linkedin_company_url(company_hits + careers_hits)
    careers_url: str | None = _pick_careers_url(careers_hits + company_hits)
    primary_domain: str | None = _pick_primary_domain(company_hits, company_name)
    description: str | None = _pick_description(company_hits, company_name)
    categories: list[str] = _pick_industry_tags(company_hits, company_name, description)
    company_size: ParsedCompanySize = _pick_company_size(company_hits)
    funding_stage: str | None = _pick_funding_stage(company_hits)
    return ParsedOrgEnrichment(
        primary_domain=primary_domain,
        description=description,
        careers_url=careers_url,
        linkedin_url=linkedin_url,
        categories=categories,
        employee_count=company_size.employee_count,
        company_size_band=company_size.company_size_band,
        funding_stage=funding_stage,
    )


def _org_enrichment_snapshot(org: Org) -> _OrgEnrichmentSnapshot:
    return _OrgEnrichmentSnapshot(
        primary_domain=org.primary_domain,
        description=org.description,
        careers_url=org.careers_url,
        linkedin_url=org.linkedin_url,
        categories=tuple(org.categories),
        employee_count=org.employee_count,
        company_size_band=org.company_size_band,
        funding_stage=org.funding_stage,
        ats_provider=org.ats_provider,
        ats_board_token=org.ats_board_token,
    )


def _count_snapshot_changes(
    before: _OrgEnrichmentSnapshot,
    after: _OrgEnrichmentSnapshot,
) -> int:
    changes: int = 0
    if before.primary_domain != after.primary_domain:
        changes += 1
    if before.description != after.description:
        changes += 1
    if before.careers_url != after.careers_url:
        changes += 1
    if before.linkedin_url != after.linkedin_url:
        changes += 1
    if before.categories != after.categories:
        changes += 1
    if before.employee_count != after.employee_count:
        changes += 1
    if before.company_size_band != after.company_size_band:
        changes += 1
    if before.funding_stage != after.funding_stage:
        changes += 1
    if before.ats_provider != after.ats_provider:
        changes += 1
    if before.ats_board_token != after.ats_board_token:
        changes += 1
    return changes


def _org_is_enriched(org: Org) -> bool:
    if org.attributes.get("exa_enriched_at") is not None:
        return True
    return (
        org.description is not None
        and org.linkedin_url is not None
        and org.careers_url is not None
    )


def _pick_linkedin_company_url(hits: list[WebSearchHit]) -> str | None:
    for hit in hits:
        if hit.url and _LINKEDIN_COMPANY_RE.match(hit.url):
            return hit.url.split("?", maxsplit=1)[0]
    return None


def _pick_careers_url(hits: list[WebSearchHit]) -> str | None:
    for hit in hits:
        if not hit.url:
            continue
        parsed = urlparse(hit.url)
        if _CAREERS_PATH_RE.search(parsed.path):
            return hit.url.split("?", maxsplit=1)[0]
    return None


def _pick_primary_domain(hits: list[WebSearchHit], company_name: str) -> str | None:
    normalized_name: str = _normalize_company_name(company_name)
    for hit in hits:
        domain: str | None = _domain_from_url(hit.url)
        if domain is None or _is_skipped_domain(domain):
            continue
        if normalized_name and normalized_name in _normalize_company_name(domain):
            return domain
        if normalized_name and normalized_name in _normalize_company_name(hit.title):
            return domain
    for hit in hits:
        domain = _domain_from_url(hit.url)
        if domain is not None and not _is_skipped_domain(domain):
            return domain
    return None


_ELLIPSIS_MARKER_RE: re.Pattern[str] = re.compile(r"\[\s*(?:\.\.\.|…)\s*\]")
_MARKDOWN_LINK_RE: re.Pattern[str] = re.compile(r"\[([^\]]+)\]\([^)]+\)")
_MARKDOWN_HEADER_RE: re.Pattern[str] = re.compile(r"^#{1,6}\s*")
_DESCRIPTION_MAX_LEN: int = 220


def _clean_org_description(text: str) -> str:
    lines: list[str] = []
    for raw_line in text.splitlines():
        line: str = raw_line.strip()
        if not line:
            continue
        line = _MARKDOWN_HEADER_RE.sub("", line)
        line = re.sub(r"\s+#+\s*", " ", line)
        line = _ELLIPSIS_MARKER_RE.sub(" ", line)
        line = _MARKDOWN_LINK_RE.sub(r"\1", line)
        line = re.sub(r"\*\*([^*]+)\*\*", r"\1", line)
        line = re.sub(r"\s+", " ", line).strip(" ·|-")
        if line:
            lines.append(line)
    return re.sub(r"\s+", " ", " ".join(lines)).strip()


def _truncate_at_word(text: str, max_len: int) -> str:
    if len(text) <= max_len:
        return text
    truncated: str = text[:max_len]
    last_space: int = truncated.rfind(" ")
    if last_space > max_len // 2:
        truncated = truncated[:last_space]
    return truncated.rstrip(".,;:- ") + "…"


def _summarize_description(text: str, *, max_len: int = _DESCRIPTION_MAX_LEN) -> str:
    cleaned: str = _clean_org_description(text)
    if not cleaned:
        return ""
    sentences: list[str] = [
        part.strip()
        for part in re.split(r"(?<=[.!?])\s+", cleaned)
        if part.strip()
    ]
    if sentences:
        summary: str = sentences[0]
        for sentence in sentences[1:3]:
            candidate: str = f"{summary} {sentence}".strip()
            if len(candidate) > max_len:
                break
            summary = candidate
        return _truncate_at_word(summary, max_len)
    return _truncate_at_word(cleaned, max_len)


def _description_quality_score(text: str) -> int:
    score: int = min(len(text), 400)
    score -= text.count("[...]") * 40
    score -= text.count("#") * 8
    score -= sum(1 for ch in text if ch in "[]{}") * 4
    if text.endswith("…"):
        score += 10
    return score


def _is_valid_description(text: str, normalized_company: str) -> bool:
    if len(text) < 40:
        return False
    if normalized_company not in text.lower() and len(text) < 80:
        return False
    return True


def _pick_description(hits: list[WebSearchHit], company_name: str) -> str | None:
    normalized_company: str = company_name.lower()

    for hit in hits:
        structured = parse_structured_company_summary(hit.summary)
        if structured is not None and structured.description:
            summary: str = _summarize_description(structured.description)
            if len(summary) >= 20:
                return summary
        if not hit.summary.strip():
            continue
        summary = _summarize_description(hit.summary)
        if _is_valid_description(summary, normalized_company):
            return summary

    best: str | None = None
    best_score: int = -1
    for hit in hits:
        if not hit.text.strip():
            continue
        candidate: str = _summarize_description(hit.text)
        if not _is_valid_description(candidate, normalized_company):
            continue
        score: int = _description_quality_score(candidate)
        if score > best_score:
            best_score = score
            best = candidate

    return best


def _pick_industry_tags(
    hits: list[WebSearchHit],
    company_name: str,
    description: str | None,
) -> list[str]:
    for hit in hits:
        structured = parse_structured_company_summary(hit.summary)
        if structured is not None and structured.industries:
            return list(structured.industries)

    fallback_texts: list[str] = [company_name]
    if description:
        fallback_texts.append(description)
    for hit in hits:
        if hit.text.strip():
            fallback_texts.append(hit.text)
        fallback_texts.extend(hit.highlights)
    return infer_industry_tags_from_text(*fallback_texts)


def _pick_company_size(hits: list[WebSearchHit]) -> ParsedCompanySize:
    for hit in hits:
        if hit.employee_count is not None and hit.employee_count > 0:
            band: str | None = headcount_to_linkedin_band(hit.employee_count)
            return ParsedCompanySize(
                employee_count=hit.employee_count,
                company_size_band=band,
            )

    for hit in hits:
        structured = parse_structured_company_summary(hit.summary)
        if structured is not None and structured.company_size_band is not None:
            return ParsedCompanySize(
                employee_count=None,
                company_size_band=structured.company_size_band,
            )

    return ParsedCompanySize(employee_count=None, company_size_band=None)


def _pick_funding_stage(hits: list[WebSearchHit]) -> str | None:
    for hit in hits:
        structured = parse_structured_company_summary(hit.summary)
        if structured is not None and structured.funding_stage is not None:
            return structured.funding_stage
    return None


def _domain_from_url(url: str) -> str | None:
    if not url:
        return None
    parsed = urlparse(url)
    host: str = (parsed.hostname or "").lower().removeprefix("www.")
    if not host or "." not in host:
        return None
    return host


def _is_skipped_domain(domain: str) -> bool:
    for skipped in _SKIP_DOMAINS:
        if domain == skipped or domain.endswith(f".{skipped}"):
            return True
    return False


def _normalize_company_name(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def schedule_org_enrichment(user_id: uuid.UUID, run_id: uuid.UUID) -> bool:
    from contactsafe_server.config import get_settings

    if get_settings().use_arq_worker:

        async def _enqueue() -> None:
            from contactsafe_server.queue import enqueue_background_job

            await enqueue_background_job(
                "enrich_user_orgs",
                str(user_id),
                str(run_id),
                _job_id=f"enrich-user-orgs-{user_id}",
            )

        asyncio.create_task(
            _enqueue(),
            name=f"org-enrichment-enqueue-{user_id}",
        )
        return True

    with _scheduling_lock:
        if user_id in _active_org_enrichment_user_ids:
            return False
        _active_org_enrichment_user_ids.add(user_id)
    asyncio.create_task(
        _run_org_enrichment_task(user_id, run_id),
        name=f"org-enrichment-{user_id}",
    )
    return True


def is_org_enrichment_running(user_id: uuid.UUID) -> bool:
    with _scheduling_lock:
        return user_id in _active_org_enrichment_user_ids


def release_org_enrichment_lock(user_id: uuid.UUID) -> None:
    with _scheduling_lock:
        _active_org_enrichment_user_ids.discard(user_id)


async def _run_org_enrichment_task(user_id: uuid.UUID, run_id: uuid.UUID) -> None:
    from contactsafe_server.deps import build_app_context

    ctx = build_app_context()
    factory = ctx.session_factory
    try:
        async with factory() as db:
            service = OrgEnrichmentService(db, ctx.settings)
            await service.enrich_orgs(user_id, run_id)
    except Exception as exc:
        logger.exception("Background org enrichment failed for user %s", user_id)
        try:
            async with factory() as db:
                run: OrgEnrichmentRun | None = await db.get(OrgEnrichmentRun, run_id)
                if run is not None:
                    run.state = "failed"
                    run.error = str(exc)[:500]
                    run.completed_at = datetime.now(tz=UTC)
                    run.progress_message = None
                    await db.commit()
                    publish_org_enrichment_failed(
                        user_id,
                        orgs_enriched=run.orgs_enriched,
                        orgs_total=run.orgs_total,
                        error=run.error,
                    )
        except Exception:
            logger.exception("Failed to mark org enrichment run %s as failed", run_id)
    finally:
        release_org_enrichment_lock(user_id)
