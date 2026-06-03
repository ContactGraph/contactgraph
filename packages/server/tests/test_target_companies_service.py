"""Tests for target company queries."""

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from contactsafe_server.db.models import (
    Base,
    EmploymentClaim,
    Org,
    Person,
    RelationshipClaim,
    User,
    UserPersonObservation,
)
from contactsafe_server.services.relationship_trust import FIRST_DEGREE_TRUST_THRESHOLD
from contactsafe_server.services.target_companies_service import (
    TargetCompaniesService,
    _looks_like_email,
    _looks_like_team_account,
    _passes_display_quality,
)


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


async def _add_insider(
    db_session: AsyncSession,
    *,
    user: User,
    user_person: Person,
    org: Org,
    name: str,
    email: str,
    emp_source_kind: str = "gmail_signature",
    emp_confidence: float = 0.8,
) -> Person:
    """Helper: create a Person at *org* with an employment claim and observation."""
    person = Person(
        canonical_name=name,
        primary_email=email,
        current_org_id=org.id,
        current_org_name=org.canonical_name,
    )
    db_session.add(person)
    await db_session.flush()

    db_session.add(EmploymentClaim(
        person_id=person.id,
        org_id=org.id,
        is_current=True,
        contributor_user_id=user.id,
        contributor_source_kind=emp_source_kind,
        confidence=emp_confidence,
    ))
    db_session.add(UserPersonObservation(
        user_id=user.id,
        person_id=person.id,
        tie_strength_score=0.8,
        outbound_count=3,
        relationship_types=["phone_contacts_upload"],
        is_human=True,
    ))
    db_session.add(RelationshipClaim(
        person_a_id=min(user_person.id, person.id),
        person_b_id=max(user_person.id, person.id),
        kind="phone_contact",
        contributor_user_id=user.id,
        contributor_source_kind="phone_contacts_upload",
    ))
    await db_session.flush()
    return person


# ---------------------------------------------------------------------------
# Unit tests for filter helpers
# ---------------------------------------------------------------------------


def test_looks_like_email() -> None:
    assert _looks_like_email("planning.city@usa.com") is True
    assert _looks_like_email("Jane Smith") is False
    assert _looks_like_email("hello@world") is True


def test_looks_like_team_account() -> None:
    assert _looks_like_team_account("GCS Portugal team", "GCS") is True
    assert _looks_like_team_account("GV Funds Team", None) is True
    assert _looks_like_team_account("Tahoe Getaways", "Tahoe Getaways") is True
    assert _looks_like_team_account("Jane Insider", "Acme Corp") is False


def test_passes_display_quality() -> None:
    assert _passes_display_quality("Jane Insider", "Acme") is True
    assert _passes_display_quality("info@acme.com", "Acme") is False
    assert _passes_display_quality("Sales Team", None) is False
    assert _passes_display_quality("Acme Corp", "Acme Corp") is False


# ---------------------------------------------------------------------------
# Integration tests
# ---------------------------------------------------------------------------


async def test_list_first_degree_groups_by_org(
    db_session: AsyncSession,
    user: User,
    user_person: Person,
) -> None:
    org = Org(canonical_name="Acme Corp", primary_domain="acme.com")
    db_session.add(org)
    await db_session.flush()

    await _add_insider(
        db_session,
        user=user,
        user_person=user_person,
        org=org,
        name="Jane Insider",
        email="jane@acme.com",
    )

    service = TargetCompaniesService(db_session)
    matches = await service.list_first_degree(user.id)
    assert len(matches) == 1
    assert matches[0].org_name == "Acme Corp"
    assert matches[0].insiders[0].person_name == "Jane Insider"


