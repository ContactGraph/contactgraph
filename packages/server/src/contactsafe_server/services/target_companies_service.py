"""Target-company queries for job-search North Star use cases."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from contactsafe_server.db.models import Person, RelationshipClaim, User, UserPersonObservation
from contactsafe_server.services.relationship_trust import (
    HIGH_TRUST_THRESHOLD,
    best_relationship_kind,
    compute_trust_score,
    is_high_trust_connection,
)


@dataclass(frozen=True, slots=True)
class TargetCompanyInsider:
    person_id: uuid.UUID
    person_name: str
    person_role: str | None
    trust_score: float
    relationship_kind: str | None


@dataclass(frozen=True, slots=True)
class TargetCompanyMatch:
    org_id: uuid.UUID
    org_name: str
    insiders: list[TargetCompanyInsider]
    best_trust_score: float


@dataclass(frozen=True, slots=True)
class SecondDegreeTargetInsider:
    person_id: uuid.UUID
    person_name: str
    person_role: str | None
    bridge_user_id: uuid.UUID
    bridge_name: str
    trust_score: float


@dataclass(frozen=True, slots=True)
class SecondDegreeTargetCompanyMatch:
    org_id: uuid.UUID
    org_name: str
    insiders: list[SecondDegreeTargetInsider]
    best_trust_score: float


class TargetCompaniesService:
    def __init__(self, db: AsyncSession) -> None:
        self._db: AsyncSession = db

    async def list_first_degree(
        self,
        user_id: uuid.UUID,
        *,
        min_trust: float = HIGH_TRUST_THRESHOLD,
        limit: int = 50,
    ) -> list[TargetCompanyMatch]:
        user: User | None = await self._db.get(User, user_id)
        exclude_person_id: uuid.UUID | None = user.person_id if user is not None else None

        from sqlalchemy import or_
        from sqlalchemy.dialects.postgresql import ARRAY as PG_ARRAY, array as pg_array
        from sqlalchemy import Text, cast

        phone_rhs = cast(pg_array(["phone_contacts_upload"]), PG_ARRAY(Text))
        stmt = (
            select(Person, UserPersonObservation)
            .join(
                UserPersonObservation,
                (UserPersonObservation.person_id == Person.id)
                & (UserPersonObservation.user_id == user_id),
            )
            .where(
                Person.current_org_id.isnot(None),
                UserPersonObservation.is_broadcast.is_(False),
                UserPersonObservation.is_automated.is_(False),
                UserPersonObservation.is_human.is_(True),
                or_(
                    UserPersonObservation.outbound_count > 0,
                    UserPersonObservation.relationship_types.op("&&")(phone_rhs),
                ),
            )
        )
        result = await self._db.execute(stmt)
        rows: list[tuple[Person, UserPersonObservation]] = list(result.all())

        by_org: dict[uuid.UUID, TargetCompanyMatch] = {}
        for person, obs in rows:
            if exclude_person_id is not None and person.id == exclude_person_id:
                continue
            rel_kind: str | None = await self._relationship_kind_for_pair(
                user_id=user_id,
                contact_person_id=person.id,
                observation=obs,
            )
            trust: float = compute_trust_score(
                observation=obs,
                relationship_kind=rel_kind,
            )
            if trust < min_trust:
                continue
            org_id: uuid.UUID = person.current_org_id
            assert org_id is not None
            org_name: str = person.current_org_name or "Unknown"
            insider = TargetCompanyInsider(
                person_id=person.id,
                person_name=person.canonical_name,
                person_role=person.current_role,
                trust_score=trust,
                relationship_kind=rel_kind,
            )
            existing: TargetCompanyMatch | None = by_org.get(org_id)
            if existing is None:
                by_org[org_id] = TargetCompanyMatch(
                    org_id=org_id,
                    org_name=org_name,
                    insiders=[insider],
                    best_trust_score=trust,
                )
                continue
            updated_insiders: list[TargetCompanyInsider] = [*existing.insiders, insider]
            updated_insiders.sort(key=lambda item: item.trust_score, reverse=True)
            by_org[org_id] = TargetCompanyMatch(
                org_id=org_id,
                org_name=org_name,
                insiders=updated_insiders,
                best_trust_score=max(existing.best_trust_score, trust),
            )

        matches: list[TargetCompanyMatch] = sorted(
            by_org.values(),
            key=lambda item: item.best_trust_score,
            reverse=True,
        )
        return matches[:limit]

    async def list_second_degree(
        self,
        user_id: uuid.UUID,
        member_user_ids: list[uuid.UUID],
        *,
        private_person_ids_by_member: dict[uuid.UUID, set[uuid.UUID]],
        min_trust: float = HIGH_TRUST_THRESHOLD,
        limit: int = 50,
    ) -> list[SecondDegreeTargetCompanyMatch]:
        by_org: dict[uuid.UUID, SecondDegreeTargetCompanyMatch] = {}

        for member_id in member_user_ids:
            bridge_user: User | None = await self._db.get(User, member_id)
            bridge_name: str = (
                (bridge_user.display_name or bridge_user.google_profile_name or bridge_user.email)
                if bridge_user is not None
                else "Trusted contact"
            )
            private_ids: set[uuid.UUID] = private_person_ids_by_member.get(member_id, set())

            stmt = (
                select(Person, UserPersonObservation)
                .join(
                    UserPersonObservation,
                    (UserPersonObservation.person_id == Person.id)
                    & (UserPersonObservation.user_id == member_id),
                )
                .where(
                    Person.current_org_id.isnot(None),
                    UserPersonObservation.is_broadcast.is_(False),
                )
            )
            result = await self._db.execute(stmt)
            rows: list[tuple[Person, UserPersonObservation]] = list(result.all())

            for person, obs in rows:
                if person.id in private_ids:
                    continue
                rel_kind: str | None = await self._relationship_kind_for_pair(
                    user_id=member_id,
                    contact_person_id=person.id,
                    observation=obs,
                )
                if not is_high_trust_connection(
                    observation=obs,
                    relationship_kind=rel_kind,
                ):
                    continue
                trust: float = compute_trust_score(
                    observation=obs,
                    relationship_kind=rel_kind,
                )
                if trust < min_trust:
                    continue

                org_id: uuid.UUID = person.current_org_id
                assert org_id is not None
                org_name: str = person.current_org_name or "Unknown"
                insider = SecondDegreeTargetInsider(
                    person_id=person.id,
                    person_name=person.canonical_name,
                    person_role=person.current_role,
                    bridge_user_id=member_id,
                    bridge_name=bridge_name,
                    trust_score=trust,
                )
                existing: SecondDegreeTargetCompanyMatch | None = by_org.get(org_id)
                if existing is None:
                    by_org[org_id] = SecondDegreeTargetCompanyMatch(
                        org_id=org_id,
                        org_name=org_name,
                        insiders=[insider],
                        best_trust_score=trust,
                    )
                    continue
                updated: list[SecondDegreeTargetInsider] = [*existing.insiders, insider]
                updated.sort(key=lambda item: item.trust_score, reverse=True)
                by_org[org_id] = SecondDegreeTargetCompanyMatch(
                    org_id=org_id,
                    org_name=org_name,
                    insiders=updated,
                    best_trust_score=max(existing.best_trust_score, trust),
                )

        matches: list[SecondDegreeTargetCompanyMatch] = sorted(
            by_org.values(),
            key=lambda item: item.best_trust_score,
            reverse=True,
        )
        return matches[:limit]

    async def _relationship_kind_for_pair(
        self,
        *,
        user_id: uuid.UUID,
        contact_person_id: uuid.UUID,
        observation: UserPersonObservation,
    ) -> str | None:
        user: User | None = await self._db.get(User, user_id)
        if user is None or user.person_id is None:
            return None
        a_id: uuid.UUID = min(user.person_id, contact_person_id)
        b_id: uuid.UUID = max(user.person_id, contact_person_id)
        stmt = select(RelationshipClaim).where(
            RelationshipClaim.person_a_id == a_id,
            RelationshipClaim.person_b_id == b_id,
            RelationshipClaim.contributor_user_id == user_id,
        )
        result = await self._db.execute(stmt)
        claims: list[RelationshipClaim] = list(result.scalars().all())
        return best_relationship_kind(claims)
