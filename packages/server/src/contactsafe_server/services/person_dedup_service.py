"""Merge duplicate Person records that share the same canonical name."""

from __future__ import annotations

import logging
import re
import uuid
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from contactsafe_core.contact_schemas import DedupPersonsResult
from contactsafe_server.db.models import (
    ContactPrivacyLabelRow,
    EmploymentClaim,
    EnrichmentAttempt,
    InteractionExcerpt,
    Person,
    PersonAlias,
    PersonAttributeClaim,
    UserOrgObservation,
    UserPersonObservation,
    UserRelationshipObservation,
)

from contactsafe_server.services.phone_normalization import normalize_phone

logger: logging.Logger = logging.getLogger(__name__)

_EMAIL_RE: re.Pattern[str] = re.compile(r"@")


@dataclass(frozen=True, slots=True)
class _PersonGroup:
    normalized_name: str
    persons: tuple[Person, ...]


class PersonDedupService:
    def __init__(self, db: AsyncSession) -> None:
        self._db: AsyncSession = db

    async def dedup_for_user(self, user_id: uuid.UUID) -> DedupPersonsResult:
        person_ids: list[uuid.UUID] = await self._load_observed_person_ids(user_id)
        if not person_ids:
            return DedupPersonsResult(
                groups_merged=0,
                persons_removed=0,
                message="No people found to deduplicate.",
            )

        alias_counts: dict[uuid.UUID, int] = await self._load_alias_counts(person_ids)
        persons: list[Person] = await self._load_persons(person_ids)
        groups: list[_PersonGroup] = self._group_by_name(persons)

        groups_merged: int = 0
        persons_removed: int = 0
        merged_ids: set[uuid.UUID] = set()

        for group in groups:
            if len(group.persons) < 2:
                continue
            survivor: Person = self._pick_survivor(group.persons, alias_counts)
            duplicates: list[Person] = [p for p in group.persons if p.id != survivor.id]
            for duplicate in duplicates:
                await self._merge_person(
                    survivor=survivor,
                    duplicate=duplicate,
                )
                await self._db.delete(duplicate)
                merged_ids.add(duplicate.id)
                persons_removed += 1
            groups_merged += 1

        phone_groups_merged, phone_removed = await self._dedup_by_phone(
            person_ids=person_ids,
            alias_counts=alias_counts,
            merged_ids=merged_ids,
        )
        groups_merged += phone_groups_merged
        persons_removed += phone_removed

        email_groups_merged, email_removed = await self._dedup_by_email_as_name(
            person_ids=[pid for pid in person_ids if pid not in merged_ids],
            alias_counts=alias_counts,
            merged_ids=merged_ids,
        )
        groups_merged += email_groups_merged
        persons_removed += email_removed

        await self._db.flush()
        message: str = (
            f"Merged {groups_merged} duplicate name group(s); "
            f"removed {persons_removed} person record(s)."
            if groups_merged
            else "No duplicate names found among your contacts."
        )
        logger.info("Person dedup for user %s: %s", user_id, message)
        return DedupPersonsResult(
            groups_merged=groups_merged,
            persons_removed=persons_removed,
            message=message,
        )

    async def _load_observed_person_ids(self, user_id: uuid.UUID) -> list[uuid.UUID]:
        stmt = select(UserPersonObservation.person_id).where(
            UserPersonObservation.user_id == user_id,
        )
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def _load_alias_counts(
        self,
        person_ids: list[uuid.UUID],
    ) -> dict[uuid.UUID, int]:
        stmt = (
            select(PersonAlias.person_id, func.count(PersonAlias.id))
            .where(PersonAlias.person_id.in_(person_ids))
            .group_by(PersonAlias.person_id)
        )
        result = await self._db.execute(stmt)
        return {person_id: int(count) for person_id, count in result.all()}

    async def _load_persons(self, person_ids: list[uuid.UUID]) -> list[Person]:
        stmt = select(Person).where(Person.id.in_(person_ids))
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    def _group_by_name(self, persons: list[Person]) -> list[_PersonGroup]:
        grouped: dict[str, list[Person]] = defaultdict(list)
        for person in persons:
            normalized: str = person.canonical_name.strip().lower()
            if not normalized:
                continue
            grouped[normalized].append(person)
        return [
            _PersonGroup(normalized_name=name, persons=tuple(group))
            for name, group in grouped.items()
        ]

    def _pick_survivor(
        self,
        persons: tuple[Person, ...],
        alias_counts: dict[uuid.UUID, int],
    ) -> Person:
        return max(
            persons,
            key=lambda person: (
                0 if _looks_like_email(person.canonical_name) else 1,
                alias_counts.get(person.id, 0),
                1 if person.primary_email else 0,
                len(person.phone_numbers or []),
                1 if person.current_org_id else 0,
                -person.created_at.timestamp(),
            ),
        )

    async def _dedup_by_phone(
        self,
        *,
        person_ids: list[uuid.UUID],
        alias_counts: dict[uuid.UUID, int],
        merged_ids: set[uuid.UUID],
    ) -> tuple[int, int]:
        active_ids: list[uuid.UUID] = [pid for pid in person_ids if pid not in merged_ids]
        if len(active_ids) < 2:
            return 0, 0

        stmt = select(PersonAlias).where(
            PersonAlias.person_id.in_(active_ids),
            PersonAlias.kind == "phone",
        )
        result = await self._db.execute(stmt)
        aliases: list[PersonAlias] = list(result.scalars().all())

        grouped: dict[str, list[uuid.UUID]] = defaultdict(list)
        for alias in aliases:
            normalized: str = normalize_phone(alias.value)
            if normalized:
                grouped[normalized].append(alias.person_id)

        groups_merged: int = 0
        persons_removed: int = 0
        for person_ids_for_phone in grouped.values():
            unique_ids: list[uuid.UUID] = sorted(set(person_ids_for_phone))
            if len(unique_ids) < 2:
                continue
            persons: list[Person] = await self._load_persons(unique_ids)
            survivor: Person = self._pick_survivor(tuple(persons), alias_counts)
            for duplicate in persons:
                if duplicate.id == survivor.id or duplicate.id in merged_ids:
                    continue
                await self._merge_person(survivor=survivor, duplicate=duplicate)
                await self._db.delete(duplicate)
                merged_ids.add(duplicate.id)
                persons_removed += 1
            groups_merged += 1
        return groups_merged, persons_removed

    async def _dedup_by_email_as_name(
        self,
        *,
        person_ids: list[uuid.UUID],
        alias_counts: dict[uuid.UUID, int],
        merged_ids: set[uuid.UUID],
    ) -> tuple[int, int]:
        active_ids: list[uuid.UUID] = [pid for pid in person_ids if pid not in merged_ids]
        if len(active_ids) < 2:
            return 0, 0

        persons: list[Person] = await self._load_persons(active_ids)
        email_to_person_ids: dict[str, list[uuid.UUID]] = defaultdict(list)
        for person in persons:
            if _looks_like_email(person.canonical_name):
                email_to_person_ids[person.canonical_name.lower()].append(person.id)
            if person.primary_email:
                email_to_person_ids[person.primary_email.lower()].append(person.id)

        stmt = select(PersonAlias).where(
            PersonAlias.person_id.in_(active_ids),
            PersonAlias.kind == "email",
        )
        result = await self._db.execute(stmt)
        for alias in result.scalars().all():
            email_to_person_ids[alias.value.lower()].append(alias.person_id)

        groups_merged: int = 0
        persons_removed: int = 0
        for linked_person_ids in email_to_person_ids.values():
            unique_ids: list[uuid.UUID] = sorted(set(linked_person_ids))
            if len(unique_ids) < 2:
                continue
            group_persons: list[Person] = await self._load_persons(unique_ids)
            if not any(_looks_like_email(p.canonical_name) for p in group_persons):
                if len({p.canonical_name.strip().lower() for p in group_persons}) == 1:
                    continue
            survivor: Person = self._pick_survivor(tuple(group_persons), alias_counts)
            for duplicate in group_persons:
                if duplicate.id == survivor.id or duplicate.id in merged_ids:
                    continue
                await self._merge_person(survivor=survivor, duplicate=duplicate)
                await self._db.delete(duplicate)
                merged_ids.add(duplicate.id)
                persons_removed += 1
            groups_merged += 1
        return groups_merged, persons_removed

    async def _merge_person(
        self,
        *,
        survivor: Person,
        duplicate: Person,
    ) -> None:
        self._merge_person_fields(survivor, duplicate)
        await self._merge_aliases(survivor.id, duplicate.id)
        await self._merge_all_observations(survivor.id, duplicate.id)
        await self._reassign_claims(survivor.id, duplicate.id)
        await self._reassign_interaction_excerpts(survivor.id, duplicate.id)
        await self._reassign_relationship_observations(survivor.id, duplicate.id)
        await self._reassign_org_observations(survivor.id, duplicate.id)
        await self._reassign_privacy_labels(survivor.id, duplicate.id)
        await self._reassign_enrichment_attempts(survivor.id, duplicate.id)

    def _merge_person_fields(self, survivor: Person, duplicate: Person) -> None:
        if not survivor.primary_email and duplicate.primary_email:
            survivor.primary_email = duplicate.primary_email
        if duplicate.phone_numbers:
            existing: set[str] = set(survivor.phone_numbers or [])
            merged_phones: list[str] = list(survivor.phone_numbers or [])
            for phone in duplicate.phone_numbers:
                if phone not in existing:
                    merged_phones.append(phone)
                    existing.add(phone)
            survivor.phone_numbers = merged_phones
        if not survivor.current_org_id and duplicate.current_org_id:
            survivor.current_org_id = duplicate.current_org_id
        if not survivor.current_org_name and duplicate.current_org_name:
            survivor.current_org_name = duplicate.current_org_name
        if not survivor.current_role and duplicate.current_role:
            survivor.current_role = duplicate.current_role
        if not survivor.bio_summary and duplicate.bio_summary:
            survivor.bio_summary = duplicate.bio_summary
        if not survivor.location and duplicate.location:
            survivor.location = duplicate.location

    async def _merge_aliases(
        self,
        survivor_id: uuid.UUID,
        duplicate_id: uuid.UUID,
    ) -> None:
        survivor_aliases: set[tuple[str, str]] = await self._alias_keys_for_person(survivor_id)
        dup_result = await self._db.execute(
            select(PersonAlias).where(PersonAlias.person_id == duplicate_id)
        )
        duplicate_aliases: list[PersonAlias] = list(dup_result.scalars().all())
        for alias in duplicate_aliases:
            key: tuple[str, str] = (alias.kind, alias.value)
            if key in survivor_aliases:
                await self._db.delete(alias)
                continue
            alias.person_id = survivor_id
            survivor_aliases.add(key)

    async def _alias_keys_for_person(self, person_id: uuid.UUID) -> set[tuple[str, str]]:
        result = await self._db.execute(
            select(PersonAlias.kind, PersonAlias.value).where(
                PersonAlias.person_id == person_id,
            )
        )
        return {(kind, value) for kind, value in result.all()}

    async def _merge_all_observations(
        self,
        survivor_id: uuid.UUID,
        duplicate_id: uuid.UUID,
    ) -> None:
        result = await self._db.execute(
            select(UserPersonObservation).where(
                UserPersonObservation.person_id == duplicate_id,
            )
        )
        duplicate_observations: list[UserPersonObservation] = list(result.scalars().all())
        for duplicate_obs in duplicate_observations:
            await self._merge_observation(
                survivor_id,
                duplicate_obs.user_id,
                duplicate_obs,
            )

    async def _merge_observation(
        self,
        survivor_id: uuid.UUID,
        obs_user_id: uuid.UUID,
        duplicate_obs: UserPersonObservation,
    ) -> None:
        survivor_obs: UserPersonObservation | None = await self._db.get(
            UserPersonObservation,
            (obs_user_id, survivor_id),
        )
        if survivor_obs is None:
            duplicate_obs.person_id = survivor_id
            return

        survivor_obs.tie_strength_score = min(
            1.0,
            survivor_obs.tie_strength_score + duplicate_obs.tie_strength_score,
        )
        survivor_obs.email_count += duplicate_obs.email_count
        survivor_obs.outbound_count += duplicate_obs.outbound_count
        survivor_obs.inbound_count += duplicate_obs.inbound_count
        survivor_obs.thread_count += duplicate_obs.thread_count
        survivor_obs.is_human = survivor_obs.is_human or duplicate_obs.is_human
        survivor_obs.relationship_types = sorted(
            set(survivor_obs.relationship_types or [])
            | set(duplicate_obs.relationship_types or [])
        )
        survivor_obs.first_observed_at = self._earliest(
            survivor_obs.first_observed_at,
            duplicate_obs.first_observed_at,
        )
        survivor_obs.last_observed_at = self._latest(
            survivor_obs.last_observed_at,
            duplicate_obs.last_observed_at,
        )
        survivor_obs.last_genuine_interaction_at = self._latest(
            survivor_obs.last_genuine_interaction_at,
            duplicate_obs.last_genuine_interaction_at,
        )
        await self._db.delete(duplicate_obs)

    async def _reassign_claims(
        self,
        survivor_id: uuid.UUID,
        duplicate_id: uuid.UUID,
    ) -> None:
        await self._reassign_employment_claims(survivor_id, duplicate_id)
        await self._reassign_attribute_claims(survivor_id, duplicate_id)

    async def _reassign_employment_claims(
        self,
        survivor_id: uuid.UUID,
        duplicate_id: uuid.UUID,
    ) -> None:
        result = await self._db.execute(
            select(EmploymentClaim).where(EmploymentClaim.person_id == duplicate_id)
        )
        claims: list[EmploymentClaim] = list(result.scalars().all())
        survivor_keys: set[tuple[uuid.UUID, str, uuid.UUID | None]] = {
            (claim.org_id, claim.contributor_source_kind, claim.contributor_user_id)
            for claim in (
                await self._db.execute(
                    select(EmploymentClaim).where(EmploymentClaim.person_id == survivor_id)
                )
            ).scalars().all()
        }
        for claim in claims:
            key = (claim.org_id, claim.contributor_source_kind, claim.contributor_user_id)
            if key in survivor_keys:
                await self._db.delete(claim)
                continue
            claim.person_id = survivor_id
            survivor_keys.add(key)

    async def _reassign_attribute_claims(
        self,
        survivor_id: uuid.UUID,
        duplicate_id: uuid.UUID,
    ) -> None:
        result = await self._db.execute(
            select(PersonAttributeClaim).where(
                PersonAttributeClaim.person_id == duplicate_id,
            )
        )
        claims: list[PersonAttributeClaim] = list(result.scalars().all())
        survivor_keys: set[tuple[str, str, str, uuid.UUID | None]] = {
            (
                claim.kind,
                claim.value,
                claim.contributor_source_kind,
                claim.contributor_user_id,
            )
            for claim in (
                await self._db.execute(
                    select(PersonAttributeClaim).where(
                        PersonAttributeClaim.person_id == survivor_id,
                    )
                )
            ).scalars().all()
        }
        for claim in claims:
            key = (
                claim.kind,
                claim.value,
                claim.contributor_source_kind,
                claim.contributor_user_id,
            )
            if key in survivor_keys:
                await self._db.delete(claim)
                continue
            claim.person_id = survivor_id
            survivor_keys.add(key)

    async def _reassign_interaction_excerpts(
        self,
        survivor_id: uuid.UUID,
        duplicate_id: uuid.UUID,
    ) -> None:
        await self._db.execute(
            update(InteractionExcerpt)
            .where(InteractionExcerpt.person_id == duplicate_id)
            .values(person_id=survivor_id)
        )

    async def _reassign_relationship_observations(
        self,
        survivor_id: uuid.UUID,
        duplicate_id: uuid.UUID,
    ) -> None:
        await self._db.execute(
            update(UserRelationshipObservation)
            .where(UserRelationshipObservation.person_a_id == duplicate_id)
            .values(person_a_id=survivor_id)
        )
        await self._db.execute(
            update(UserRelationshipObservation)
            .where(UserRelationshipObservation.person_b_id == duplicate_id)
            .values(person_b_id=survivor_id)
        )

    async def _reassign_org_observations(
        self,
        survivor_id: uuid.UUID,
        duplicate_id: uuid.UUID,
    ) -> None:
        result = await self._db.execute(select(UserOrgObservation))
        observations: list[UserOrgObservation] = list(result.scalars().all())
        for observation in observations:
            if duplicate_id not in observation.associated_person_ids:
                continue
            updated_ids: list[uuid.UUID] = [
                survivor_id if person_id == duplicate_id else person_id
                for person_id in observation.associated_person_ids
            ]
            observation.associated_person_ids = sorted(set(updated_ids))

    async def _reassign_privacy_labels(
        self,
        survivor_id: uuid.UUID,
        duplicate_id: uuid.UUID,
    ) -> None:
        result = await self._db.execute(
            select(ContactPrivacyLabelRow).where(
                ContactPrivacyLabelRow.person_id == duplicate_id,
            )
        )
        duplicate_labels: list[ContactPrivacyLabelRow] = list(result.scalars().all())
        for duplicate_label in duplicate_labels:
            survivor_label: ContactPrivacyLabelRow | None = (
                await self._db.execute(
                    select(ContactPrivacyLabelRow).where(
                        ContactPrivacyLabelRow.user_id == duplicate_label.user_id,
                        ContactPrivacyLabelRow.person_id == survivor_id,
                    )
                )
            ).scalar_one_or_none()
            if survivor_label is None:
                duplicate_label.person_id = survivor_id
                continue
            await self._db.delete(duplicate_label)

    async def _reassign_enrichment_attempts(
        self,
        survivor_id: uuid.UUID,
        duplicate_id: uuid.UUID,
    ) -> None:
        result = await self._db.execute(
            select(EnrichmentAttempt).where(EnrichmentAttempt.person_id == duplicate_id)
        )
        attempts: list[EnrichmentAttempt] = list(result.scalars().all())
        survivor_kinds: set[str] = {
            attempt.source_kind
            for attempt in (
                await self._db.execute(
                    select(EnrichmentAttempt).where(
                        EnrichmentAttempt.person_id == survivor_id,
                    )
                )
            ).scalars().all()
        }
        for attempt in attempts:
            if attempt.source_kind in survivor_kinds:
                await self._db.delete(attempt)
                continue
            attempt.person_id = survivor_id
            survivor_kinds.add(attempt.source_kind)

    @staticmethod
    def _earliest(
        left: datetime | None,
        right: datetime | None,
    ) -> datetime | None:
        if left is None:
            return right
        if right is None:
            return left
        return min(left, right)

    @staticmethod
    def _latest(
        left: datetime | None,
        right: datetime | None,
    ) -> datetime | None:
        if left is None:
            return right
        if right is None:
            return left
        return max(left, right)


def _looks_like_email(name: str) -> bool:
    return bool(_EMAIL_RE.search(name))
