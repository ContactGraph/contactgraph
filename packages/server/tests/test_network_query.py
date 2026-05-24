import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from contactsafe_core.query_plan import QueryPlan
from contactsafe_server.db.models import Person, PersonEdge, User
from contactsafe_server.services.network_query_service import NetworkQueryService


@pytest.mark.asyncio
async def test_executor_filters_name_and_excludes_broadcast(
    db_session: AsyncSession,
) -> None:
    user = User(email=f"query-{uuid.uuid4()}@example.com")
    db_session.add(user)
    await db_session.flush()

    human = Person(
        user_id=user.id,
        canonical_name="Chris Pappas",
        email_addresses=["chris@aix.com"],
        current_org_name="AIX",
        inferred_categories=["founder"],
        last_seen_in_email=datetime.now(tz=UTC),
    )
    newsletter = Person(
        user_id=user.id,
        canonical_name="Chris Newsletter",
        email_addresses=["newsletter@marketing.io"],
        last_seen_in_email=datetime.now(tz=UTC),
    )
    bot = Person(
        user_id=user.id,
        canonical_name="GitHub Bot",
        email_addresses=["ci_activity@noreply.github.com"],
        last_seen_in_email=datetime.now(tz=UTC),
    )
    db_session.add_all([human, newsletter, bot])
    await db_session.flush()

    db_session.add_all(
        [
            PersonEdge(
                user_id=user.id,
                person_id=human.id,
                tie_strength_score=0.9,
                is_human=True,
                is_broadcast=False,
                is_automated=False,
                outbound_count=5,
                inbound_count=5,
            ),
            PersonEdge(
                user_id=user.id,
                person_id=newsletter.id,
                tie_strength_score=0.8,
                is_human=False,
                is_broadcast=True,
                is_automated=False,
                outbound_count=0,
                inbound_count=20,
            ),
            PersonEdge(
                user_id=user.id,
                person_id=bot.id,
                tie_strength_score=0.95,
                is_human=False,
                is_broadcast=False,
                is_automated=True,
                outbound_count=50,
                inbound_count=0,
            ),
        ]
    )
    await db_session.flush()

    executor = NetworkQueryService(db_session)
    plan = QueryPlan(name_tokens=["chris"], org_names=["aix"], exclude_broadcast=True, limit=10)
    matches = await executor.execute(user_id=user.id, plan=plan)

    assert len(matches) == 1
    assert matches[0].name == "Chris Pappas"
    assert "chris" in matches[0].match_reason.lower()


@pytest.mark.asyncio
async def test_executor_category_filter(db_session: AsyncSession) -> None:
    user = User(email=f"vc-{uuid.uuid4()}@example.com")
    db_session.add(user)
    await db_session.flush()

    vc_person = Person(
        user_id=user.id,
        canonical_name="Jane Investor",
        email_addresses=["jane@vcfund.com"],
        inferred_categories=["vc"],
    )
    other = Person(
        user_id=user.id,
        canonical_name="Bob Engineer",
        email_addresses=["bob@startup.com"],
        inferred_categories=["engineer"],
    )
    db_session.add_all([vc_person, other])
    await db_session.flush()
    db_session.add_all(
        [
            PersonEdge(
                user_id=user.id,
                person_id=vc_person.id,
                tie_strength_score=0.7,
                is_broadcast=False,
            ),
            PersonEdge(
                user_id=user.id,
                person_id=other.id,
                tie_strength_score=0.6,
                is_broadcast=False,
            ),
        ]
    )
    await db_session.flush()

    matches = await NetworkQueryService(db_session).execute(
        user_id=user.id,
        plan=QueryPlan(categories_any=["vc"], limit=10),
    )
    assert len(matches) == 1
    assert matches[0].name == "Jane Investor"


@pytest.mark.asyncio
async def test_executor_category_filter_aliases_investor_to_vc(
    db_session: AsyncSession,
) -> None:
    user = User(email=f"investor-{uuid.uuid4()}@example.com")
    db_session.add(user)
    await db_session.flush()

    vc_person = Person(
        user_id=user.id,
        canonical_name="Jane Investor",
        email_addresses=["jane@vcfund.com"],
        inferred_categories=["vc"],
    )
    db_session.add(vc_person)
    await db_session.flush()
    db_session.add(
        PersonEdge(
            user_id=user.id,
            person_id=vc_person.id,
            tie_strength_score=0.7,
            is_broadcast=False,
            is_automated=False,
        )
    )
    await db_session.flush()

    matches = await NetworkQueryService(db_session).execute(
        user_id=user.id,
        plan=QueryPlan(categories_any=["investor"], limit=10),
    )
    assert len(matches) == 1
    assert matches[0].name == "Jane Investor"


@pytest.mark.asyncio
async def test_executor_org_matches_email_domain(db_session: AsyncSession) -> None:
    user = User(email=f"sticker-{uuid.uuid4()}@example.com")
    db_session.add(user)
    await db_session.flush()

    danny = Person(
        user_id=user.id,
        canonical_name="Danny Investor",
        email_addresses=["danny@sticker.vc"],
        current_org_name="Sticker",
        inferred_categories=["vc"],
    )
    db_session.add(danny)
    await db_session.flush()
    db_session.add(
        PersonEdge(
            user_id=user.id,
            person_id=danny.id,
            tie_strength_score=0.85,
            is_broadcast=False,
            outbound_count=2,
            inbound_count=3,
            is_human=True,
        )
    )
    await db_session.flush()

    matches = await NetworkQueryService(db_session).execute(
        user_id=user.id,
        plan=QueryPlan(org_names=["Sticker VC"], limit=10),
    )
    assert len(matches) == 1
    assert matches[0].emails == ["danny@sticker.vc"]


@pytest.mark.asyncio
async def test_executor_excludes_automated_by_default(
    db_session: AsyncSession,
) -> None:
    user = User(email=f"auto-{uuid.uuid4()}@example.com")
    db_session.add(user)
    await db_session.flush()

    human = Person(
        user_id=user.id,
        canonical_name="Real Person",
        email_addresses=["real@company.com"],
    )
    bot = Person(
        user_id=user.id,
        canonical_name="GitHub Bot",
        email_addresses=["push@noreply.github.com"],
    )
    db_session.add_all([human, bot])
    await db_session.flush()
    db_session.add_all(
        [
            PersonEdge(
                user_id=user.id,
                person_id=human.id,
                tie_strength_score=0.2,
                is_human=True,
                is_automated=False,
                is_broadcast=False,
            ),
            PersonEdge(
                user_id=user.id,
                person_id=bot.id,
                tie_strength_score=0.99,
                is_automated=True,
                is_broadcast=False,
            ),
        ]
    )
    await db_session.flush()

    matches = await NetworkQueryService(db_session).execute(
        user_id=user.id,
        plan=QueryPlan(limit=10),
    )
    assert len(matches) == 1
    assert matches[0].name == "Real Person"
