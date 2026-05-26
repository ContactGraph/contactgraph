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


async def test_type_keywords_matches_descriptive_tags(db_session: AsyncSession) -> None:
    """type_keywords should match against Person.descriptive_tags via array overlap."""
    user = User(email=f"typekw-{uuid.uuid4()}@example.com")
    db_session.add(user)
    await db_session.flush()

    teacher = Person(
        canonical_name="Sara Educator",
        primary_email="sara@school.edu",
        descriptive_tags=["teacher", "educator", "academic"],
        inferred_categories=[],
    )
    engineer = Person(
        canonical_name="Dan Dev",
        primary_email="dan@techco.io",
        descriptive_tags=["engineer", "devops"],
        inferred_categories=["engineer"],
    )
    db_session.add_all([teacher, engineer])
    await db_session.flush()

    db_session.add_all([
        UserPersonObservation(
            user_id=user.id, person_id=teacher.id,
            tie_strength_score=0.6, is_broadcast=False, is_automated=False, email_count=10,
        ),
        UserPersonObservation(
            user_id=user.id, person_id=engineer.id,
            tie_strength_score=0.9, is_broadcast=False, is_automated=False, email_count=50,
        ),
    ])
    await db_session.flush()

    matches = await NetworkQueryService(db_session).execute(
        user_id=user.id,
        plan=QueryPlan(type_keywords=["teacher", "professor", "educator"], limit=10),
    )
    assert len(matches) == 1
    assert matches[0].name == "Sara Educator"
    assert "teacher" in matches[0].descriptive_tags


async def test_type_keywords_matches_role_freetext(db_session: AsyncSession) -> None:
    """type_keywords should also match freetext in current_role."""
    user = User(email=f"rolekw-{uuid.uuid4()}@example.com")
    db_session.add(user)
    await db_session.flush()

    artist = Person(
        canonical_name="Kim Painter",
        primary_email="kim@gallery.art",
        current_role="Visual Artist & Illustrator",
        descriptive_tags=[],
        inferred_categories=[],
    )
    db_session.add(artist)
    await db_session.flush()

    db_session.add(UserPersonObservation(
        user_id=user.id, person_id=artist.id,
        tie_strength_score=0.5, is_broadcast=False, is_automated=False, email_count=5,
    ))
    await db_session.flush()

    matches = await NetworkQueryService(db_session).execute(
        user_id=user.id,
        plan=QueryPlan(type_keywords=["artist", "painter", "illustrator"], limit=10),
    )
    assert len(matches) == 1
    assert matches[0].name == "Kim Painter"


async def test_type_keywords_no_fallback_to_unfiltered(db_session: AsyncSession) -> None:
    """When no one matches type_keywords, return empty."""
    user = User(email=f"notype-{uuid.uuid4()}@example.com")
    db_session.add(user)
    await db_session.flush()

    person = Person(
        canonical_name="Random Contact",
        primary_email="random@gmail.com",
        descriptive_tags=[],
        inferred_categories=[],
    )
    db_session.add(person)
    await db_session.flush()

    db_session.add(UserPersonObservation(
        user_id=user.id, person_id=person.id,
        tie_strength_score=0.99, is_broadcast=False, is_automated=False, email_count=200,
    ))
    await db_session.flush()

    matches = await NetworkQueryService(db_session).execute(
        user_id=user.id,
        plan=QueryPlan(type_keywords=["journalist", "reporter", "media"], limit=25),
    )
    assert matches == []


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


async def test_category_filter_no_fallback_to_unfiltered(db_session: AsyncSession) -> None:
    """When no one matches the category, return empty — never fall back to top-N by tie strength."""
    user = User(email=f"nofallback-{uuid.uuid4()}@example.com")
    db_session.add(user)
    await db_session.flush()

    engineer = Person(
        canonical_name="Alice Builder",
        primary_email="alice@startup.io",
        inferred_categories=["engineer"],
    )
    family = Person(
        canonical_name="Mom",
        primary_email="mom@gmail.com",
        inferred_categories=[],
    )
    db_session.add_all([engineer, family])
    await db_session.flush()

    db_session.add_all([
        UserPersonObservation(
            user_id=user.id, person_id=engineer.id,
            tie_strength_score=0.9, is_broadcast=False, is_automated=False, email_count=50,
        ),
        UserPersonObservation(
            user_id=user.id, person_id=family.id,
            tie_strength_score=0.99, is_broadcast=False, is_automated=False, email_count=200,
        ),
    ])
    await db_session.flush()

    matches = await NetworkQueryService(db_session).execute(
        user_id=user.id,
        plan=QueryPlan(categories_any=["vc"], limit=25),
    )
    assert matches == []


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
        allow_unfiltered=True,
    )
    assert len(matches) == 1
    assert matches[0].name == "Real Person"
