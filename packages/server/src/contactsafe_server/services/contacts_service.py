from __future__ import annotations

import re
import uuid
from collections import defaultdict
from typing import Callable

from sqlalchemy import delete, exists, func, select
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
    UpdateOrgRequest,
    UpdatePersonRequest,
    split_display_name,
)
from contactsafe_core.enums import IdentityKind
from contactsafe_server.db.models import (
    EmploymentClaim,
    Org,
    Person,
    PersonAlias,
    PersonAttributeClaim,
    Source,
    UserPersonObservation,
)

from contactsafe_server.services.claim_writer import (
    record_employment,
    record_org_attribute,
    record_person_attribute,
)
from contactsafe_server.services.entity_resolution import EntityResolver
from contactsafe_server.services.person_profile_recompute import (
    PersonProfileRecompute,
    sanitize_display_name,
)
from contactsafe_server.services.phone_normalization import normalize_phone
from contactsafe_server.services.strong_tie_matcher import (
    LINKEDIN_CONNECTIONS_RELATIONSHIP,
    SCRAPINGDOG_SOURCE_KIND,
)

_MANUAL_SOURCE_KIND: str = "user_manual"
_MANUAL_CONFIDENCE: float = 1.0
_PLATFORM_CLEAN_RE: re.Pattern[str] = re.compile(r"[^a-z0-9_]+")


def normalize_social_platform(raw: str) -> str | None:
    cleaned: str = _PLATFORM_CLEAN_RE.sub(
        "",
        raw.strip().lower().replace(" ", "_").replace("-", "_"),
    )
    if not cleaned or cleaned == "linkedin":
        return None
    return cleaned

PHONE_RELATIONSHIP: str = "phone_contacts_upload"


