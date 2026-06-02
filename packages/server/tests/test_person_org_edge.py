"""Tests for employment claims (replaces old PersonOrgEdge tests)."""

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from contactsafe_server.db.models import (
    Base,
    EmploymentClaim,
    Org,
    Person,
    User,
    UserPersonObservation,
)
from contactsafe_server.services.claim_writer import record_employment
from contactsafe_server.services.person_profile_recompute import PersonProfileRecompute

@pytest.fixture(autouse=True)
async def _setup_tables(db_engine):
    async with db_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def test_employment_claim_recomputes_person_denorm(
    db_session: AsyncSession,
) -> None:
    user = User(email=f"emp-{uuid.uuid4()}@example.com")
    db_session.add(user)
    await db_session.flush()

    org = Org(canonical_name="Northlight", primary_domain="northlight.io")
    person = Person(canonical_name="Priya Ramaswamy", primary_email="priya@northlight.io")
    db_session.add_all([org, person])
    await db_session.flush()

    db_session.add(UserPersonObservation(
        user_id=user.id, person_id=person.id,
        tie_strength_score=0.5, is_human=True, email_count=5,
    ))
    await db_session.flush()

    await record_employment(
        db_session,
        person_id=person.id,
        org_id=org.id,
        role_title="Founder",
        contributor_user_id=user.id,
        contributor_source_kind="gmail_domain",
    )

    recompute = PersonProfileRecompute(db_session)
    await recompute.recompute_for_user(user.id)

    await db_session.refresh(person)
    assert person.current_org_id == org.id
    assert person.current_org_name == "Northlight"
    assert person.current_role == "Founder"
