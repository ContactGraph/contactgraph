"""API-facing helpers for strong-tie network UX."""

from __future__ import annotations

import uuid
from collections import defaultdict

from sqlalchemy import Select, and_, exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from contactsafe_core.contact_schemas import (
    EnrichStrongTiesResult,
    ListStrongTiesResult,
    NetworkStatusResult,
    ScrapingDogEnrichmentStatusResult,
    StrongTieCompaniesResult,
    StrongTieCompanyInsider,
    StrongTieCompanySummary,
    StrongTieCountResult,
    StrongTieItem,
)
from contactsafe_core.enums import EnrichmentQueueStatus
from contactsafe_server.config import Settings
from contactsafe_server.db.models import (
    EmploymentClaim,
    EnrichmentQueueItem,
    Person,
    PersonAlias,
    Source,
    UserPersonObservation,
)
from contactsafe_server.services.enrichment_queue_service import EnrichmentQueueService
from contactsafe_server.services.strong_tie_matcher import (
    LINKEDIN_CONNECTIONS_RELATIONSHIP,
    SCRAPINGDOG_SOURCE_KIND,
    count_strong_ties,
    find_strong_ties,
)

PHONE_RELATIONSHIP: str = "phone_contacts_upload"


def _phone_observation_exists(user_id: uuid.UUID) -> exists:
    return exists(
        select(UserPersonObservation.person_id).where(
            UserPersonObservation.user_id == user_id,
            UserPersonObservation.person_id == Person.id,
            UserPersonObservation.relationship_types.any(PHONE_RELATIONSHIP),
        )
    ).correlate(Person)


def _linkedin_observation_exists(user_id: uuid.UUID) -> exists:
    return exists(
        select(UserPersonObservation.person_id).where(
            UserPersonObservation.user_id == user_id,
            UserPersonObservation.person_id == Person.id,
            UserPersonObservation.relationship_types.any(LINKEDIN_CONNECTIONS_RELATIONSHIP),
        )
    ).correlate(Person)


def _gmail_match_exists(user_id: uuid.UUID) -> exists:
    return exists(
        select(UserPersonObservation.person_id).where(
            UserPersonObservation.user_id == user_id,
            UserPersonObservation.person_id == Person.id,
            UserPersonObservation.is_human.is_(True),
            UserPersonObservation.is_broadcast.is_(False),
            UserPersonObservation.is_automated.is_(False),
            UserPersonObservation.email_count > 0,
        )
    ).correlate(Person)


def _linkedin_alias_exists() -> exists:
    return exists(
        select(PersonAlias.person_id).where(
            PersonAlias.person_id == Person.id,
            PersonAlias.kind == "linkedin_url",
        )
    ).correlate(Person)


def _scrapingdog_claim_exists() -> exists:
    return exists(
        select(EmploymentClaim.person_id).where(
            EmploymentClaim.person_id == Person.id,
            EmploymentClaim.contributor_source_kind == SCRAPINGDOG_SOURCE_KIND,
        )
    ).correlate(Person)


