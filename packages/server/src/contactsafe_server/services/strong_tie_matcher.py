"""Identify contacts appearing in both LinkedIn connections and personal sources."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import Select, and_, exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from contactsafe_server.db.models import EmploymentClaim, Person, PersonAlias, UserPersonObservation
from contactsafe_server.services.scrapingdog_client import extract_linkedin_slug

LINKEDIN_CONNECTIONS_RELATIONSHIP: str = "linkedin_connections_upload"
PERSONAL_RELATIONSHIP_TYPES: tuple[str, ...] = (
    "phone_contacts_upload",
    "google_contact",
)
SCRAPINGDOG_SOURCE_KIND: str = "scrapingdog_linkedin"


@dataclass(frozen=True, slots=True)
class StrongTieMatch:
    person_id: uuid.UUID
    canonical_name: str
    linkedin_url: str
    linkedin_slug: str
    tie_strength_score: float
    primary_email: str | None
    phone_number: str | None
    current_org_name: str | None
    current_role: str | None
    already_scraped: bool


def _linkedin_observation_exists(user_id: uuid.UUID) -> exists:
    return exists(
        select(UserPersonObservation.person_id).where(
            UserPersonObservation.user_id == user_id,
            UserPersonObservation.person_id == Person.id,
            UserPersonObservation.relationship_types.any(LINKEDIN_CONNECTIONS_RELATIONSHIP),
        )
    ).correlate(Person)


def _personal_observation_exists(user_id: uuid.UUID) -> exists:
    personal_type_match = or_(
        *[
            UserPersonObservation.relationship_types.any(relationship_type)
            for relationship_type in PERSONAL_RELATIONSHIP_TYPES
        ],
    )
    gmail_match = and_(
        UserPersonObservation.is_human.is_(True),
        UserPersonObservation.is_broadcast.is_(False),
        UserPersonObservation.is_automated.is_(False),
        UserPersonObservation.email_count > 0,
    )
    return exists(
        select(UserPersonObservation.person_id).where(
            UserPersonObservation.user_id == user_id,
            UserPersonObservation.person_id == Person.id,
            or_(personal_type_match, gmail_match),
        )
    ).correlate(Person)


def _linkedin_alias_exists() -> exists:
    return exists(
        select(PersonAlias.person_id).where(
            PersonAlias.person_id == Person.id,
            PersonAlias.kind == "linkedin_url",
        )
    ).correlate(Person)


def _scrapingdog_claim_exists() -> exists:
    return exists(
        select(EmploymentClaim.person_id).where(
            EmploymentClaim.person_id == Person.id,
            EmploymentClaim.contributor_source_kind == SCRAPINGDOG_SOURCE_KIND,
        )
    ).correlate(Person)


def build_strong_tie_query(
    user_id: uuid.UUID,
    *,
    skip_already_scraped: bool = True,
    limit: int | None = None,
) -> Select[tuple[Person, UserPersonObservation, str, bool]]:
    linkedin_alias = (
        select(PersonAlias.value)
        .where(
            PersonAlias.person_id == Person.id,
            PersonAlias.kind == "linkedin_url",
        )
        .order_by(PersonAlias.first_seen_at.asc())
        .limit(1)
        .scalar_subquery()
    )

    stmt: Select[tuple[Person, UserPersonObservation, str, bool]] = (
        select(
            Person,
            UserPersonObservation,
            linkedin_alias.label("linkedin_url"),
            _scrapingdog_claim_exists().label("already_scraped"),
        )
        .join(
            UserPersonObservation,
            and_(
                UserPersonObservation.person_id == Person.id,
                UserPersonObservation.user_id == user_id,
            ),
        )
        .where(
            _linkedin_observation_exists(user_id),
            _personal_observation_exists(user_id),
            _linkedin_alias_exists(),
            UserPersonObservation.is_human.is_(True),
            UserPersonObservation.is_broadcast.is_(False),
            UserPersonObservation.is_automated.is_(False),
        )
        .order_by(UserPersonObservation.tie_strength_score.desc())
    )

    if skip_already_scraped:
        stmt = stmt.where(~_scrapingdog_claim_exists())

    if limit is not None:
        stmt = stmt.limit(limit)

    return stmt


async def find_strong_ties(
    session: AsyncSession,
    user_id: uuid.UUID,
    *,
    skip_already_scraped: bool = True,
    limit: int | None = None,
) -> list[StrongTieMatch]:
    stmt = build_strong_tie_query(
        user_id,
        skip_already_scraped=skip_already_scraped,
        limit=limit,
    )
    result = await session.execute(stmt)
    matches: list[StrongTieMatch] = []

    for person, obs, linkedin_url, already_scraped in result.all():
        if not isinstance(linkedin_url, str) or not linkedin_url.strip():
            continue
        slug: str | None = extract_linkedin_slug(linkedin_url)
        if slug is None:
            continue

        phone_number: str | None = person.phone_numbers[0] if person.phone_numbers else None
        matches.append(
            StrongTieMatch(
                person_id=person.id,
                canonical_name=person.canonical_name,
                linkedin_url=linkedin_url.rstrip("/"),
                linkedin_slug=slug,
                tie_strength_score=float(obs.tie_strength_score),
                primary_email=person.primary_email,
                phone_number=phone_number,
                current_org_name=person.current_org_name,
                current_role=person.current_role,
                already_scraped=bool(already_scraped),
            )
        )

    return matches


async def count_strong_ties(
    session: AsyncSession,
    user_id: uuid.UUID,
    *,
    skip_already_scraped: bool = True,
) -> int:
    count_stmt = select(func.count()).select_from(
        build_strong_tie_query(
            user_id,
            skip_already_scraped=skip_already_scraped,
        ).subquery()
    )
    result = await session.execute(count_stmt)
    return int(result.scalar_one())
