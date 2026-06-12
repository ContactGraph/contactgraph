"""User ↔ org relationship edges aggregated from contact activity."""

import uuid
from datetime import datetime

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from contactsafe_server.db.models import Org, OrgEdge, Person, PersonEdge, PersonOrgEdge
from contactsafe_server.services.org_industry_taxonomy import is_investor_industry_tag


class OrgEdgeService:
    def __init__(self, db: AsyncSession) -> None:
        self._db: AsyncSession = db

    async def rebuild_org_edges_for_user(self, user_id: uuid.UUID) -> None:
        await self._db.execute(delete(OrgEdge).where(OrgEdge.user_id == user_id))

        result = await self._db.execute(
            select(PersonOrgEdge, PersonEdge, Person)
            .join(Person, Person.id == PersonOrgEdge.person_id)
            .join(
                PersonEdge,
                (PersonEdge.person_id == Person.id) & (PersonEdge.user_id == user_id),
            )
            .where(
                PersonOrgEdge.user_id == user_id,
                PersonOrgEdge.is_current.is_(True),
                PersonEdge.is_automated.is_(False),
            )
        )
        rows = result.all()

        by_org: dict[uuid.UUID, dict[str, object]] = {}
        for employment, person_edge, person in rows:
            org_id: uuid.UUID = employment.org_id
            bucket: dict[str, object] | None = by_org.get(org_id)
            if bucket is None:
                bucket = {
                    "person_ids": set(),
                    "email_count": 0,
                    "tie_strength": 0.0,
                    "last_interaction": None,
                }
                by_org[org_id] = bucket

            person_ids: set[uuid.UUID] = bucket["person_ids"]  # type: ignore[assignment]
            person_ids.add(person.id)
            bucket["email_count"] = int(bucket["email_count"]) + person_edge.email_count
            bucket["tie_strength"] = max(
                float(bucket["tie_strength"]), person_edge.tie_strength_score
            )
            last_at: datetime | None = person_edge.last_genuine_interaction_at or person.last_seen_in_email
            prev: datetime | None = bucket["last_interaction"]  # type: ignore[assignment]
            if last_at is not None and (prev is None or last_at > prev):
                bucket["last_interaction"] = last_at

        for org_id, bucket in by_org.items():
            org: Org | None = await self._db.get(Org, org_id)
            if org is None:
                continue
            person_ids_set: set[uuid.UUID] = bucket["person_ids"]  # type: ignore[assignment]
            relationship_types: list[str] = _infer_org_relationship_types(org, len(person_ids_set))
            self._db.add(
                OrgEdge(
                    user_id=user_id,
                    org_id=org_id,
                    relationship_types=relationship_types,
                    associated_person_ids=sorted(person_ids_set),
                    total_email_count=int(bucket["email_count"]),
                    last_interaction_at=bucket["last_interaction"],  # type: ignore[arg-type]
                    tie_strength_score=float(bucket["tie_strength"]),
                )
            )

        await self._db.flush()


def _infer_org_relationship_types(org: Org, contact_count: int) -> list[str]:
    types: list[str] = ["contact"]
    domain: str = org.domain.lower()
    if domain.endswith(".edu"):
        types.append("school")
    if domain.endswith(".org"):
        types.append("nonprofit")
    if domain.endswith(".gov"):
        types.append("government")
    if any(is_investor_industry_tag(cat) or cat in ("vc", "investor") for cat in org.categories):
        types.append("investor")
    if contact_count >= 3:
        types.append("community")
    return list(dict.fromkeys(types))
