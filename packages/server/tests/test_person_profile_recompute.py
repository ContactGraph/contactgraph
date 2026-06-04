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
    PersonAlias,
    PersonAttributeClaim,
    User,
    UserPersonObservation,
)
from contactsafe_server.services.person_profile_recompute import (
    PersonProfileRecompute,
    sanitize_display_name,
)

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

    emp_result = await db_session.execute(
        select(EmploymentClaim).where(EmploymentClaim.person_id == person.id),
    )
    claims: list[EmploymentClaim] = list(emp_result.scalars().all())
    org1_claim = next(c for c in claims if c.org_id == org1.id)
    assert org1_claim.is_current is False
    assert org1_claim.ended_at is not None


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


# ---------------------------------------------------------------------------
# sanitize_display_name
# ---------------------------------------------------------------------------


def test_sanitize_strips_single_quotes() -> None:
    assert sanitize_display_name("'Kelli Stockdale'") == "Kelli Stockdale"


def test_sanitize_strips_unicode_quotes() -> None:
    assert sanitize_display_name("\u2018Wiraj W. Karve\u2019") == "Wiraj W. Karve"


def test_sanitize_strips_double_quotes() -> None:
    assert sanitize_display_name('"Bob Smith"') == "Bob Smith"


def test_sanitize_leaves_clean_names_alone() -> None:
    assert sanitize_display_name("Jane Doe") == "Jane Doe"


def test_sanitize_empty_string() -> None:
    assert sanitize_display_name("") == ""


async def test_recompute_rejects_postgres_role(
    db_session: AsyncSession, user: User, person: Person, org: Org,
) -> None:
    db_session.add(UserPersonObservation(
        user_id=user.id, person_id=person.id, email_count=10,
    ))
    db_session.add(EmploymentClaim(
        person_id=person.id,
        org_id=org.id,
        role_title="postgres",
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
    assert updated.current_role is None


async def test_recompute_preserves_phone_numbers_from_aliases(
    db_session: AsyncSession, user: User,
) -> None:
    person = Person(
        canonical_name="Jane Doe",
        primary_email="jane@example.com",
        phone_numbers=["+15550100"],
    )
    db_session.add(person)
    await db_session.flush()
    db_session.add(UserPersonObservation(
        user_id=user.id, person_id=person.id, email_count=1,
    ))
    db_session.add(PersonAlias(
        person_id=person.id,
        kind="phone",
        value="+15550101",
    ))
    await db_session.flush()

    recompute = PersonProfileRecompute(db_session)
    await recompute.recompute_for_user(user.id)

    result = await db_session.execute(select(Person).where(Person.id == person.id))
    updated: Person = result.scalar_one()
    assert updated.phone_numbers == ["+15550100", "+15550101"]


async def test_recompute_strips_quoted_name(
    db_session: AsyncSession, user: User,
) -> None:
    p = Person(canonical_name="'Kelli Stockdale'", primary_email="kelli@test.com")
    db_session.add(p)
    await db_session.flush()
    db_session.add(UserPersonObservation(
        user_id=user.id, person_id=p.id, email_count=1,
    ))
    await db_session.flush()

    recompute = PersonProfileRecompute(db_session)
    await recompute.recompute_for_user(user.id)

    result = await db_session.execute(select(Person).where(Person.id == p.id))
    updated: Person = result.scalar_one()
    assert updated.canonical_name == "Kelli Stockdale"