class StrongTieApiService:
    def __init__(self, db: AsyncSession, settings: Settings) -> None:
        self._db: AsyncSession = db
        self._settings: Settings = settings

    async def list_strong_ties(
        self,
        user_id: uuid.UUID,
        *,
        limit: int | None = None,
    ) -> ListStrongTiesResult:
        matches = await find_strong_ties(
            self._db,
            user_id,
            skip_already_scraped=False,
            limit=limit,
        )
        items: list[StrongTieItem] = [
            StrongTieItem(
                person_id=match.person_id,
                name=match.canonical_name,
                email=match.primary_email,
                phone=match.phone_number,
                linkedin_url=match.linkedin_url,
                tie_strength_score=match.tie_strength_score,
                current_company=match.current_org_name,
                current_role=match.current_role,
                scrapingdog_enriched=match.already_scraped,
            )
            for match in matches
        ]
        return ListStrongTiesResult(
            strong_ties=items,
            total=len(items),
            message=f"Found {len(items)} strong professional tie(s) in your network.",
        )

    async def count_strong_ties(self, user_id: uuid.UUID) -> StrongTieCountResult:
        total: int = await count_strong_ties(
            self._db,
            user_id,
            skip_already_scraped=False,
        )
        pending: int = await count_strong_ties(
            self._db,
            user_id,
            skip_already_scraped=True,
        )
        enriched: int = total - pending
        return StrongTieCountResult(
            total=total,
            pending_enrichment=pending,
            enriched=enriched,
            message=f"{total} strong professional tie(s); {enriched} enriched.",
        )

    async def list_companies(self, user_id: uuid.UUID) -> StrongTieCompaniesResult:
        matches = await find_strong_ties(
            self._db,
            user_id,
            skip_already_scraped=False,
        )
        grouped: dict[str, list[StrongTieCompanyInsider]] = defaultdict(list)
        org_ids: dict[str, uuid.UUID | None] = {}
        person_ids: list[uuid.UUID] = [match.person_id for match in matches]
        org_id_by_person: dict[uuid.UUID, uuid.UUID | None] = {}
        if person_ids:
            person_rows = await self._db.execute(
                select(Person.id, Person.current_org_id).where(Person.id.in_(person_ids))
            )
            org_id_by_person = {
                person_id: current_org_id
                for person_id, current_org_id in person_rows.all()
            }

        for match in matches:
            company_name: str = (match.current_org_name or "").strip()
            if not company_name:
                continue
            grouped[company_name].append(
                StrongTieCompanyInsider(
                    person_id=match.person_id,
                    person_name=match.canonical_name,
                    person_role=match.current_role,
                    tie_strength_score=match.tie_strength_score,
                )
            )
            if company_name not in org_ids:
                org_ids[company_name] = org_id_by_person.get(match.person_id)

        companies: list[StrongTieCompanySummary] = []
        for company_name, insiders in grouped.items():
            sorted_insiders: list[StrongTieCompanyInsider] = sorted(
                insiders,
                key=lambda insider: insider.tie_strength_score,
                reverse=True,
            )
            companies.append(
                StrongTieCompanySummary(
                    org_id=org_ids.get(company_name),
                    company_name=company_name,
                    insider_count=len(sorted_insiders),
                    insiders=sorted_insiders,
                    best_tie_strength=max(
                        insider.tie_strength_score for insider in sorted_insiders
                    ),
                )
            )

        companies.sort(key=lambda company: company.best_tie_strength, reverse=True)
        return StrongTieCompaniesResult(
            companies=companies,
            total=len(companies),
            message=f"Your strong professional ties work at {len(companies)} companies.",
        )

    async def enrich_strong_ties(self, user_id: uuid.UUID) -> EnrichStrongTiesResult:
        if not self._settings.scrapingdog_api_key:
            return EnrichStrongTiesResult(
                enqueued=0,
                message="SCRAPINGDOG_API_KEY is not configured.",
            )

        matches = await find_strong_ties(
            self._db,
            user_id,
            skip_already_scraped=True,
        )
        if not matches:
            return EnrichStrongTiesResult(
                enqueued=0,
                message="No strong professional ties need LinkedIn enrichment.",
            )

        queue = EnrichmentQueueService(self._db, self._settings)
        enqueued: int = await queue.enqueue_strong_tie_scrapes(
            user_id=user_id,
            person_ids=[match.person_id for match in matches],
        )
        return EnrichStrongTiesResult(
            enqueued=enqueued,
            message=f"Queued LinkedIn enrichment for {enqueued} strong professional tie(s).",
        )

    async def scrapingdog_status(self, user_id: uuid.UUID) -> ScrapingDogEnrichmentStatusResult:
        total: int = await count_strong_ties(
            self._db,
            user_id,
            skip_already_scraped=False,
        )
        enriched_count: int = await self._count_enriched_strong_ties(user_id)
        strong_tie_ids: list[uuid.UUID] = [
            match.person_id
            for match in await find_strong_ties(
                self._db,
                user_id,
                skip_already_scraped=False,
            )
        ]

        status_counts: dict[str, int] = {
            EnrichmentQueueStatus.PENDING.value: 0,
            EnrichmentQueueStatus.IN_PROGRESS.value: 0,
            EnrichmentQueueStatus.COMPLETE.value: 0,
            EnrichmentQueueStatus.FAILED.value: 0,
            EnrichmentQueueStatus.DEFERRED.value: 0,
        }
        if strong_tie_ids:
            result = await self._db.execute(
                select(EnrichmentQueueItem.status, func.count())
                .where(EnrichmentQueueItem.person_id.in_(strong_tie_ids))
                .group_by(EnrichmentQueueItem.status)
            )
            for status, count in result.all():
                status_counts[str(status)] = int(count)

        pending: int = (
            status_counts[EnrichmentQueueStatus.PENDING.value]
            + status_counts[EnrichmentQueueStatus.DEFERRED.value]
        )
        in_progress: int = status_counts[EnrichmentQueueStatus.IN_PROGRESS.value]
        complete: int = status_counts[EnrichmentQueueStatus.COMPLETE.value]
        failed: int = status_counts[EnrichmentQueueStatus.FAILED.value]

        if pending > 0 or in_progress > 0:
            state = "running"
            message = f"Enriching {complete + in_progress} of {total} strong professional ties."
        elif enriched_count > 0 and enriched_count >= total:
            state = "complete"
            message = f"Enriched {enriched_count} of {total} strong professional ties."
        elif enriched_count > 0:
            state = "partial"
            message = f"Enriched {enriched_count} of {total} strong professional ties."
        else:
            state = "idle"
            message = "LinkedIn enrichment has not started."

        return ScrapingDogEnrichmentStatusResult(
            state=state,
            total=total,
            pending=pending,
            in_progress=in_progress,
            complete=complete,
            failed=failed,
            enriched_count=enriched_count,
            message=message,
        )

    async def network_status(self, user_id: uuid.UUID) -> NetworkStatusResult:
        phone_contact_count: int = await self._count_phone_contacts(user_id)
        gmail_matched_count: int = await self._count_gmail_matched_phone_contacts(user_id)
        linkedin_matched_count: int = await self._count_linkedin_matched_phone_contacts(user_id)
        strong_tie_count: int = await count_strong_ties(
            self._db,
            user_id,
            skip_already_scraped=False,
        )
        enriched_strong_tie_count: int = await self._count_enriched_strong_ties(user_id)
        companies = await self.list_companies(user_id)

        phone_imported: bool = await self._source_imported(user_id, "phone_contacts_upload")
        gmail_connected: bool = await self._source_imported(user_id, "google_mail")
        linkedin_imported: bool = await self._source_imported(
            user_id,
            "linkedin_connections_upload",
        )

        if phone_contact_count == 0:
            message = "Import phone contacts to build your network."
        elif strong_tie_count == 0:
            message = "Connect Gmail or upload LinkedIn connections to find strong professional ties."
        else:
            message = (
                f"{phone_contact_count} contacts · {strong_tie_count} strong professional ties · "
                f"{enriched_strong_tie_count} enriched"
            )

        return NetworkStatusResult(
            phone_contact_count=phone_contact_count,
            gmail_matched_count=gmail_matched_count,
            linkedin_matched_count=linkedin_matched_count,
            strong_tie_count=strong_tie_count,
            enriched_strong_tie_count=enriched_strong_tie_count,
            target_company_count=companies.total,
            phone_imported=phone_imported,
            gmail_connected=gmail_connected,
            linkedin_imported=linkedin_imported,
            message=message,
        )

    async def _count_phone_contacts(self, user_id: uuid.UUID) -> int:
        stmt: Select[tuple[int]] = (
            select(func.count())
            .select_from(Person)
            .join(
                UserPersonObservation,
                and_(
                    UserPersonObservation.person_id == Person.id,
                    UserPersonObservation.user_id == user_id,
                ),
            )
            .where(_phone_observation_exists(user_id))
        )
        result = await self._db.execute(stmt)
        return int(result.scalar_one())

    async def _count_gmail_matched_phone_contacts(self, user_id: uuid.UUID) -> int:
        stmt: Select[tuple[int]] = (
            select(func.count())
            .select_from(Person)
            .join(
                UserPersonObservation,
                and_(
                    UserPersonObservation.person_id == Person.id,
                    UserPersonObservation.user_id == user_id,
                ),
            )
            .where(
                _phone_observation_exists(user_id),
                _gmail_match_exists(user_id),
            )
        )
        result = await self._db.execute(stmt)
        return int(result.scalar_one())

    async def _count_linkedin_matched_phone_contacts(self, user_id: uuid.UUID) -> int:
        stmt: Select[tuple[int]] = (
            select(func.count())
            .select_from(Person)
            .join(
                UserPersonObservation,
                and_(
                    UserPersonObservation.person_id == Person.id,
                    UserPersonObservation.user_id == user_id,
                ),
            )
            .where(
                _phone_observation_exists(user_id),
                _linkedin_observation_exists(user_id),
                _linkedin_alias_exists(),
            )
        )
        result = await self._db.execute(stmt)
        return int(result.scalar_one())

    async def _count_enriched_strong_ties(self, user_id: uuid.UUID) -> int:
        total: int = await count_strong_ties(
            self._db,
            user_id,
            skip_already_scraped=False,
        )
        pending: int = await count_strong_ties(
            self._db,
            user_id,
            skip_already_scraped=True,
        )
        return total - pending

    async def _source_imported(self, user_id: uuid.UUID, source_type: str) -> bool:
        result = await self._db.execute(
            select(Source.id)
            .where(
                Source.user_id == user_id,
                Source.source_type == source_type,
                Source.sync_state.in_(("complete", "partial")),
            )
            .limit(1)
        )
        return result.scalar_one_or_none() is not None
