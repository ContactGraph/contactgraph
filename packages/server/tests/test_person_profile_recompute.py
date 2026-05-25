"""Tests for PersonProfileRecompute — derives person columns from claims."""

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from contactsafe_server.db.models import (
    Base,
    EmploymentClaim,
    Org,
    Person,
    PersonAttributeClaim,
    User,
    UserPersonObservation,
)
from contactsafe_server.services.person_profile_recompute import PersonProfileRecompute

pytestmark = pytest.mark.anyio


@pytest.fixture(autouse=True)
async def _setup_tables(db_engine):
    async with db_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


@pytest.fixture
async def user(db_session: AsyncSession) -> User:
    u = User(email="tester@test.com")
    db_session.add(u)
    await db_session.flush()
    return u


@pytest.fixture
async def person(db_session: AsyncSession) -> Person:
    p = Person(canonical_name="Test Person", primary_email="test@example.com")
    db_session.add(p)
    await db_session.flush()
    return p


@pytest.fixture
async def org(db_session: AsyncSession) -> Org:
    o = Org(canonical_name="Sticker Ventures", primary_domain="sticker.vc")
    db_session.add(o)
    await db_session.flush()
    return o


async def test_recompute_employment(
    db_session: AsyncSession, user: User, person: Person, org: Org,
) -> None:
    db_session.add(UserPersonObservation(
        user_id=user.id, person_id=person.id, email_count=10,
    ))
    db_session.add(EmploymentClaim(
        person_id=person.id,
        org_id=org.id,
        role_title="Partner",
        is_current=True,
        contributor_user_id=user.id,
        contributor_source_kind="exa",
        confidence=0.9,
    ))
    await db_session.flush()

    recompute = PersonProfileRecompute(db_session)
    await recompute.recompute_for_user(user.id)

    result = await db_session.execute(select(Person).where(Person.id == person.id))
    updated: Person = result.scalar_one()
    assert updated.current_org_id == org.id
    assert updated.current_org_name == "Sticker Ventures"
    assert updated.current_role == "Partner"


async def test_recompute_highest_confidence_wins(
    db_session: AsyncSession, user: User, person: Person,
) -> None:
    org1 = Org(canonical_name="Org A", primary_domain="a.com")
    org2 = Org(canonical_name="Org B", primary_domain="b.com")
    db_session.add_all([org1, org2])
    await db_session.flush()

    db_session.add(UserPersonObservation(
        user_id=user.id, person_id=person.id, email_count=5,
    ))
    db_session.add(EmploymentClaim(
        person_id=person.id, org_id=org1.id, role_title="Junior",
        is_current=True, contributor_user_id=user.id,
        contributor_source_kind="heuristic", confidence=0.4,
    ))
    db_session.add(EmploymentClaim(
        person_id=person.id, org_id=org2.id, role_title="CTO",
        is_current=True, contributor_user_id=user.id,
        contributor_source_kind="exa", confidence=0.9,
    ))
    await db_session.flush()

    recompute = PersonProfileRecompute(db_session)
    await recompute.recompute_for_user(user.id)

    result = await db_session.execute(select(Person).where(Person.id == person.id))
    updated: Person = result.scalar_one()
    assert updated.current_org_id == org2.id
    assert updated.current_role == "CTO"


async def test_recompute_categories_and_social(
    db_session: AsyncSession, user: User, person: Person,
) -> None:
    db_session.add(UserPersonObservation(
        user_id=user.id, person_id=person.id, email_count=3,
    ))
    db_session.add(PersonAttributeClaim(
        person_id=person.id, kind="category", value="vc",
        contributor_user_id=user.id, contributor_source_kind="heuristic",
    ))
    db_session.add(PersonAttributeClaim(
        person_id=person.id, kind="category", value="founder",
        contributor_user_id=user.id, contributor_source_kind="llm",
    ))
    db_session.add(PersonAttributeClaim(
        person_id=person.id, kind="social_profile.github", value="https://github.com/test",
        contributor_user_id=user.id, contributor_source_kind="exa",
    ))
    db_session.add(PersonAttributeClaim(
        person_id=person.id, kind="bio_summary", value="A short bio.",
        contributor_user_id=user.id, contributor_source_kind="exa",
    ))
    await db_session.flush()

    recompute = PersonProfileRecompute(db_session)
    await recompute.recompute_for_user(user.id)

    result = await db_session.execute(select(Person).where(Person.id == person.id))
    updated: Person = result.scalar_one()
    assert "vc" in updated.inferred_categories
    assert "founder" in updated.inferred_categories
    assert updated.social_profiles.get("github") == "https://github.com/test"
    assert updated.bio_summary == "A short bio."
