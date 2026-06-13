"""Tests for job digest email notifications."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from contactsafe_core.enums import JobDigestFrequency
from contactsafe_server.config import Settings
from contactsafe_server.db.models import Org, OrgJob, User, UserJobRelevance
from contactsafe_server.services.email_service import EmailService
from contactsafe_server.services.job_digest_service import (
    JobDigestService,
    digest_watermark,
    is_user_due_for_digest,
)
from contactsafe_server.services.jwt_service import JWTService


@pytest.fixture(scope="module")
async def postgres_digest_schema_ready(db_engine: AsyncEngine) -> None:
    async with db_engine.connect() as conn:
        result = await conn.execute(
            text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema = 'public' AND table_name = 'users' "
                "AND column_name = 'job_digest_frequency'",
            ),
        )
        if result.scalar() is None:
            pytest.skip("public.users is missing digest columns; run migrations.")


@pytest.fixture
def digest_settings() -> Settings:
    return Settings(
        token_encryption_key="test-encryption-key",
        session_secret="test-session-secret",
        google_client_id="test-client",
        google_client_secret="test-secret",
        jwt_signing_key="jwt-test-signing-key",
        base_url="http://testserver",
        web_base_url="http://testweb",
        email_digest_min_match_score=60,
        email_digest_max_jobs=20,
        email_digest_send_hour_utc=15,
    )


@pytest.fixture
def jwt_service(digest_settings: Settings) -> JWTService:
    return JWTService(digest_settings)


@pytest.fixture
def monitored_user() -> User:
    return User(
        email="seeker@example.com",
        job_monitor_enabled=True,
        job_digest_frequency=JobDigestFrequency.DAILY,
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )


@pytest.fixture
async def db_monitored_user(db_session: AsyncSession) -> User:
    user = User(
        email="seeker@example.com",
        job_monitor_enabled=True,
        job_digest_frequency=JobDigestFrequency.DAILY,
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    db_session.add(user)
    await db_session.flush()
    return user


def test_digest_watermark_uses_last_sent_at(monitored_user: User) -> None:
    sent_at = datetime(2026, 6, 1, tzinfo=UTC)
    monitored_user.job_digest_last_sent_at = sent_at
    assert digest_watermark(monitored_user) == sent_at


def test_digest_watermark_falls_back_to_created_at(monitored_user: User) -> None:
    assert digest_watermark(monitored_user) == monitored_user.created_at


def test_is_user_due_daily_at_send_hour(monitored_user: User) -> None:
    now = datetime(2026, 6, 12, 15, 30, tzinfo=UTC)
    monitored_user.job_digest_last_sent_at = now - timedelta(days=2)
    assert is_user_due_for_digest(
        monitored_user,
        now=now,
        send_hour_utc=15,
    )


def test_is_user_due_rejects_wrong_hour(monitored_user: User) -> None:
    now = datetime(2026, 6, 12, 10, 30, tzinfo=UTC)
    monitored_user.job_digest_last_sent_at = now - timedelta(days=2)
    assert not is_user_due_for_digest(
        monitored_user,
        now=now,
        send_hour_utc=15,
    )


def test_is_user_due_rejects_recent_daily_send(monitored_user: User) -> None:
    now = datetime(2026, 6, 12, 15, 30, tzinfo=UTC)
    monitored_user.job_digest_last_sent_at = now - timedelta(hours=12)
    assert not is_user_due_for_digest(
        monitored_user,
        now=now,
        send_hour_utc=15,
    )


def test_is_user_due_weekly_requires_seven_days(monitored_user: User) -> None:
    now = datetime(2026, 6, 12, 15, 30, tzinfo=UTC)
    monitored_user.job_digest_frequency = JobDigestFrequency.WEEKLY
    monitored_user.job_digest_last_sent_at = now - timedelta(days=3)
    assert not is_user_due_for_digest(
        monitored_user,
        now=now,
        send_hour_utc=15,
    )
    monitored_user.job_digest_last_sent_at = now - timedelta(days=8)
    assert is_user_due_for_digest(
        monitored_user,
        now=now,
        send_hour_utc=15,
    )


def test_is_user_due_rejects_off_and_unmonitored(monitored_user: User) -> None:
    now = datetime(2026, 6, 12, 15, 30, tzinfo=UTC)
    monitored_user.job_digest_frequency = JobDigestFrequency.OFF
    assert not is_user_due_for_digest(
        monitored_user,
        now=now,
        send_hour_utc=15,
    )
    monitored_user.job_digest_frequency = JobDigestFrequency.DAILY
    monitored_user.job_monitor_enabled = False
    assert not is_user_due_for_digest(
        monitored_user,
        now=now,
        send_hour_utc=15,
    )


async def _seed_relevant_job(
    db_session: AsyncSession,
    *,
    user: User,
    title: str,
    match_score: int,
    classified_at: datetime,
    company_name: str = "Acme Corp",
) -> OrgJob:
    org = Org(canonical_name=company_name)
    db_session.add(org)
    await db_session.flush()

    job = OrgJob(
        org_id=org.id,
        external_job_id=f"ext-{uuid.uuid4()}",
        source="greenhouse",
        title=title,
        location="Remote",
        url=f"https://jobs.example.com/{uuid.uuid4()}",
        is_active=True,
    )
    db_session.add(job)
    await db_session.flush()

    relevance = UserJobRelevance(
        user_id=user.id,
        job_id=job.id,
        is_relevant=True,
        match_score=match_score,
        classified_at=classified_at,
    )
    db_session.add(relevance)
    await db_session.flush()
    return job


async def test_build_digest_returns_only_new_matches_above_threshold(
    postgres_digest_schema_ready: None,
    db_session: AsyncSession,
    db_monitored_user: User,
    digest_settings: Settings,
) -> None:
    watermark = datetime(2026, 6, 1, tzinfo=UTC)
    db_monitored_user.job_digest_last_sent_at = watermark
    await db_session.flush()

    await _seed_relevant_job(
        db_session,
        user=db_monitored_user,
        title="Old Match",
        match_score=80,
        classified_at=datetime(2026, 5, 31, tzinfo=UTC),
    )
    await _seed_relevant_job(
        db_session,
        user=db_monitored_user,
        title="Low Score",
        match_score=40,
        classified_at=datetime(2026, 6, 2, tzinfo=UTC),
    )
    new_job = await _seed_relevant_job(
        db_session,
        user=db_monitored_user,
        title="New Match",
        match_score=85,
        classified_at=datetime(2026, 6, 2, tzinfo=UTC),
        company_name="Stripe",
    )

    service = JobDigestService(db_session, digest_settings)
    digest = await service.build_digest(db_monitored_user.id)
    assert digest is not None
    assert digest.total_new_matches == 1
    assert len(digest.jobs) == 1
    assert digest.jobs[0].job_id == new_job.id
    assert digest.jobs[0].company_name == "Stripe"


async def test_build_digest_returns_empty_when_no_new_matches(
    postgres_digest_schema_ready: None,
    db_session: AsyncSession,
    db_monitored_user: User,
    digest_settings: Settings,
) -> None:
    db_monitored_user.job_digest_last_sent_at = datetime(2026, 6, 10, tzinfo=UTC)
    await db_session.flush()

    service = JobDigestService(db_session, digest_settings)
    digest = await service.build_digest(db_monitored_user.id)
    assert digest is not None
    assert digest.total_new_matches == 0
    assert digest.jobs == ()


async def test_send_digest_skips_without_resend_key(
    postgres_digest_schema_ready: None,
    db_session: AsyncSession,
    db_monitored_user: User,
    digest_settings: Settings,
    jwt_service: JWTService,
) -> None:
    db_monitored_user.job_digest_last_sent_at = datetime(2026, 6, 1, tzinfo=UTC)
    await db_session.flush()
    await _seed_relevant_job(
        db_session,
        user=db_monitored_user,
        title="Backend Engineer",
        match_score=90,
        classified_at=datetime(2026, 6, 2, tzinfo=UTC),
    )

    service = JobDigestService(
        db_session,
        digest_settings,
        jwt_service=jwt_service,
    )
    result = await service.send_digest_for_user(db_monitored_user.id)
    assert not result.sent
    assert result.job_count == 1
    assert db_monitored_user.job_digest_last_sent_at == datetime(2026, 6, 1, tzinfo=UTC)


async def test_unsubscribe_user_sets_frequency_off(
    postgres_digest_schema_ready: None,
    db_session: AsyncSession,
    db_monitored_user: User,
    digest_settings: Settings,
) -> None:
    service = JobDigestService(db_session, digest_settings)
    updated = await service.unsubscribe_user(db_monitored_user.id)
    assert updated
    await db_session.refresh(db_monitored_user)
    assert db_monitored_user.job_digest_frequency == JobDigestFrequency.OFF


def test_email_service_noop_without_api_key(digest_settings: Settings) -> None:
    service = EmailService(digest_settings)
    assert not service.is_configured
