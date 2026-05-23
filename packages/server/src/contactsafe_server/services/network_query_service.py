import uuid

from sqlalchemy import Text, cast, func, or_, select
from sqlalchemy.dialects.postgresql import ARRAY, array as pg_array
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute, selectinload
from sqlalchemy.sql.elements import ColumnElement

from contactsafe_core.query_plan import QueryIntent, QueryPlan, QuerySortBy
from contactsafe_core.schemas import PersonMatch
from contactsafe_server.db.models import (
    InteractionExcerpt,
    Org,
    Person,
    PersonEdge,
    PersonPersonEdge,
)
from contactsafe_server.services.org_search import expand_org_search_terms


def _org_match_conditions(org_query: str, user_id: uuid.UUID) -> ColumnElement[bool]:
    """Match org query against org names, domains, emails, and excerpt text."""
    terms: list[str] = expand_org_search_terms(org_query)
    if not terms:
        pattern: str = f"%{org_query.lower()}%"
        terms = [org_query.lower()]

    term_conditions: list[ColumnElement[bool]] = []
    email_blob = func.lower(func.array_to_string(Person.email_addresses, " "))

    for term in terms:
        term_pattern: str = f"%{term.lower()}%"
        term_conditions.extend(
            [
                func.lower(Person.current_org_name).like(term_pattern),
                email_blob.like(term_pattern),
                func.exists(
                    select(1)
                    .select_from(Org)
                    .where(
                        Org.id == Person.current_org_id,
                        or_(
                            func.lower(Org.canonical_name).like(term_pattern),
                            func.lower(Org.domain).like(term_pattern),
                        ),
                    )
                    .correlate(Person)
                ),
                func.exists(
                    select(1)
                    .select_from(InteractionExcerpt)
                    .where(
                        InteractionExcerpt.person_id == Person.id,
                        InteractionExcerpt.user_id == user_id,
                        func.lower(InteractionExcerpt.excerpt_text).like(term_pattern),
                    )
                    .correlate(Person)
                ),
            ]
        )

    return or_(*term_conditions)

def _pg_text_array_overlaps(
    column: InstrumentedAttribute[list[str]],
    values: list[str],
) -> ColumnElement[bool]:
    """`column && values` with explicit text[] typing for Postgres."""
    rhs = cast(pg_array(values), ARRAY(Text))
    return column.op("&&")(rhs)


