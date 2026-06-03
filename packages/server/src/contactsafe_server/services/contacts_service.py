from __future__ import annotations

import uuid
from collections import defaultdict

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from contactsafe_core.contact_schemas import (
    ListOrgsResult,
    ListPeopleResult,
    OrgDetailResult,
    OrgListItem,
    OrgPersonSummary,
    PersonDetailResult,
    PersonListItem,
    split_display_name,
)
from contactsafe_core.enums import IdentityKind
from contactsafe_server.db.models import (
    EmploymentClaim,
    Org,
    Person,
    PersonAlias,
    Source,
    UserPersonObservation,
)


class ContactsService:
    def __init__(self, db: AsyncSession) -> None:
        self._db: AsyncSession = db

    async def list_people(self, user_id: uuid.UUID) -> ListPeopleResult:
        result = await self._db.execute(
            select(Person, UserPersonObservation, Source)
            .join(
                UserPersonObservation,
                (UserPersonObservation.person_id == Person.id)
                & (UserPersonObservation.user_id == user_id),
            )
            .outerjoin(Source, Source.id == UserPersonObservation.source_id)
            .order_by(
                UserPersonObservation.last_observed_at.desc().nullslast(),
                Person.canonical_name.asc(),
            )
        )
        rows: list[tuple[Person, UserPersonObservation, Source | None]] = list(
            result.all()
        )
        if not rows:
            return ListPeopleResult(
                people=[],
                total=0,
                message="No contacts in your graph yet. Connect a source and run sync.",
            )

        person_ids: list[uuid.UUID] = [person.id for person, _, _ in rows]
        emails_by_person: dict[uuid.UUID, list[str]] = await self._load_emails_by_person(
            person_ids
        )
        sources_by_person: dict[uuid.UUID, list[str]] = await self._load_sources_by_person(
            user_id,
            person_ids,
        )

        people: list[PersonListItem] = []
        for person, obs, source in rows:
            first_name, last_name = split_display_name(person.canonical_name)
            emails: list[str] = self._collect_emails(
                person,
                emails_by_person.get(person.id, []),
            )
            source_labels: list[str] = list(
                dict.fromkeys(
                    [
                        *(sources_by_person.get(person.id, [])),
                        *([source.label] if source is not None else []),
                    ]
                )
            )
            phone: str | None = person.phone_numbers[0] if person.phone_numbers else None

            people.append(
                PersonListItem(
                    person_id=person.id,
                    first_name=first_name,
                    last_name=last_name,
                    display_name=person.canonical_name,
                    primary_email=person.primary_email,
                    phone=phone,
                    org_name=person.current_org_name,
                    current_role=person.current_role,
                    emails=emails,
                    sources=source_labels,
                    first_contact_at=obs.first_observed_at,
                    last_contact_at=obs.last_observed_at,
                    tie_strength_score=obs.tie_strength_score,
                    is_human=obs.is_human,
                    is_broadcast=obs.is_broadcast,
                    is_automated=obs.is_automated,
                )
            )

        return ListPeopleResult(
            people=people,
            total=len(people),
            message=f"Found {len(people)} contact(s) in your graph.",
        )

    async def get_person(
        self,
        user_id: uuid.UUID,
        person_id: uuid.UUID,
    ) -> PersonDetailResult | None:
        result = await self._db.execute(
            select(Person, UserPersonObservation, Source)
            .join(
                UserPersonObservation,
                (UserPersonObservation.person_id == Person.id)
                & (UserPersonObservation.user_id == user_id),
            )
            .outerjoin(Source, Source.id == UserPersonObservation.source_id)
            .where(Person.id == person_id)
        )
        row: tuple[Person, UserPersonObservation, Source | None] | None = result.one_or_none()
        if row is None:
            return None

        person, obs, source = row
        emails_by_person: dict[uuid.UUID, list[str]] = await self._load_emails_by_person(
            [person_id]
        )
        sources_by_person: dict[uuid.UUID, list[str]] = await self._load_sources_by_person(
            user_id,
            [person_id],
        )

        first_name, last_name = split_display_name(person.canonical_name)
        emails: list[str] = self._collect_emails(
            person,
            emails_by_person.get(person_id, []),
        )
        source_labels: list[str] = list(
            dict.fromkeys(
                [
                    *(sources_by_person.get(person_id, [])),
                    *([source.label] if source is not None else []),
                ]
            )
        )
        phones: list[str] = list(dict.fromkeys(person.phone_numbers or []))
        web_links: list[str] = list(dict.fromkeys(person.social_profiles.values()))

        return PersonDetailResult(
            person_id=person.id,
            first_name=first_name,
            last_name=last_name,
            display_name=person.canonical_name,
            primary_email=person.primary_email,
            phone=phones[0] if phones else None,
            phones=phones,
            emails=emails,
            org_name=person.current_org_name,
            org_id=person.current_org_id,
            current_role=person.current_role,
            location=person.location,
            bio_summary=person.bio_summary,
            inferred_categories=list(person.inferred_categories or []),
            descriptive_tags=list(person.descriptive_tags or []),
            social_profiles=dict(person.social_profiles or {}),
            web_links=web_links,
            sources=source_labels,
            first_contact_at=obs.first_observed_at,
            last_contact_at=obs.last_observed_at,
            last_genuine_interaction_at=obs.last_genuine_interaction_at,
            tie_strength_score=obs.tie_strength_score,
            email_count=obs.email_count,
            is_human=obs.is_human,
            is_broadcast=obs.is_broadcast,
            is_automated=obs.is_automated,
            message=f"Contact details for {person.canonical_name}.",
        )

    async def list_orgs(self, user_id: uuid.UUID) -> ListOrgsResult:
        result = await self._db.execute(
            select(
                Org,
                func.count(Person.id.distinct()).label("contact_count"),
            )
            .join(Person, Person.current_org_id == Org.id)
            .join(
                UserPersonObservation,
                (UserPersonObservation.person_id == Person.id)
                & (UserPersonObservation.user_id == user_id),
            )
            .group_by(Org.id)
            .order_by(Org.canonical_name.asc())
        )
        rows: list[tuple[Org, int]] = [(org, int(count)) for org, count in result.all()]
        if not rows:
            return ListOrgsResult(
                orgs=[],
                total=0,
                message="No organizations resolved yet.",
            )

        orgs: list[OrgListItem] = [
            OrgListItem(
                org_id=org.id,
                name=org.canonical_name,
                primary_domain=org.primary_domain,
                categories=list(org.categories or []),
                contact_count=count,
            )
            for org, count in rows
        ]
        return ListOrgsResult(
            orgs=orgs,
            total=len(orgs),
            message=f"Found {len(orgs)} organization(s) in your graph.",
        )

    async def get_org(
        self,
        user_id: uuid.UUID,
        org_id: uuid.UUID,
    ) -> OrgDetailResult | None:
        org: Org | None = await self._db.get(
            Org,
            org_id,
            options=(selectinload(Org.aliases),),
        )
        if org is None:
            return None

        people_result = await self._db.execute(
            select(Person)
            .join(
                UserPersonObservation,
                (UserPersonObservation.person_id == Person.id)
                & (UserPersonObservation.user_id == user_id),
            )
            .where(Person.current_org_id == org_id)
            .order_by(Person.canonical_name.asc())
        )
        people_rows: list[Person] = list(people_result.scalars().all())
        if not people_rows:
            return None

        alias_values: list[str] = [alias.value for alias in org.aliases]

        return OrgDetailResult(
            org_id=org.id,
            name=org.canonical_name,
            primary_domain=org.primary_domain,
            categories=list(org.categories or []),
            attributes=dict(org.attributes or {}),
            aliases=alias_values,
            people=[
                OrgPersonSummary(
                    person_id=person.id,
                    display_name=person.canonical_name,
                    primary_email=person.primary_email,
                    current_role=person.current_role,
                )
                for person in people_rows
            ],
            contact_count=len(people_rows),
            message=f"Organization details for {org.canonical_name}.",
        )

    async def _load_emails_by_person(
        self,
        person_ids: list[uuid.UUID],
    ) -> dict[uuid.UUID, list[str]]:
        if not person_ids:
            return {}
        result = await self._db.execute(
            select(PersonAlias.person_id, PersonAlias.value).where(
                PersonAlias.person_id.in_(person_ids),
                PersonAlias.kind == IdentityKind.EMAIL.value,
            )
        )
        emails_by_person: dict[uuid.UUID, list[str]] = defaultdict(list)
        for person_id, value in result.all():
            emails_by_person[person_id].append(value)
        return dict(emails_by_person)

    async def _load_sources_by_person(
        self,
        user_id: uuid.UUID,
        person_ids: list[uuid.UUID],
    ) -> dict[uuid.UUID, list[str]]:
        if not person_ids:
            return {}
        result = await self._db.execute(
            select(EmploymentClaim.person_id, EmploymentClaim.contributor_source_kind)
            .where(
                EmploymentClaim.person_id.in_(person_ids),
                EmploymentClaim.contributor_user_id == user_id,
            )
            .distinct()
        )
        sources_by_person: dict[uuid.UUID, list[str]] = defaultdict(list)
        for person_id, source_kind in result.all():
            if source_kind:
                sources_by_person[person_id].append(str(source_kind))
        return dict(sources_by_person)

    @staticmethod
    def _collect_emails(person: Person, alias_emails: list[str]) -> list[str]:
        emails: list[str] = []
        if person.primary_email:
            emails.append(person.primary_email)
        for email in alias_emails:
            if email not in emails:
                emails.append(email)
        return emails
