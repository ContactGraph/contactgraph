"""Person ↔ org employment and affiliation edges."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from contactsafe_server.db.models import Org, Person, PersonOrgEdge


class EmploymentService:
    def __init__(self, db: AsyncSession) -> None:
        self._db: AsyncSession = db

    async def upsert_current_employment(
        self,
        *,
        user_id: uuid.UUID,
        person_id: uuid.UUID,
        org_id: uuid.UUID,
        role_title: str | None = None,
        relationship_type: str = "employee",
        source: str = "email_domain",
        confidence: float = 0.7,
    ) -> PersonOrgEdge:
        result = await self._db.execute(
            select(PersonOrgEdge).where(
                PersonOrgEdge.user_id == user_id,
                PersonOrgEdge.person_id == person_id,
                PersonOrgEdge.org_id == org_id,
            )
        )
        edge: PersonOrgEdge | None = result.scalar_one_or_none()
        if edge is None:
            edge = PersonOrgEdge(
                user_id=user_id,
                person_id=person_id,
                org_id=org_id,
                relationship_type=relationship_type,
                role_title=role_title,
                is_current=True,
                source=source,
                confidence=confidence,
            )
            self._db.add(edge)
        else:
            edge.is_current = True
            edge.relationship_type = relationship_type
            if role_title:
                edge.role_title = role_title
            edge.source = source
            edge.confidence = confidence

        await self._db.flush()
        await self.sync_person_denorm_from_employment(person_id)
        return edge

    async def apply_enrichment_to_employment(
        self,
        *,
        person: Person,
        org_name: str | None,
        role_title: str | None,
        source: str,
    ) -> None:
        if not person.current_org_id:
            return
        result = await self._db.execute(
            select(PersonOrgEdge).where(
                PersonOrgEdge.user_id == person.user_id,
                PersonOrgEdge.person_id == person.id,
                PersonOrgEdge.org_id == person.current_org_id,
                PersonOrgEdge.is_current.is_(True),
            )
        )
        edge: PersonOrgEdge | None = result.scalar_one_or_none()
        if edge is None:
            edge = PersonOrgEdge(
                user_id=person.user_id,
                person_id=person.id,
                org_id=person.current_org_id,
                relationship_type="employee",
                role_title=role_title,
                is_current=True,
                source=source,
                confidence=0.75,
            )
            self._db.add(edge)
        else:
            if role_title and not edge.role_title:
                edge.role_title = role_title
            edge.source = source
        if org_name:
            person.current_org_name = org_name
        if role_title:
            person.current_role = role_title
        await self._db.flush()

    async def sync_person_denorm_from_employment(self, person_id: uuid.UUID) -> None:
        person: Person | None = await self._db.get(Person, person_id)
        if person is None:
            return

        result = await self._db.execute(
            select(PersonOrgEdge)
            .where(
                PersonOrgEdge.person_id == person_id,
                PersonOrgEdge.is_current.is_(True),
            )
            .order_by(PersonOrgEdge.confidence.desc())
        )
        edge: PersonOrgEdge | None = result.scalars().first()
        if edge is None:
            person.current_org_id = None
            person.current_org_name = None
            person.current_role = None
            await self._db.flush()
            return

        person.current_org_id = edge.org_id
        person.current_role = edge.role_title
        org: Org | None = await self._db.get(Org, edge.org_id)
        if org is not None:
            person.current_org_name = org.canonical_name
        await self._db.flush()
