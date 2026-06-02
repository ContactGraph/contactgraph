"""Tests for GraphSummaryService against entity-claim schema."""

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from contactsafe_server.db.models import (
    Base,
    Person,
    User,
    UserPersonObservation,
)
from contactsafe_server.services.graph_summary_service import GraphSummaryService

@pytest.fixture(autouse=True)
async def _setup_tables(db_engine):
    async with db_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def test_describe_graph_summarizes_queryable_contacts(db_session: AsyncSession) -> None:
    user = User(email=f"summary-{uuid.uuid4()}@example.com")
    db_session.add(user)
    await db_session.flush()

    human_vc = Person(
        canonical_name="Jane Investor",
        primary_email="jane@vcfund.com",
        current_org_name="VC Fund",
        inferred_categories=["vc"],
    )
    human_founder = Person(
        canonical_name="Chris Founder",
        primary_email="chris@startup.com",
        current_org_name="Startup Inc",
        inferred_categories=["founder"],
    )
    newsletter = Person(
        canonical_name="Newsletter",
        primary_email="news@marketing.io",
    )
    bot = Person(
        canonical_name="GitHub Bot",
        primary_email="ci@noreply.github.com",
    )
    db_session.add_all([human_vc, human_founder, newsletter, bot])
    await db_session.flush()

    db_session.add_all([
        UserPersonObservation(
            user_id=user.id, person_id=human_vc.id, tie_strength_score=0.95,
            is_human=True, is_broadcast=False, is_automated=False, email_count=20,
            last_observed_at=datetime.now(tz=UTC),
        ),
        UserPersonObservation(
            user_id=user.id, person_id=human_founder.id, tie_strength_score=0.7,
            is_human=True, is_broadcast=False, is_automated=False, email_count=15,
            last_observed_at=datetime.now(tz=UTC),
        ),
        UserPersonObservation(
            user_id=user.id, person_id=newsletter.id, tie_strength_score=0.8,
            is_human=False, is_broadcast=True, is_automated=False, email_count=50,
        ),
        UserPersonObservation(
            user_id=user.id, person_id=bot.id, tie_strength_score=0.99,
            is_human=False, is_broadcast=False, is_automated=True, email_count=100,
        ),
    ])
    await db_session.flush()

    summary = await GraphSummaryService(db_session).describe(user.id)

    assert summary.total_contacts == 4
    assert summary.human_contacts == 2
    assert summary.broadcast_contacts == 1
    assert summary.automated_contacts == 1
    assert summary.queryable_contacts == 2
    assert {item.category for item in summary.top_categories} == {"vc", "founder"}
    assert {item.org_name for item in summary.top_orgs} == {"VC Fund", "Startup Inc"}
    assert len(summary.strongest_ties) == 2
    assert summary.strongest_ties[0].name == "Jane Investor"
    assert "2 are queryable" in summary.message
