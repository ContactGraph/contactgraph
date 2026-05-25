import logging
import uuid

from sqlalchemy import Text, cast, func, literal, or_, select
from sqlalchemy.dialects.postgresql import ARRAY, array as pg_array
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute
from sqlalchemy.sql.elements import ColumnElement

from contactsafe_core.query_plan import QueryIntent, QueryPlan, QuerySortBy
from contactsafe_core.schemas import PersonMatch
from contactsafe_server.db.models import (
    EmploymentClaim,
    InteractionExcerpt,
    Org,
    Person,
    PersonAlias,
    UserPersonObservation,
    UserRelationshipObservation,
)
from contactsafe_server.services.org_search import expand_org_search_terms

logger: logging.Logger = logging.getLogger(__name__)

_CATEGORY_ALIASES: dict[str, str] = {
    "investor": "vc",
    "investors": "vc",
    "venture_capital": "vc",
    "venture capital": "vc",
    "founders": "founder",
    "engineers": "engineer",
}


def _normalize_category_tokens(categories: list[str]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for category in categories:
        lowered: str = category.strip().lower()
        if not lowered:
            continue
        canonical: str = _CATEGORY_ALIASES.get(lowered, lowered)
        if canonical in seen:
            continue
        seen.add(canonical)
        normalized.append(canonical)
    return normalized


def _org_match_conditions(org_query: str, user_id: uuid.UUID) -> ColumnElement[bool]:
    """Match org query against person org names, employment claims, and excerpts."""
    terms: list[str] = expand_org_search_terms(org_query)
    if not terms:
        terms = [org_query.lower()]

    term_conditions: list[ColumnElement[bool]] = []

    for term in terms:
        term_pattern: str = f"%{term.lower()}%"
        term_conditions.extend(
            [
                func.lower(Person.current_org_name).like(term_pattern),
                func.lower(Person.primary_email).like(term_pattern),
                func.exists(
                    select(1)
                    .select_from(EmploymentClaim)
                    .join(Org, Org.id == EmploymentClaim.org_id)
                    .where(
                        EmploymentClaim.person_id == Person.id,
                        EmploymentClaim.is_current.is_(True),
                        or_(
                            func.lower(Org.canonical_name).like(term_pattern),
                            func.lower(Org.primary_domain).like(term_pattern),
                        ),
                    )
                    .correlate(Person)
                ),
                func.exists(
                    select(1)
                    .select_from(Org)
                    .where(
                        Org.id == Person.current_org_id,
                        or_(
                            func.lower(Org.canonical_name).like(term_pattern),
                            func.lower(Org.primary_domain).like(term_pattern),
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
    rhs = cast(pg_array(values), ARRAY(Text))
    return column.op("&&")(rhs)


def _category_match_condition(categories: list[str]) -> ColumnElement[bool]:
    lowered: list[str] = _normalize_category_tokens(categories)
    if not lowered:
        return cast(literal(True), ColumnElement[bool])
    return _pg_text_array_overlaps(Person.inferred_categories, lowered)


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

        matches: list[PersonMatch] = await self._execute_plan(user_id, plan)
        if matches:
            return matches

        relaxed: QueryPlan | None = self._relax_plan(plan)
        if relaxed is not None:
            logger.info("Strict query returned 0 results, retrying with relaxed plan")
            return await self._execute_plan(user_id, relaxed)
        return []

    @staticmethod
    def _relax_plan(plan: QueryPlan) -> QueryPlan | None:
        """Drop the most restrictive optional filters for a retry."""
        relaxed: QueryPlan = plan.model_copy(deep=True)
        changed: bool = False
        if relaxed.relationship_types_any:
            relaxed.relationship_types_any = []
            changed = True
        if relaxed.require_genuine_contact:
            relaxed.require_genuine_contact = False
            changed = True
        if relaxed.categories_any:
            relaxed.categories_any = []
            changed = True
        if relaxed.role_keywords:
            relaxed.role_keywords = []
            changed = True
        return relaxed if changed else None

    async def _execute_plan(
        self,
        user_id: uuid.UUID,
        plan: QueryPlan,
    ) -> list[PersonMatch]:
        stmt = (
            select(Person, UserPersonObservation)
            .join(
                UserPersonObservation,
                (UserPersonObservation.person_id == Person.id)
                & (UserPersonObservation.user_id == user_id),
            )
        )

        if plan.exclude_broadcast:
            stmt = stmt.where(UserPersonObservation.is_broadcast.is_(False))

        if plan.exclude_automated:
            stmt = stmt.where(UserPersonObservation.is_automated.is_(False))

        if plan.require_genuine_contact:
            stmt = stmt.where(UserPersonObservation.last_genuine_interaction_at.isnot(None))

        for token in plan.name_tokens:
            pattern: str = f"%{token.lower()}%"
            email_pattern: str = f"%{token.lower()}%"
            stmt = stmt.where(
                or_(
                    func.lower(Person.canonical_name).like(pattern),
                    func.lower(Person.primary_email).like(email_pattern),
                    func.exists(
                        select(1)
                        .select_from(PersonAlias)
                        .where(
                            PersonAlias.person_id == Person.id,
                            PersonAlias.kind == "email",
                            func.lower(PersonAlias.value).like(email_pattern),
                        )
                        .correlate(Person)
                    ),
                )
            )

        if plan.org_names:
            org_conditions: list[ColumnElement[bool]] = [
                _org_match_conditions(org_name, user_id) for org_name in plan.org_names
            ]
            stmt = stmt.where(or_(*org_conditions))

        if plan.categories_any:
            stmt = stmt.where(_category_match_condition(plan.categories_any))

        for role_kw in plan.role_keywords:
            role_pattern: str = f"%{role_kw.lower()}%"
            stmt = stmt.where(func.lower(Person.current_role).like(role_pattern))

        if plan.relationship_types_any:
            lowered_rel: list[str] = [r.lower() for r in plan.relationship_types_any]
            if _is_cooccurrence_relationship_query(lowered_rel):
                stmt = stmt.where(
                    func.exists(
                        select(1)
                        .select_from(UserRelationshipObservation)
                        .where(
                            UserRelationshipObservation.user_id == user_id,
                            or_(
                                UserRelationshipObservation.person_a_id == Person.id,
                                UserRelationshipObservation.person_b_id == Person.id,
                            ),
                        )
                        .correlate(Person)
                    )
                )
            else:
                stmt = stmt.where(
                    _pg_text_array_overlaps(UserPersonObservation.relationship_types, lowered_rel)
                )

        if plan.sort_by == QuerySortBy.LAST_SEEN:
            stmt = stmt.order_by(
                UserPersonObservation.last_genuine_interaction_at.desc().nullslast(),
                UserPersonObservation.last_observed_at.desc().nullslast(),
            )
        else:
            stmt = stmt.order_by(
                UserPersonObservation.tie_strength_score.desc(),
                UserPersonObservation.last_genuine_interaction_at.desc().nullslast(),
            )

        stmt = stmt.limit(min(plan.limit, 100))
        result = await self._db.execute(stmt)
        rows: list[tuple[Person, UserPersonObservation]] = list(result.unique().all())

        matches: list[PersonMatch] = []
        for person, obs in rows:
            aliases: list[str] = await self._load_also_known_as(person.id)
            matches.append(self._to_person_match(person, obs, plan, also_known_as=aliases))
        return matches

    async def _semantic_search(
        self,
        *,
        user_id: uuid.UUID,
        plan: QueryPlan,
    ) -> list[PersonMatch] | None:
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
            select(Person, UserPersonObservation)
            .join(subq, subq.c.person_id == Person.id)
            .join(
                UserPersonObservation,
                (UserPersonObservation.person_id == Person.id)
                & (UserPersonObservation.user_id == user_id),
            )
            .order_by(subq.c.min_distance)
        )
        result = await self._db.execute(stmt)
        rows = list(result.unique().all())
        matches: list[PersonMatch] = []
        for person, obs in rows:
            aliases: list[str] = await self._load_also_known_as(person.id)
            matches.append(self._to_person_match(
                person, obs, plan,
                reason_prefix="semantic excerpt match",
                also_known_as=aliases,
            ))
        return matches

    async def _load_also_known_as(self, person_id: uuid.UUID) -> list[str]:
        result = await self._db.execute(
            select(PersonAlias.value)
            .where(
                PersonAlias.person_id == person_id,
                PersonAlias.kind.in_(["email", "linkedin_url", "github_url", "bluesky_handle"]),
            )
        )
        return list(result.scalars().all())

    def _to_person_match(
        self,
        person: Person,
        obs: UserPersonObservation,
        plan: QueryPlan,
        *,
        reason_prefix: str | None = None,
        also_known_as: list[str] | None = None,
    ) -> PersonMatch:
        reasons: list[str] = []
        if reason_prefix:
            reasons.append(reason_prefix)
        if plan.name_tokens:
            reasons.append(f"name tokens: {', '.join(plan.name_tokens)}")
        if plan.org_names:
            org_label: str = person.current_org_name or ""
            if org_label:
                reasons.append(f"org: {org_label}")
            else:
                reasons.append(f"org filter: {', '.join(plan.org_names)}")
        if plan.categories_any and person.inferred_categories:
            normalized_requested: set[str] = {
                _CATEGORY_ALIASES.get(c.strip().lower(), c.strip().lower())
                for c in plan.categories_any
            }
            matched_cats: list[str] = [
                c
                for c in person.inferred_categories
                if _CATEGORY_ALIASES.get(c.lower(), c.lower()) in normalized_requested
            ]
            if matched_cats:
                reasons.append(f"categories: {', '.join(matched_cats)}")
        if plan.role_keywords and person.current_role:
            reasons.append(f"role: {person.current_role}")

        tie: float = obs.tie_strength_score
        relevance_parts: list[str] = []
        if person.current_org_name:
            relevance_parts.append(f"org: {person.current_org_name}")
        if person.current_role:
            relevance_parts.append(f"role: {person.current_role}")
        if obs.last_observed_at:
            relevance_parts.append(
                f"last email: {obs.last_observed_at.date().isoformat()}"
            )
        if tie:
            relevance_parts.append(f"tie strength: {tie:.2f}")
        social: dict[str, str] = dict(person.social_profiles or {})
        if social:
            relevance_parts.append(f"profiles: {', '.join(social.keys())}")
        if person.bio_summary:
            relevance_parts.append(f"bio: {person.bio_summary[:120]}")

        all_emails: list[str] = [person.primary_email] if person.primary_email else []
        if also_known_as:
            for aka in also_known_as:
                if aka not in all_emails:
                    all_emails.append(aka)

        return PersonMatch(
            person_id=person.id,
            name=person.canonical_name,
            emails=all_emails,
            org_name=person.current_org_name,
            current_role=person.current_role,
            inferred_categories=list(person.inferred_categories),
            social_profiles=social,
            bio_summary=person.bio_summary,
            also_known_as=also_known_as or [],
            last_seen_in_email=obs.last_observed_at,
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
