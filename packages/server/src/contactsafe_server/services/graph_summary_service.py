"""High-level summaries of a user's contact graph."""

import uuid
from collections import Counter

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from contactsafe_core.query_plan import QueryPlan
from contactsafe_core.schemas import (
    CategoryCount,
    DescribeGraphResult,
    OrgCount,
    PersonMatch,
)
from contactsafe_server.db.models import Person, PersonEdge
from contactsafe_server.services.network_query_service import NetworkQueryService

_DEFAULT_STRONGEST_TIES_LIMIT: int = 5
_DEFAULT_TOP_CATEGORIES_LIMIT: int = 10
_DEFAULT_TOP_ORGS_LIMIT: int = 10


class GraphSummaryService:
    def __init__(self, db: AsyncSession) -> None:
        self._db: AsyncSession = db

    async def describe(
        self,
        user_id: uuid.UUID,
        *,
        strongest_ties_limit: int = _DEFAULT_STRONGEST_TIES_LIMIT,
        top_categories_limit: int = _DEFAULT_TOP_CATEGORIES_LIMIT,
        top_orgs_limit: int = _DEFAULT_TOP_ORGS_LIMIT,
    ) -> DescribeGraphResult:
        counts = await self._load_edge_counts(user_id)
        queryable_people = await self._load_queryable_people(user_id)

        category_counter: Counter[str] = Counter()
        org_counter: Counter[str] = Counter()
        for person in queryable_people:
            for category in person.inferred_categories:
                normalized: str = category.strip().lower()
                if normalized:
                    category_counter[normalized] += 1
            org_name: str | None = person.current_org_name
            if org_name and org_name.strip():
                org_counter[org_name.strip()] += 1

        top_categories: list[CategoryCount] = [
            CategoryCount(category=category, count=count)
            for category, count in category_counter.most_common(top_categories_limit)
        ]
        top_orgs: list[OrgCount] = [
            OrgCount(org_name=org_name, count=count)
            for org_name, count in org_counter.most_common(top_orgs_limit)
        ]

        strongest_ties: list[PersonMatch] = await NetworkQueryService(self._db).execute(
            user_id=user_id,
            plan=QueryPlan(
                exclude_broadcast=True,
                exclude_automated=True,
                limit=max(1, strongest_ties_limit),
            ),
        )

        queryable_contacts: int = len(queryable_people)
        message: str = self._build_message(
            queryable_contacts=queryable_contacts,
            total_contacts=counts["total"],
            top_categories=top_categories,
            top_orgs=top_orgs,
        )

        return DescribeGraphResult(
            total_contacts=counts["total"],
            human_contacts=counts["human"],
            broadcast_contacts=counts["broadcast"],
            automated_contacts=counts["automated"],
            queryable_contacts=queryable_contacts,
            top_categories=top_categories,
            top_orgs=top_orgs,
            strongest_ties=strongest_ties,
            message=message,
        )

    async def _load_edge_counts(self, user_id: uuid.UUID) -> dict[str, int]:
        result = await self._db.execute(
            select(
                func.count(Person.id).label("total"),
                func.count(Person.id)
                .filter(PersonEdge.is_human.is_(True))
                .label("human"),
                func.count(Person.id)
                .filter(PersonEdge.is_broadcast.is_(True))
                .label("broadcast"),
                func.count(Person.id)
                .filter(PersonEdge.is_automated.is_(True))
                .label("automated"),
            )
            .select_from(Person)
            .join(
                PersonEdge,
                (PersonEdge.person_id == Person.id) & (PersonEdge.user_id == user_id),
            )
            .where(Person.user_id == user_id)
        )
        row = result.one()
        return {
            "total": int(row.total),
            "human": int(row.human),
            "broadcast": int(row.broadcast),
            "automated": int(row.automated),
        }

    async def _load_queryable_people(self, user_id: uuid.UUID) -> list[Person]:
        result = await self._db.execute(
            select(Person)
            .join(
                PersonEdge,
                (PersonEdge.person_id == Person.id) & (PersonEdge.user_id == user_id),
            )
            .options(selectinload(Person.edge), selectinload(Person.current_org))
            .where(
                Person.user_id == user_id,
                PersonEdge.is_broadcast.is_(False),
                PersonEdge.is_automated.is_(False),
            )
        )
        return list(result.scalars().unique().all())

    def _build_message(
        self,
        *,
        queryable_contacts: int,
        total_contacts: int,
        top_categories: list[CategoryCount],
        top_orgs: list[OrgCount],
    ) -> str:
        if total_contacts == 0:
            return "No contacts in your graph yet. Run sync_source after connecting Gmail."

        parts: list[str] = [
            (
                f"Graph has {total_contacts} contact(s); "
                f"{queryable_contacts} are queryable (human, non-newsletter, non-automated)."
            )
        ]
        if top_categories:
            category_bits: list[str] = [
                f"{item.category} ({item.count})" for item in top_categories[:5]
            ]
            parts.append(f"Top categories: {', '.join(category_bits)}.")
        if top_orgs:
            org_bits: list[str] = [f"{item.org_name} ({item.count})" for item in top_orgs[:5]]
            parts.append(f"Top orgs: {', '.join(org_bits)}.")
        parts.append("Use query_network for filtered searches.")
        return " ".join(parts)
