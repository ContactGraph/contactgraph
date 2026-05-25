"""Tests for claim_writer — idempotent upserts on re-sync."""

import uuid

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from contactsafe_server.db.models import (
    Base,
    EmploymentClaim,
    Org,
    Person,
    PersonAttributeClaim,
    RelationshipClaim,
    User,
)
from contactsafe_server.services.claim_writer import (
    record_employment,
    record_person_attribute,
    record_relationship,
)

pytestmark = pytest.mark.anyio


@pytest.fixture(autouse=True)
async def _setup_tables(db_engine):
    async with db_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


@pytest.fixture
async def person(db_session: AsyncSession) -> Person:
    p = Person(canonical_name="Test Person", primary_email="test@example.com")
    db_session.add(p)
    await db_session.flush()
    return p


@pytest.fixture
async def org(db_session: AsyncSession) -> Org:
    o = Org(canonical_name="Test Org", primary_domain="example.com")
    db_session.add(o)
    await db_session.flush()
    return o


@pytest.fixture
async def user_id(db_session: AsyncSession) -> uuid.UUID:
    user = User(email=f"claim-writer-{uuid.uuid4()}@example.com")
    db_session.add(user)
    await db_session.flush()
    return user.id


async def test_employment_idempotent(
    db_session: AsyncSession, person: Person, org: Org, user_id: uuid.UUID
) -> None:
    await record_employment(
        db_session,
        person_id=person.id,
        org_id=org.id,
        role_title="Engineer",
        contributor_user_id=user_id,
        contributor_source_kind="gmail_domain",
        confidence=0.5,
    )
    await record_employment(
        db_session,
        person_id=person.id,
        org_id=org.id,
        role_title="Senior Engineer",
        contributor_user_id=user_id,
        contributor_source_kind="gmail_domain",
        confidence=0.7,
    )

    result = await db_session.execute(select(func.count()).select_from(EmploymentClaim))
    assert result.scalar() == 1

    result = await db_session.execute(
        select(EmploymentClaim).where(EmploymentClaim.person_id == person.id)
    )
    claim: EmploymentClaim = result.scalar_one()
    assert claim.role_title == "Senior Engineer"
    assert claim.confidence == 0.7


async def test_relationship_idempotent(
    db_session: AsyncSession, user_id: uuid.UUID
) -> None:
    p1 = Person(canonical_name="A", primary_email="a@test.com")
    p2 = Person(canonical_name="B", primary_email="b@test.com")
    db_session.add_all([p1, p2])
    await db_session.flush()

    await record_relationship(
        db_session,
        person_a_id=p1.id,
        person_b_id=p2.id,
        kind="co_thread",
        observed_count=3,
        contributor_user_id=user_id,
    )
    await record_relationship(
        db_session,
        person_a_id=p1.id,
        person_b_id=p2.id,
        kind="co_thread",
        observed_count=5,
        contributor_user_id=user_id,
    )

    result = await db_session.execute(select(func.count()).select_from(RelationshipClaim))
    assert result.scalar() == 1

    result = await db_session.execute(select(RelationshipClaim))
    claim: RelationshipClaim = result.scalar_one()
    assert claim.observed_count == 8


async def test_person_attribute_idempotent(
    db_session: AsyncSession, person: Person, user_id: uuid.UUID
) -> None:
    await record_person_attribute(
        db_session,
        person_id=person.id,
        kind="category",
        value="vc",
        contributor_user_id=user_id,
        contributor_source_kind="heuristic",
        confidence=0.5,
    )
    await record_person_attribute(
        db_session,
        person_id=person.id,
        kind="category",
        value="vc",
        contributor_user_id=user_id,
        contributor_source_kind="heuristic",
        confidence=0.8,
    )

    result = await db_session.execute(
        select(func.count()).select_from(PersonAttributeClaim)
    )
    assert result.scalar() == 1

    result = await db_session.execute(select(PersonAttributeClaim))
    claim: PersonAttributeClaim = result.scalar_one()
    assert claim.confidence == 0.8


async def test_multiple_categories_from_same_source(
    db_session: AsyncSession, person: Person, user_id: uuid.UUID
) -> None:
    """Multi-valued kinds (category) use the value as part of the key."""
    await record_person_attribute(
        db_session,
        person_id=person.id,
        kind="category",
        value="vc",
        contributor_user_id=user_id,
        contributor_source_kind="heuristic",
    )
    await record_person_attribute(
        db_session,
        person_id=person.id,
        kind="category",
        value="founder",
        contributor_user_id=user_id,
        contributor_source_kind="heuristic",
    )

    result = await db_session.execute(
        select(func.count()).select_from(PersonAttributeClaim)
    )
    assert result.scalar() == 2