async def test_heuristic_only_employment_is_filtered(
    db_session: AsyncSession,
    user: User,
    user_person: Person,
) -> None:
    """Contacts whose only current employment is heuristic-sourced are hidden."""
    org = Org(canonical_name="Pjcgeotech", primary_domain="pjcgeotech.com")
    db_session.add(org)
    await db_session.flush()

    await _add_insider(
        db_session,
        user=user,
        user_person=user_person,
        org=org,
        name="Kelli Stockdale",
        email="kelli@pjcgeotech.com",
        emp_source_kind="heuristic",
        emp_confidence=0.4,
    )

    service = TargetCompaniesService(db_session)
    matches = await service.list_first_degree(user.id)
    assert len(matches) == 0, "Heuristic-only employment should be filtered"


async def test_heuristic_plus_signature_is_kept(
    db_session: AsyncSession,
    user: User,
    user_person: Person,
) -> None:
    """If a person also has a signature-derived claim, they should appear."""
    org = Org(canonical_name="Acme Corp", primary_domain="acme.com")
    db_session.add(org)
    await db_session.flush()

    person = await _add_insider(
        db_session,
        user=user,
        user_person=user_person,
        org=org,
        name="Alice Real",
        email="alice@acme.com",
        emp_source_kind="heuristic",
        emp_confidence=0.4,
    )
    db_session.add(EmploymentClaim(
        person_id=person.id,
        org_id=org.id,
        is_current=True,
        contributor_user_id=user.id,
        contributor_source_kind="gmail_signature",
        confidence=0.8,
    ))
    await db_session.flush()

    service = TargetCompaniesService(db_session)
    matches = await service.list_first_degree(user.id)
    assert len(matches) == 1


async def test_email_as_name_filtered(
    db_session: AsyncSession,
    user: User,
    user_person: Person,
) -> None:
    org = Org(canonical_name="City of Mill Valley", primary_domain="millvalley.ca.gov")
    db_session.add(org)
    await db_session.flush()

    await _add_insider(
        db_session,
        user=user,
        user_person=user_person,
        org=org,
        name="planning.cityofmillvalley.ca@usa.com",
        email="planning.cityofmillvalley.ca@usa.com",
    )

    service = TargetCompaniesService(db_session)
    matches = await service.list_first_degree(user.id)
    assert len(matches) == 0, "Email-as-name should be filtered"


async def test_team_account_filtered(
    db_session: AsyncSession,
    user: User,
    user_person: Person,
) -> None:
    org = Org(canonical_name="GCS", primary_domain="globalcitizensolutions.com")
    db_session.add(org)
    await db_session.flush()

    await _add_insider(
        db_session,
        user=user,
        user_person=user_person,
        org=org,
        name="GCS Portugal team",
        email="team@globalcitizensolutions.com",
    )

    service = TargetCompaniesService(db_session)
    matches = await service.list_first_degree(user.id)
    assert len(matches) == 0, "Team accounts should be filtered"


async def test_google_contact_only_can_appear(
    db_session: AsyncSession,
    user: User,
    user_person: Person,
) -> None:
    """Google Contacts with no outbound email should still surface at first-degree trust."""
    org = Org(canonical_name="EquityBee", primary_domain="equitybee.com")
    db_session.add(org)
    await db_session.flush()

    person = Person(
        canonical_name="Yaeli Gila",
        primary_email="yaeli@equitybee.com",
        current_org_id=org.id,
        current_org_name=org.canonical_name,
    )
    db_session.add(person)
    await db_session.flush()

    db_session.add(EmploymentClaim(
        person_id=person.id,
        org_id=org.id,
        is_current=True,
        contributor_user_id=user.id,
        contributor_source_kind="google_contacts",
        confidence=0.8,
    ))
    db_session.add(UserPersonObservation(
        user_id=user.id,
        person_id=person.id,
        tie_strength_score=0.3,
        outbound_count=0,
        relationship_types=["contact", "google_contact"],
        is_human=True,
    ))
    await db_session.flush()

    service = TargetCompaniesService(db_session)
    matches = await service.list_first_degree(user.id, min_trust=FIRST_DEGREE_TRUST_THRESHOLD)
    assert len(matches) == 1
    assert matches[0].org_name == "EquityBee"
    assert matches[0].insiders[0].person_name == "Yaeli Gila"