class NetworkQueryService:
    def __init__(self, db: AsyncSession) -> None:
        self._db: AsyncSession = db

    async def execute(
        self,
        *,
        user_id: uuid.UUID,
        plan: QueryPlan,
    ) -> list[PersonMatch]:
        if plan.intent == QueryIntent.SEMANTIC_SEARCH and plan.semantic_query:
            semantic_matches: list[PersonMatch] | None = await self._semantic_search(
                user_id=user_id,
                plan=plan,
            )
            if semantic_matches is not None:
                return semantic_matches

        stmt = (
            select(Person)
            .join(PersonEdge, PersonEdge.person_id == Person.id)
            .options(selectinload(Person.edge), selectinload(Person.current_org))
            .where(Person.user_id == user_id)
        )

        if plan.exclude_broadcast:
            stmt = stmt.where(PersonEdge.is_broadcast.is_(False))

        if plan.require_genuine_contact:
            stmt = stmt.where(PersonEdge.last_genuine_interaction_at.isnot(None))

        for token in plan.name_tokens:
            pattern: str = f"%{token.lower()}%"
            email_blob = func.lower(func.array_to_string(Person.email_addresses, " "))
            stmt = stmt.where(
                or_(
                    func.lower(Person.canonical_name).like(pattern),
                    email_blob.like(pattern),
                )
            )

        if plan.org_names:
            org_conditions: list[ColumnElement[bool]] = [
                _org_match_conditions(org_name, user_id) for org_name in plan.org_names
            ]
            stmt = stmt.where(or_(*org_conditions))

        if plan.categories_any:
            lowered: list[str] = [c.lower() for c in plan.categories_any]
            stmt = stmt.where(_pg_text_array_overlaps(Person.inferred_categories, lowered))

        for role_kw in plan.role_keywords:
            role_pattern: str = f"%{role_kw.lower()}%"
            stmt = stmt.where(func.lower(Person.current_role).like(role_pattern))

        if plan.relationship_types_any:
            lowered_rel: list[str] = [r.lower() for r in plan.relationship_types_any]
            if _is_cooccurrence_relationship_query(lowered_rel):
                stmt = stmt.where(
                    func.exists(
                        select(1)
                        .select_from(PersonPersonEdge)
                        .where(
                            PersonPersonEdge.user_id == user_id,
                            or_(
                                PersonPersonEdge.left_person_id == Person.id,
                                PersonPersonEdge.right_person_id == Person.id,
                            ),
                        )
                        .correlate(Person)
                    )
                )
            else:
                stmt = stmt.where(
                    _pg_text_array_overlaps(PersonEdge.relationship_types, lowered_rel)
                )

        if plan.sort_by == QuerySortBy.LAST_SEEN:
            stmt = stmt.order_by(
                PersonEdge.last_genuine_interaction_at.desc().nullslast(),
                Person.last_seen_in_email.desc().nullslast(),
            )
        else:
            stmt = stmt.order_by(
                PersonEdge.tie_strength_score.desc(),
                PersonEdge.last_genuine_interaction_at.desc().nullslast(),
                Person.last_seen_in_email.desc().nullslast(),
            )

        stmt = stmt.limit(min(plan.limit, 100))
        result = await self._db.execute(stmt)
        people: list[Person] = list(result.scalars().unique().all())

        return [
            self._to_person_match(person, plan)
            for person in people
        ]

    async def _semantic_search(
        self,
        *,
        user_id: uuid.UUID,
        plan: QueryPlan,
    ) -> list[PersonMatch] | None:
        """Vector search on interaction_excerpts when embeddings exist."""
        from contactsafe_server.services.embedding_service import EmbeddingService

        embedder = EmbeddingService()
        query_embedding: list[float] | None = await embedder.embed_text(plan.semantic_query or "")
        if query_embedding is None:
            return None

        try:
            distance = InteractionExcerpt.embedding.cosine_distance(query_embedding)
        except Exception:
            return None

        subq = (
            select(
                InteractionExcerpt.person_id,
                func.min(distance).label("min_distance"),
            )
            .where(InteractionExcerpt.user_id == user_id)
            .group_by(InteractionExcerpt.person_id)
            .order_by(func.min(distance))
            .limit(plan.limit)
            .subquery()
        )

        stmt = (
            select(Person)
            .join(subq, subq.c.person_id == Person.id)
            .options(selectinload(Person.edge), selectinload(Person.current_org))
            .where(Person.user_id == user_id)
            .order_by(subq.c.min_distance)
        )
        result = await self._db.execute(stmt)
        people: list[Person] = list(result.scalars().unique().all())
        return [self._to_person_match(p, plan, reason_prefix="semantic excerpt match") for p in people]

    def _to_person_match(
        self,
        person: Person,
        plan: QueryPlan,
        *,
        reason_prefix: str | None = None,
    ) -> PersonMatch:
        reasons: list[str] = []
        if reason_prefix:
            reasons.append(reason_prefix)
        if plan.name_tokens:
            reasons.append(f"name tokens: {', '.join(plan.name_tokens)}")
        if plan.org_names:
            org_label: str = person.current_org_name or (
                person.current_org.canonical_name if person.current_org else ""
            )
            if org_label:
                reasons.append(f"org: {org_label}")
            else:
                reasons.append(f"org filter: {', '.join(plan.org_names)}")
        if plan.categories_any and person.inferred_categories:
            matched_cats: list[str] = [
                c
                for c in person.inferred_categories
                if c.lower() in {x.lower() for x in plan.categories_any}
            ]
            if matched_cats:
                reasons.append(f"categories: {', '.join(matched_cats)}")
        if plan.role_keywords and person.current_role:
            reasons.append(f"role: {person.current_role}")

        tie: float = person.edge.tie_strength_score if person.edge else 0.0
        relevance_parts: list[str] = []
        if person.current_org_name:
            relevance_parts.append(f"org: {person.current_org_name}")
        if person.current_role:
            relevance_parts.append(f"role: {person.current_role}")
        if person.last_seen_in_email:
            relevance_parts.append(
                f"last email: {person.last_seen_in_email.date().isoformat()}"
            )
        if tie:
            relevance_parts.append(f"tie strength: {tie:.2f}")

        return PersonMatch(
            person_id=person.id,
            name=person.canonical_name,
            emails=list(person.email_addresses),
            org_name=person.current_org_name
            or (person.current_org.canonical_name if person.current_org else None),
            current_role=person.current_role,
            inferred_categories=list(person.inferred_categories),
            last_seen_in_email=person.last_seen_in_email,
            tie_strength_score=tie,
            match_reason="; ".join(reasons) if reasons else "matched graph filters",
            relevance="; ".join(relevance_parts) if relevance_parts else "contact from graph",
        )


def _is_cooccurrence_relationship_query(relationship_types: list[str]) -> bool:
    tokens: set[str] = {x.strip().lower() for x in relationship_types}
    return any(
        token in tokens
        for token in {
            "cooccurrence",
            "co-occurrence",
            "co occurrence",
            "co-occurred",
            "cooccurred",
            "introduced",
            "connected",
        }
    )