class ContactsService:
    def __init__(self, db: AsyncSession) -> None:
        self._db: AsyncSession = db

    async def list_people(
        self,
        user_id: uuid.UUID,
        *,
        network_only: bool = True,
    ) -> ListPeopleResult:
        stmt = (
            select(Person, UserPersonObservation, Source)
            .join(
                UserPersonObservation,
                (UserPersonObservation.person_id == Person.id)
                & (UserPersonObservation.user_id == user_id),
            )
            .outerjoin(Source, Source.id == UserPersonObservation.source_id)
        )
        if network_only:
            stmt = stmt.where(
                UserPersonObservation.relationship_types.any(PHONE_RELATIONSHIP),
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
        stmt = stmt.order_by(
            UserPersonObservation.tie_strength_score.desc(),
            Person.canonical_name.asc(),
        )
        result = await self._db.execute(stmt)
        rows: list[tuple[Person, UserPersonObservation, Source | None]] = list(
            result.all()
        )
        if not rows:
            return ListPeopleResult(
                people=[],
                total=0,
                strong_tie_count=0,
                enriched_count=0,
                message="No contacts in your network yet. Import phone contacts to get started.",
            )

        person_ids: list[uuid.UUID] = [person.id for person, _, _ in rows]
        emails_by_person: dict[uuid.UUID, list[str]] = await self._load_emails_by_person(
            person_ids
        )
        sources_by_person: dict[uuid.UUID, list[str]] = await self._load_sources_by_person(
            user_id,
            person_ids,
        )
        linkedin_by_person: dict[uuid.UUID, str] = await self._load_linkedin_urls(person_ids)
        strong_tie_ids: set[uuid.UUID] = await self._load_strong_tie_ids(user_id, person_ids)
        enriched_ids: set[uuid.UUID] = await self._load_scrapingdog_enriched_ids(person_ids)

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
                    is_strong_tie=person.id in strong_tie_ids,
                    linkedin_url=linkedin_by_person.get(person.id),
                    scrapingdog_enriched=person.id in enriched_ids,
                )
            )

        strong_tie_count: int = sum(1 for person in people if person.is_strong_tie)
        enriched_count: int = sum(1 for person in people if person.scrapingdog_enriched)

        return ListPeopleResult(
            people=people,
            total=len(people),
            strong_tie_count=strong_tie_count,
            enriched_count=enriched_count,
            message=(
                f"{len(people)} contact(s) in your network · "
                f"{strong_tie_count} strong professional tie(s) · {enriched_count} enriched."
            ),
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
        social_profiles: dict[str, str] = dict(person.social_profiles or {})
        linkedin_by_person: dict[uuid.UUID, str] = await self._load_linkedin_urls(
            [person_id],
        )
        linkedin_url: str | None = (
            linkedin_by_person.get(person_id) or social_profiles.get("linkedin")
        )
        web_links: list[str] = list(dict.fromkeys(social_profiles.values()))

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
            social_profiles=social_profiles,
            linkedin_url=linkedin_url,
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
            .where(
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
                description=org.description,
                careers_url=org.careers_url,
                linkedin_url=org.linkedin_url,
                categories=list(org.categories or []),
                employee_count=org.employee_count,
                company_size_band=org.company_size_band,
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
            description=org.description,
            careers_url=org.careers_url,
            linkedin_url=org.linkedin_url,
            categories=list(org.categories or []),
            employee_count=org.employee_count,
            company_size_band=org.company_size_band,
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

    async def update_person(
        self,
        user_id: uuid.UUID,
        body: UpdatePersonRequest,
    ) -> PersonDetailResult | None:
        person_id: uuid.UUID = uuid.UUID(body.person_id)
        person: Person | None = await self._get_observed_person(user_id, person_id)
        if person is None:
            return None

        resolver: EntityResolver = EntityResolver(self._db)

        if body.first_name is not None or body.last_name is not None:
            first: str = (
                body.first_name.strip()
                if body.first_name is not None
                else split_display_name(person.canonical_name)[0]
            )
            last: str = (
                body.last_name.strip()
                if body.last_name is not None
                else split_display_name(person.canonical_name)[1]
            )
            display_name: str = sanitize_display_name(f"{first} {last}".strip())
            if display_name:
                person.canonical_name = display_name

        if body.primary_email is not None:
            email: str = body.primary_email.strip().lower()
            person.primary_email = email or None
            if email:
                await resolver.add_person_alias(
                    person_id=person.id,
                    kind=IdentityKind.EMAIL.value,
                    value=email,
                    confidence=_MANUAL_CONFIDENCE,
                )

        await self._apply_manual_person_attribute(
            person_id=person.id,
            user_id=user_id,
            kind="phone",
            value=body.phone,
            on_clear=lambda: setattr(person, "phone_numbers", []),
        )
        await self._apply_manual_person_attribute(
            person_id=person.id,
            user_id=user_id,
            kind="location",
            value=body.location,
        )
        await self._apply_manual_person_attribute(
            person_id=person.id,
            user_id=user_id,
            kind="bio_summary",
            value=body.bio_summary,
        )
        await self._apply_manual_person_attribute(
            person_id=person.id,
            user_id=user_id,
            kind="role",
            value=body.current_role,
        )

        if body.linkedin_url is not None:
            linkedin: str = body.linkedin_url.strip().rstrip("/")
            if linkedin:
                await record_person_attribute(
                    self._db,
                    person_id=person.id,
                    kind="social_profile.linkedin",
                    value=linkedin,
                    contributor_user_id=user_id,
                    contributor_source_kind=_MANUAL_SOURCE_KIND,
                    confidence=_MANUAL_CONFIDENCE,
                )
                await resolver.add_person_alias(
                    person_id=person.id,
                    kind="linkedin_url",
                    value=linkedin,
                    confidence=_MANUAL_CONFIDENCE,
                )
            else:
                person.social_profiles = {
                    key: value
                    for key, value in (person.social_profiles or {}).items()
                    if key != "linkedin"
                }

        if body.social_profiles is not None:
            await self._sync_social_profiles(
                person_id=person.id,
                user_id=user_id,
                profiles=body.social_profiles,
            )

        if body.org_name is not None:
            org_name: str = body.org_name.strip()
            if org_name:
                org: Org = await resolver.resolve_org(domain=None, name=org_name)
                role_title: str | None = (
                    body.current_role.strip()
                    if body.current_role is not None and body.current_role.strip()
                    else person.current_role
                )
                await record_employment(
                    self._db,
                    person_id=person.id,
                    org_id=org.id,
                    role_title=role_title,
                    is_current=True,
                    contributor_user_id=user_id,
                    contributor_source_kind=_MANUAL_SOURCE_KIND,
                    confidence=_MANUAL_CONFIDENCE,
                )
            else:
                current_claims = await self._db.execute(
                    select(EmploymentClaim).where(
                        EmploymentClaim.person_id == person.id,
                        EmploymentClaim.is_current.is_(True),
                    )
                )
                for claim in current_claims.scalars().all():
                    claim.is_current = False
        elif body.current_role is not None and body.current_role.strip():
            if person.current_org_id is not None:
                await record_employment(
                    self._db,
                    person_id=person.id,
                    org_id=person.current_org_id,
                    role_title=body.current_role.strip(),
                    is_current=True,
                    contributor_user_id=user_id,
                    contributor_source_kind=_MANUAL_SOURCE_KIND,
                    confidence=_MANUAL_CONFIDENCE,
                )

        if body.phone is not None and body.phone.strip():
            normalized_phone: str = normalize_phone(body.phone.strip())
            await resolver.add_person_alias(
                person_id=person.id,
                kind="phone",
                value=normalized_phone,
                confidence=_MANUAL_CONFIDENCE,
            )

        recompute: PersonProfileRecompute = PersonProfileRecompute(self._db)
        await recompute.recompute_persons([person.id])
        await self._db.flush()
        return await self.get_person(user_id, person.id)

    async def update_org(
        self,
        user_id: uuid.UUID,
        body: UpdateOrgRequest,
    ) -> OrgDetailResult | None:
        org_id: uuid.UUID = uuid.UUID(body.org_id)
        existing: OrgDetailResult | None = await self.get_org(user_id, org_id)
        if existing is None:
            return None

        org: Org | None = await self._db.get(Org, org_id)
        if org is None:
            return None

        field_map: list[tuple[str, str | None, str]] = [
            ("name", body.name, "canonical_name"),
            ("primary_domain", body.primary_domain, "primary_domain"),
            ("description", body.description, "description"),
            ("linkedin_url", body.linkedin_url, "linkedin_url"),
            ("careers_url", body.careers_url, "careers_url"),
        ]
        for kind, raw_value, attr_name in field_map:
            if raw_value is None:
                continue
            cleaned: str = raw_value.strip()
            if kind == "primary_domain":
                cleaned = cleaned.removeprefix("https://").removeprefix("http://").rstrip("/")
            if kind in {"linkedin_url", "careers_url"}:
                cleaned = cleaned.rstrip("/")
            if kind == "name" and not cleaned:
                continue
            setattr(org, attr_name, cleaned or None)
            if cleaned:
                await record_org_attribute(
                    self._db,
                    org_id=org.id,
                    kind=kind,
                    value=cleaned,
                    contributor_user_id=user_id,
                    contributor_source_kind=_MANUAL_SOURCE_KIND,
                    confidence=_MANUAL_CONFIDENCE,
                )

        if body.categories is not None:
            categories: list[str] = [
                category.strip()
                for category in body.categories
                if category.strip()
            ]
            org.categories = categories
            if categories:
                await record_org_attribute(
                    self._db,
                    org_id=org.id,
                    kind="categories",
                    value=", ".join(categories),
                    contributor_user_id=user_id,
                    contributor_source_kind=_MANUAL_SOURCE_KIND,
                    confidence=_MANUAL_CONFIDENCE,
                )

        if body.name is not None and org.canonical_name:
            persons_at_org = await self._db.execute(
                select(Person).where(Person.current_org_id == org.id)
            )
            for person in persons_at_org.scalars().all():
                person.current_org_name = org.canonical_name

        await self._db.flush()
        return await self.get_org(user_id, org.id)

    async def _get_observed_person(
        self,
        user_id: uuid.UUID,
        person_id: uuid.UUID,
    ) -> Person | None:
        result = await self._db.execute(
            select(Person)
            .join(
                UserPersonObservation,
                (UserPersonObservation.person_id == Person.id)
                & (UserPersonObservation.user_id == user_id),
            )
            .where(Person.id == person_id)
        )
        return result.scalar_one_or_none()

    async def _sync_social_profiles(
        self,
        *,
        person_id: uuid.UUID,
        user_id: uuid.UUID,
        profiles: dict[str, str],
    ) -> None:
        await self._db.execute(
            delete(PersonAttributeClaim).where(
                PersonAttributeClaim.person_id == person_id,
                PersonAttributeClaim.kind.like("social_profile.%"),
                PersonAttributeClaim.kind != "social_profile.linkedin",
            )
        )

        seen_platforms: set[str] = set()
        for raw_platform, raw_url in profiles.items():
            platform: str | None = normalize_social_platform(raw_platform)
            if platform is None or platform in seen_platforms:
                continue
            url: str = raw_url.strip().rstrip("/")
            if not url:
                continue
            seen_platforms.add(platform)
            await record_person_attribute(
                self._db,
                person_id=person_id,
                kind=f"social_profile.{platform}",
                value=url,
                contributor_user_id=user_id,
                contributor_source_kind=_MANUAL_SOURCE_KIND,
                confidence=_MANUAL_CONFIDENCE,
            )

    async def _apply_manual_person_attribute(
        self,
        *,
        person_id: uuid.UUID,
        user_id: uuid.UUID,
        kind: str,
        value: str | None,
        on_clear: Callable[[], None] | None = None,
    ) -> None:
        if value is None:
            return
        cleaned: str = value.strip()
        if cleaned:
            await record_person_attribute(
                self._db,
                person_id=person_id,
                kind=kind,
                value=cleaned,
                contributor_user_id=user_id,
                contributor_source_kind=_MANUAL_SOURCE_KIND,
                confidence=_MANUAL_CONFIDENCE,
            )
            return
        if on_clear is not None:
            on_clear()

    async def _load_linkedin_urls(
        self,
        person_ids: list[uuid.UUID],
    ) -> dict[uuid.UUID, str]:
        if not person_ids:
            return {}
        result = await self._db.execute(
            select(PersonAlias.person_id, PersonAlias.value).where(
                PersonAlias.person_id.in_(person_ids),
                PersonAlias.kind == "linkedin_url",
            )
        )
        linkedin_by_person: dict[uuid.UUID, str] = {}
        for person_id, value in result.all():
            if person_id not in linkedin_by_person:
                linkedin_by_person[person_id] = value.rstrip("/")
        return linkedin_by_person

    async def _load_strong_tie_ids(
        self,
        user_id: uuid.UUID,
        person_ids: list[uuid.UUID],
    ) -> set[uuid.UUID]:
        if not person_ids:
            return set()
        result = await self._db.execute(
            select(Person.id)
            .where(
                Person.id.in_(person_ids),
                exists(
                    select(UserPersonObservation.person_id).where(
                        UserPersonObservation.user_id == user_id,
                        UserPersonObservation.person_id == Person.id,
                        UserPersonObservation.relationship_types.any(PHONE_RELATIONSHIP),
                    )
                ),
                exists(
                    select(UserPersonObservation.person_id).where(
                        UserPersonObservation.user_id == user_id,
                        UserPersonObservation.person_id == Person.id,
                        UserPersonObservation.relationship_types.any(
                            LINKEDIN_CONNECTIONS_RELATIONSHIP,
                        ),
                    )
                ),
                exists(
                    select(PersonAlias.person_id).where(
                        PersonAlias.person_id == Person.id,
                        PersonAlias.kind == "linkedin_url",
                    )
                ),
            )
        )
        return {row[0] for row in result.all()}

    async def _load_scrapingdog_enriched_ids(
        self,
        person_ids: list[uuid.UUID],
    ) -> set[uuid.UUID]:
        if not person_ids:
            return set()
        result = await self._db.execute(
            select(EmploymentClaim.person_id)
            .where(
                EmploymentClaim.person_id.in_(person_ids),
                EmploymentClaim.contributor_source_kind == SCRAPINGDOG_SOURCE_KIND,
            )
            .distinct()
        )
        return {row[0] for row in result.all()}

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
