from __future__ import annotations

import re
import uuid
from collections import defaultdict
from typing import Callable

from sqlalchemy import delete, exists, func, or_, select
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
    join_display_name,
    split_display_name,
)
from contactsafe_core.enums import (
    ContactPrivacyLabel,
    IdentityKind,
    TrustListMembershipStatus,
)
from contactsafe_server.services.ats_detection import apply_ats_detection_to_org
from contactsafe_server.db.models import (
    ContactPrivacyLabelRow,
    EmploymentClaim,
    Org,
    Person,
    PersonAlias,
    PersonAttributeClaim,
    Source,
    TrustListMembership,
    User,
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
        include_shared: bool = True,
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

        own_person_ids: set[uuid.UUID] = {person.id for person, _, _ in rows}

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
        claimed_avatars: dict[uuid.UUID, str | None] = await self._load_claimed_avatars(person_ids)

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
                    display_name=join_display_name(first_name, last_name),
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
                    is_claimed=person.id in claimed_avatars,
                    avatar_url=claimed_avatars.get(person.id),
                    linkedin_url=linkedin_by_person.get(person.id),
                    scrapingdog_enriched=person.id in enriched_ids,
                )
            )

        if include_shared:
            shared_people: list[PersonListItem] = await self._load_shared_people(
                user_id, own_person_ids
            )
            people.extend(shared_people)

        strong_tie_count: int = sum(1 for p in people if p.is_strong_tie)
        enriched_count: int = sum(1 for p in people if p.scrapingdog_enriched)

        if not people:
            return ListPeopleResult(
                people=[],
                total=0,
                strong_tie_count=0,
                enriched_count=0,
                message="No contacts in your network yet. Import phone contacts to get started.",
            )

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

        claimed_avatars: dict[uuid.UUID, str | None] = await self._load_claimed_avatars(
            [person_id],
        )

        return PersonDetailResult(
            person_id=person.id,
            first_name=first_name,
            last_name=last_name,
            display_name=join_display_name(first_name, last_name),
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
            is_claimed=person_id in claimed_avatars,
            avatar_url=claimed_avatars.get(person_id),
            message=f"Contact details for {person.canonical_name}.",
        )

    async def list_orgs(
        self,
        user_id: uuid.UUID,
        *,
        include_shared: bool = True,
    ) -> ListOrgsResult:
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

        org_map: dict[uuid.UUID, OrgListItem] = {}
        for org, count in rows:
            org_map[org.id] = OrgListItem(
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

        if include_shared:
            await self._merge_shared_orgs(user_id, org_map)

        orgs: list[OrgListItem] = sorted(org_map.values(), key=lambda o: o.name.lower())

        if not orgs:
            return ListOrgsResult(
                orgs=[],
                total=0,
                message="No organizations resolved yet.",
            )

        return ListOrgsResult(
            orgs=orgs,
            total=len(orgs),
            message=f"Found {len(orgs)} organization(s) in your graph.",
        )

    async def get_org(
        self,
        user_id: uuid.UUID,
        org_id: uuid.UUID,
        *,
        include_shared: bool = True,
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
        own_person_ids: set[uuid.UUID] = {p.id for p in people_rows}

        people_summaries: list[OrgPersonSummary] = [
            OrgPersonSummary(
                person_id=person.id,
                display_name=join_display_name(*split_display_name(person.canonical_name)),
                primary_email=person.primary_email,
                current_role=person.current_role,
            )
            for person in people_rows
        ]

        if include_shared:
            shared_summaries: list[OrgPersonSummary] = await self._load_shared_org_people(
                user_id, org_id, own_person_ids
            )
            people_summaries.extend(shared_summaries)

        if not people_summaries:
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
            people=people_summaries,
            contact_count=len(people_summaries),
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

        if body.careers_url is not None:
            apply_ats_detection_to_org(org)

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

    # ------------------------------------------------------------------
    # Shared network helpers
    # ------------------------------------------------------------------

    async def _get_trust_member_ids(self, user_id: uuid.UUID) -> list[uuid.UUID]:
        """Return user_ids of all active trust list members for a given user."""
        stmt = select(TrustListMembership).where(
            TrustListMembership.status == TrustListMembershipStatus.ACTIVE,
            or_(
                TrustListMembership.user_a_id == user_id,
                TrustListMembership.user_b_id == user_id,
            ),
        )
        result = await self._db.execute(stmt)
        memberships: list[TrustListMembership] = list(result.scalars().all())
        member_ids: list[uuid.UUID] = []
        for m in memberships:
            other: uuid.UUID = m.user_b_id if m.user_a_id == user_id else m.user_a_id
            member_ids.append(other)
        return member_ids

    async def _get_private_person_ids(self, user_id: uuid.UUID) -> set[uuid.UUID]:
        """Return person_ids that this user has marked private."""
        stmt = select(ContactPrivacyLabelRow.person_id).where(
            ContactPrivacyLabelRow.user_id == user_id,
            ContactPrivacyLabelRow.label == ContactPrivacyLabel.PRIVATE,
        )
        result = await self._db.execute(stmt)
        return set(result.scalars().all())

    @staticmethod
    def _mask_last_name(full_name: str) -> tuple[str, str, str]:
        """Return (first_name, masked_last, masked_display_name) with last initial only."""
        first, last = split_display_name(full_name)
        masked_last: str = f"{last[0]}." if last else ""
        masked_display: str = (
            join_display_name(first, masked_last) if first else full_name
        )
        return first, masked_last, masked_display

    async def _load_shared_people(
        self,
        user_id: uuid.UUID,
        own_person_ids: set[uuid.UUID],
    ) -> list[PersonListItem]:
        """Load contacts from trusted users' networks, with privacy masking."""
        member_ids: list[uuid.UUID] = await self._get_trust_member_ids(user_id)
        if not member_ids:
            return []

        member_names: dict[uuid.UUID, str] = {}
        for mid in member_ids:
            user_row: User | None = await self._db.get(User, mid)
            if user_row is not None:
                member_names[mid] = (
                    user_row.display_name or user_row.google_profile_name or user_row.email
                )

        shared_people: list[PersonListItem] = []
        seen_person_ids: set[uuid.UUID] = set(own_person_ids)

        for member_id in member_ids:
            private_ids: set[uuid.UUID] = await self._get_private_person_ids(member_id)
            sharer_name: str = member_names.get(member_id, "Someone")

            stmt = (
                select(Person, UserPersonObservation)
                .join(
                    UserPersonObservation,
                    (UserPersonObservation.person_id == Person.id)
                    & (UserPersonObservation.user_id == member_id),
                )
                .where(
                    UserPersonObservation.relationship_types.any(PHONE_RELATIONSHIP),
                    exists(
                        select(UserPersonObservation.person_id).where(
                            UserPersonObservation.user_id == member_id,
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
                .order_by(Person.canonical_name.asc())
            )
            result = await self._db.execute(stmt)
            rows: list[tuple[Person, UserPersonObservation]] = list(result.all())

            for person, _obs in rows:
                if person.id in seen_person_ids:
                    continue
                if person.id in private_ids:
                    continue
                seen_person_ids.add(person.id)

                first, masked_last, masked_display = self._mask_last_name(
                    person.canonical_name
                )
                shared_people.append(
                    PersonListItem(
                        person_id=person.id,
                        first_name=first,
                        last_name=masked_last,
                        display_name=masked_display,
                        primary_email=None,
                        phone=None,
                        org_name=person.current_org_name,
                        current_role=person.current_role,
                        emails=[],
                        sources=[],
                        first_contact_at=None,
                        last_contact_at=None,
                        tie_strength_score=0.0,
                        is_human=True,
                        is_broadcast=False,
                        is_automated=False,
                        is_strong_tie=False,
                        linkedin_url=None,
                        scrapingdog_enriched=False,
                        shared_from=sharer_name,
                        shared_from_user_id=member_id,
                    )
                )

        return shared_people

    async def _merge_shared_orgs(
        self,
        user_id: uuid.UUID,
        org_map: dict[uuid.UUID, OrgListItem],
    ) -> None:
        """Merge organizations from trusted users' networks into org_map."""
        member_ids: list[uuid.UUID] = await self._get_trust_member_ids(user_id)
        if not member_ids:
            return

        member_names: dict[uuid.UUID, str] = {}
        for mid in member_ids:
            user_row: User | None = await self._db.get(User, mid)
            if user_row is not None:
                member_names[mid] = (
                    user_row.display_name or user_row.google_profile_name or user_row.email
                )

        for member_id in member_ids:
            private_ids: set[uuid.UUID] = await self._get_private_person_ids(member_id)
            sharer_name: str = member_names.get(member_id, "Someone")

            stmt = (
                select(
                    Org,
                    func.count(Person.id.distinct()).label("contact_count"),
                )
                .join(Person, Person.current_org_id == Org.id)
                .where(
                    ~Person.id.in_(private_ids) if private_ids else True,
                    exists(
                        select(UserPersonObservation.person_id).where(
                            UserPersonObservation.user_id == member_id,
                            UserPersonObservation.person_id == Person.id,
                            UserPersonObservation.relationship_types.any(PHONE_RELATIONSHIP),
                        ).correlate(Person)
                    ),
                    exists(
                        select(UserPersonObservation.person_id).where(
                            UserPersonObservation.user_id == member_id,
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
            )
            result = await self._db.execute(stmt)
            rows: list[tuple[Org, int]] = [(org, int(c)) for org, c in result.all()]

            for org, count in rows:
                if org.id in org_map:
                    existing: OrgListItem = org_map[org.id]
                    if sharer_name not in existing.shared_from:
                        existing.shared_from.append(sharer_name)
                    existing.shared_contact_count += count
                else:
                    org_map[org.id] = OrgListItem(
                        org_id=org.id,
                        name=org.canonical_name,
                        primary_domain=org.primary_domain,
                        description=org.description,
                        careers_url=org.careers_url,
                        linkedin_url=org.linkedin_url,
                        categories=list(org.categories or []),
                        employee_count=org.employee_count,
                        company_size_band=org.company_size_band,
                        contact_count=0,
                        shared_from=[sharer_name],
                        shared_contact_count=count,
                    )

    async def _load_shared_org_people(
        self,
        user_id: uuid.UUID,
        org_id: uuid.UUID,
        own_person_ids: set[uuid.UUID],
    ) -> list[OrgPersonSummary]:
        """Load contacts at an org from trusted users' networks."""
        member_ids: list[uuid.UUID] = await self._get_trust_member_ids(user_id)
        if not member_ids:
            return []

        member_names: dict[uuid.UUID, str] = {}
        for mid in member_ids:
            user_row: User | None = await self._db.get(User, mid)
            if user_row is not None:
                member_names[mid] = (
                    user_row.display_name or user_row.google_profile_name or user_row.email
                )

        shared_summaries: list[OrgPersonSummary] = []
        seen_ids: set[uuid.UUID] = set(own_person_ids)

        for member_id in member_ids:
            private_ids: set[uuid.UUID] = await self._get_private_person_ids(member_id)
            sharer_name: str = member_names.get(member_id, "Someone")

            people_result = await self._db.execute(
                select(Person)
                .join(
                    UserPersonObservation,
                    (UserPersonObservation.person_id == Person.id)
                    & (UserPersonObservation.user_id == member_id),
                )
                .where(Person.current_org_id == org_id)
                .order_by(Person.canonical_name.asc())
            )
            for person in people_result.scalars().all():
                if person.id in seen_ids or person.id in private_ids:
                    continue
                seen_ids.add(person.id)
                _, masked_last, masked_display = self._mask_last_name(person.canonical_name)
                shared_summaries.append(
                    OrgPersonSummary(
                        person_id=person.id,
                        display_name=masked_display,
                        primary_email=None,
                        current_role=person.current_role,
                        shared_from=sharer_name,
                    )
                )

        return shared_summaries

    # ------------------------------------------------------------------
    # Existing private helpers
    # ------------------------------------------------------------------

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

    async def _load_claimed_avatars(
        self,
        person_ids: list[uuid.UUID],
    ) -> dict[uuid.UUID, str | None]:
        """Return {person_id: avatar_url} for persons linked to a User account."""
        if not person_ids:
            return {}
        result = await self._db.execute(
            select(User.person_id, User.google_profile_picture).where(
                User.person_id.in_(person_ids),
                User.person_id.isnot(None),
            )
        )
        return {pid: avatar for pid, avatar in result.all()}

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
