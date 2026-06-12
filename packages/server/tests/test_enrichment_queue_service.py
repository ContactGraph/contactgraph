"""Tests for per-contact enrichment queue."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from contactsafe_core.enums import EnrichmentQueueStatus
from contactsafe_server.config import Settings
from contactsafe_server.db.models import Person, User, UserPersonObservation
from contactsafe_server.services.enrichment_queue_service import EnrichmentQueueService
from contactsafe_server.services.enrichment_strategies.base import (
    compute_enqueue_priority,
    email_domain_is_fresh,
)


@pytest.fixture
def settings(monkeypatch: pytest.MonkeyPatch) -> Settings:
    monkeypatch.setenv("TOKEN_ENCRYPTION_KEY", "test-key-" + "a" * 32)
    monkeypatch.setenv("SESSION_SECRET", "session-secret")
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "test-client-id")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "test-client-secret")
    from contactsafe_server.config import get_settings

    get_settings.cache_clear()
    return get_settings()


@pytest.mark.asyncio
async def test_enqueue_enrichment_is_idempotent(
    db_session: AsyncSession,
    settings: Settings,
) -> None:
    user: User = User(email="queue@example.com")
    person: Person = Person(canonical_name="Pat", primary_email="pat@acme.com")
    db_session.add_all([user, person])
    await db_session.flush()

    obs = UserPersonObservation(
        user_id=user.id,
        person_id=person.id,
        is_human=True,
        tie_strength_score=0.8,
    )
    db_session.add(obs)
    await db_session.flush()

    service = EnrichmentQueueService(db_session, settings)
    first = await service.enqueue_enrichment(
        person_id=person.id,
        trigger_user_id=user.id,
    )
    second = await service.enqueue_enrichment(
        person_id=person.id,
        trigger_user_id=user.id,
        priority=999,
    )

    assert first.id == second.id
    assert second.priority == 999
    assert second.status == EnrichmentQueueStatus.PENDING.value
    assert len(second.strategies_remaining) > 0


@pytest.mark.asyncio
async def test_email_domain_is_fresh_respects_cutoff() -> None:
    user: User = User(email="fresh@example.com")
    person: Person = Person(canonical_name="Pat", primary_email="pat@acme.com")
    obs = UserPersonObservation(
        user_id=uuid.uuid4(),
        person_id=person.id,
        last_observed_at=datetime.now(tz=UTC) - timedelta(days=30),
    )
    stale_obs = UserPersonObservation(
        user_id=uuid.uuid4(),
        person_id=person.id,
        last_observed_at=datetime.now(tz=UTC) - timedelta(days=200),
    )

    assert email_domain_is_fresh(obs, freshness_days=180) is True
    assert email_domain_is_fresh(stale_obs, freshness_days=180) is False
    assert email_domain_is_fresh(None, freshness_days=180) is False


def test_compute_enqueue_priority_boosts_recent_human_contacts() -> None:
    recent_obs = UserPersonObservation(
        user_id=uuid.uuid4(),
        person_id=uuid.uuid4(),
        is_human=True,
        tie_strength_score=0.5,
        last_observed_at=datetime.now(tz=UTC) - timedelta(days=2),
    )
    priority: int = compute_enqueue_priority(recent_obs)
    assert priority >= 600
