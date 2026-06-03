"""Tests for target company queries."""

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from contactsafe_server.db.models import (
    Base,
    Org,
    Person,
    RelationshipClaim,
    User,
    UserPersonObservation,
)
from contactsafe_server.services.target_companies_service import TargetCompaniesService

@pytest.fixture(autouse=True)
async def _setup_tables(db_engine):
    async with db_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


@pytest.fixture
async def user(db_session: AsyncSession) -> User:
    u = User(email="seeker@test.com", display_name="Seeker")
    db_session.add(u)
    await db_session.flush()
    return u


@pytest.fixture
async def user_person(db_session: AsyncSession, user: User) -> Person:
    p = Person(canonical_name="Seeker", primary_email="seeker@test.com")
    db_session.add(p)
    await db_session.flush()
    user.person_id = p.id
    await db_session.flush()
    return p


async def test_list_first_degree_groups_by_org(
    db_session: AsyncSession,
    user: User,
    user_person: Person,
) -> None:
    org = Org(canonical_name="Acme Corp", primary_domain="acme.com")
    insider = Person(
        canonical_name="Jane Insider",
        primary_email="jane@acme.com",
        current_org_name="Acme Corp",
    )
    db_session.add_all([org, insider])
    await db_session.flush()
    insider.current_org_id = org.id
    await db_session.flush()

    db_session.add(UserPersonObservation(
        user_id=user.id,
        person_id=insider.id,
        tie_strength_score=0.8,
        outbound_count=3,
        relationship_types=["phone_contacts_upload"],
        is_human=True,
    ))
    db_session.add(RelationshipClaim(
        person_a_id=min(user_person.id, insider.id),
        person_b_id=max(user_person.id, insider.id),
        kind="phone_contact",
        contributor_user_id=user.id,
        contributor_source_kind="phone_contacts_upload",
    ))
    await db_session.flush()

    service = TargetCompaniesService(db_session)
    matches = await service.list_first_degree(user.id)
    assert len(matches) == 1
    assert matches[0].org_name == "Acme Corp"
    assert matches[0].insiders[0].person_name == "Jane Insider"
