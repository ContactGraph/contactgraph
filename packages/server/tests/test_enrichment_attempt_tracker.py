"""Tests for EnrichmentAttemptTracker — freshness gating for web enrichment."""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from contactsafe_server.db.models import Base, EnrichmentAttempt, Person
from contactsafe_server.services.enrichment_attempt_tracker import EnrichmentAttemptTracker

@pytest.fixture(autouse=True)
async def _setup_tables(db_engine):
    async with db_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


@pytest.fixture
async def person(db_session: AsyncSession) -> Person:
    p = Person(canonical_name="Tracker Test", primary_email="tracker@test.com")
    db_session.add(p)
    await db_session.flush()
    return p


async def test_first_time_should_attempt(db_session: AsyncSession, person: Person) -> None:
    tracker = EnrichmentAttemptTracker(db_session, ttl_days=30)
    assert await tracker.should_attempt(person_id=person.id, source_kind="exa") is True


async def test_fresh_attempt_should_skip(db_session: AsyncSession, person: Person) -> None:
    tracker = EnrichmentAttemptTracker(db_session, ttl_days=30)
    await tracker.record_attempt(
        person_id=person.id, source_kind="exa", succeeded=True, result_count=3,
    )
    assert await tracker.should_attempt(person_id=person.id, source_kind="exa") is False


async def test_stale_attempt_should_reattempt(db_session: AsyncSession, person: Person) -> None:
    tracker = EnrichmentAttemptTracker(db_session, ttl_days=30)
    await tracker.record_attempt(
        person_id=person.id, source_kind="exa", succeeded=True, result_count=3,
    )

    stale_time: datetime = datetime.now(timezone.utc) - timedelta(days=31)
    await db_session.execute(
        update(EnrichmentAttempt)
        .where(
            EnrichmentAttempt.person_id == person.id,
            EnrichmentAttempt.source_kind == "exa",
        )
        .values(last_attempted_at=stale_time)
    )

    assert await tracker.should_attempt(person_id=person.id, source_kind="exa") is True


async def test_failed_within_ttl_still_skipped(db_session: AsyncSession, person: Person) -> None:
    tracker = EnrichmentAttemptTracker(db_session, ttl_days=30)
    await tracker.record_attempt(
        person_id=person.id, source_kind="exa", succeeded=False, error="timeout",
    )
    assert await tracker.should_attempt(person_id=person.id, source_kind="exa") is False


async def test_different_source_kinds_independent(db_session: AsyncSession, person: Person) -> None:
    tracker = EnrichmentAttemptTracker(db_session, ttl_days=30)
    await tracker.record_attempt(
        person_id=person.id, source_kind="exa", succeeded=True,
    )
    assert await tracker.should_attempt(person_id=person.id, source_kind="exa") is False
    assert await tracker.should_attempt(person_id=person.id, source_kind="tavily") is True
