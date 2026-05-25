"""Tests for NetworkQueryService against the entity-claim graph."""

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from contactsafe_core.query_plan import QueryPlan
from contactsafe_server.db.models import (
    Base,
    Person,
    PersonAlias,
    User,
    UserPersonObservation,
)
from contactsafe_server.services.network_query_service import NetworkQueryService

pytestmark = pytest.mark.anyio


@pytest.fixture(autouse=True)
async def _setup_tables(db_engine):
    async with db_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def test_filters_name_and_excludes_broadcast(db_session: AsyncSession) -> None:
    user = User(email=f"query-{uuid.uuid4()}@example.com")
    db_session.add(user)
    await db_session.flush()

    human = Person(
        canonical_name="Amara Okafor",
        primary_email="amara@novaworks.com",
        current_org_name="Novaworks",
        inferred_categories=["founder"],
    )
    newsletter = Person(
        canonical_name="Chris Newsletter",
        primary_email="newsletter@marketing.io",
    )
    bot = Person(
        canonical_name="GitHub Bot",
        primary_email="ci_activity@noreply.github.com",
    )
    db_session.add_all([human, newsletter, bot])
    await db_session.flush()

    for alias_person, email in [(human, "amara@novaworks.com"), (newsletter, "newsletter@marketing.io"), (bot, "ci_activity@noreply.github.com")]:
        db_session.add(PersonAlias(person_id=alias_person.id, kind="email", value=email))

    db_session.add_all([
        UserPersonObservation(
            user_id=user.id, person_id=human.id, tie_strength_score=0.9,
            is_human=True, is_broadcast=False, is_automated=False, email_count=10,
        ),
        UserPersonObservation(
            user_id=user.id, person_id=newsletter.id, tie_strength_score=0.8,
            is_human=False, is_broadcast=True, is_automated=False, email_count=20,
        ),
        UserPersonObservation(
            user_id=user.id, person_id=bot.id, tie_strength_score=0.95,
            is_human=False, is_broadcast=False, is_automated=True, email_count=50,
        ),
    ])
    await db_session.flush()

    executor = NetworkQueryService(db_session)
    plan = QueryPlan(name_tokens=["amara"], org_names=["novaworks"], exclude_broadcast=True, limit=10)
    matches = await executor.execute(user_id=user.id, plan=plan)

    assert len(matches) == 1
    assert matches[0].name == "Amara Okafor"


async def test_category_filter(db_session: AsyncSession) -> None:
    user = User(email=f"vc-{uuid.uuid4()}@example.com")
    db_session.add(user)
    await db_session.flush()

    vc_person = Person(
        canonical_name="Jane Investor",
        primary_email="jane@vcfund.com",
        inferred_categories=["vc"],
    )
    other = Person(
        canonical_name="Bob Engineer",
        primary_email="bob@startup.com",
        inferred_categories=["engineer"],
    )
    db_session.add_all([vc_person, other])
    await db_session.flush()

    db_session.add_all([
        UserPersonObservation(
            user_id=user.id, person_id=vc_person.id,
            tie_strength_score=0.7, is_broadcast=False, email_count=5,
        ),
        UserPersonObservation(
            user_id=user.id, person_id=other.id,
            tie_strength_score=0.6, is_broadcast=False, email_count=3,
        ),
    ])
    await db_session.flush()

    matches = await NetworkQueryService(db_session).execute(
        user_id=user.id,
        plan=QueryPlan(categories_any=["vc"], limit=10),
    )
    assert len(matches) == 1
    assert matches[0].name == "Jane Investor"


async def test_category_filter_aliases_investor_to_vc(db_session: AsyncSession) -> None:
    user = User(email=f"investor-{uuid.uuid4()}@example.com")
    db_session.add(user)
    await db_session.flush()

    vc_person = Person(
        canonical_name="Jane Investor",
        primary_email="jane@vcfund.com",
        inferred_categories=["vc"],
    )
    db_session.add(vc_person)
    await db_session.flush()

    db_session.add(UserPersonObservation(
        user_id=user.id, person_id=vc_person.id,
        tie_strength_score=0.7, is_broadcast=False, is_automated=False, email_count=5,
    ))
    await db_session.flush()

    matches = await NetworkQueryService(db_session).execute(
        user_id=user.id,
        plan=QueryPlan(categories_any=["investor"], limit=10),
    )
    assert len(matches) == 1
    assert matches[0].name == "Jane Investor"


async def test_also_known_as_in_results(db_session: AsyncSession) -> None:
    user = User(email=f"aka-{uuid.uuid4()}@example.com")
    db_session.add(user)
    await db_session.flush()

    person = Person(
        canonical_name="Marcus Chen",
        primary_email="mchen@gmail.com",
    )
    db_session.add(person)
    await db_session.flush()

    db_session.add_all([
        PersonAlias(person_id=person.id, kind="email", value="mchen@gmail.com"),
        PersonAlias(person_id=person.id, kind="email", value="marcus@horizon.vc"),
        PersonAlias(person_id=person.id, kind="linkedin_url", value="https://linkedin.com/in/mchen"),
    ])
    db_session.add(UserPersonObservation(
        user_id=user.id, person_id=person.id,
        tie_strength_score=0.8, email_count=10,
    ))
    await db_session.flush()

    matches = await NetworkQueryService(db_session).execute(
        user_id=user.id,
        plan=QueryPlan(name_tokens=["marcus"], limit=10),
    )
    assert len(matches) == 1
    assert "mchen@gmail.com" in matches[0].also_known_as
    assert "marcus@horizon.vc" in matches[0].also_known_as
    assert "https://linkedin.com/in/mchen" in matches[0].also_known_as


async def test_excludes_automated_by_default(db_session: AsyncSession) -> None:
    user = User(email=f"auto-{uuid.uuid4()}@example.com")
    db_session.add(user)
    await db_session.flush()

    human = Person(canonical_name="Real Person", primary_email="real@company.com")
    bot = Person(canonical_name="GitHub Bot", primary_email="push@noreply.github.com")
    db_session.add_all([human, bot])
    await db_session.flush()

    db_session.add_all([
        UserPersonObservation(
            user_id=user.id, person_id=human.id,
            tie_strength_score=0.2, is_human=True, is_automated=False, is_broadcast=False, email_count=3,
        ),
        UserPersonObservation(
            user_id=user.id, person_id=bot.id,
            tie_strength_score=0.99, is_automated=True, is_broadcast=False, email_count=100,
        ),
    ])
    await db_session.flush()

    matches = await NetworkQueryService(db_session).execute(
        user_id=user.id,
        plan=QueryPlan(limit=10),
    )
    assert len(matches) == 1
    assert matches[0].name == "Real Person"
