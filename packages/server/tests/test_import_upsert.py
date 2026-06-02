"""Tests for import_service upsert logic against entity-claim schema."""

import uuid
from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from contactsafe_core.enums import SourceConnectionStatus, SourceType, SyncState
from contactsafe_server.config import get_settings
from contactsafe_server.db.models import (
    Base,
    Person,
    PersonAlias,
    Source,
    User,
    UserPersonObservation,
)
from contactsafe_server.services.crypto import TokenEncryptor
from contactsafe_server.services.email_parse import ContactAccumulator
from contactsafe_server.services.entity_resolution import EntityResolver
from contactsafe_server.services.import_service import ImportService

@pytest.fixture(autouse=True)
async def _setup_tables(db_engine):
    async with db_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def test_upsert_creates_person_and_observation(
    db_session: AsyncSession,
) -> None:
    user = User(email=f"upsert-{uuid.uuid4()}@example.com")
    db_session.add(user)
    await db_session.flush()

    source = Source(
        user_id=user.id,
        source_type=SourceType.GOOGLE_MAIL.value,
        label=user.email,
        external_account_id=user.email,
        connection_status=SourceConnectionStatus.CONNECTED.value,
        sync_state=SyncState.PENDING.value,
    )
    db_session.add(source)
    await db_session.flush()

    settings = get_settings()
    service = ImportService(
        db=db_session,
        settings=settings,
        encryptor=TokenEncryptor(settings.token_encryption_key),
        gmail=MagicMock(),
    )
    accumulator = ContactAccumulator(
        email="friend@example.com",
        display_name="Fresh Name",
        last_seen_at=datetime(2025, 6, 1, tzinfo=UTC),
    )
    accumulator.message_count = 4
    accumulator.outbound_count = 2
    accumulator.inbound_count = 2

    resolver = EntityResolver(db_session)
    await service._upsert_person(
        user.id,
        user.email,
        accumulator,
        source_id=source.id,
        resolver=resolver,
    )
    await db_session.flush()

    result = await db_session.execute(
        select(PersonAlias).where(PersonAlias.kind == "email", PersonAlias.value == "friend@example.com")
    )
    alias: PersonAlias | None = result.scalar_one_or_none()
    assert alias is not None

    obs_result = await db_session.execute(
        select(UserPersonObservation).where(
            UserPersonObservation.user_id == user.id,
            UserPersonObservation.person_id == alias.person_id,
        )
    )
    obs: UserPersonObservation | None = obs_result.scalar_one_or_none()
    assert obs is not None
    assert obs.email_count == 4


async def test_upsert_reuses_existing_person_by_email(
    db_session: AsyncSession,
) -> None:
    user = User(email=f"reuse-{uuid.uuid4()}@example.com")
    db_session.add(user)
    await db_session.flush()

    source = Source(
        user_id=user.id,
        source_type=SourceType.GOOGLE_MAIL.value,
        label=user.email,
        external_account_id=user.email,
        connection_status=SourceConnectionStatus.CONNECTED.value,
        sync_state=SyncState.PENDING.value,
    )
    db_session.add(source)
    await db_session.flush()

    settings = get_settings()
    service = ImportService(
        db=db_session,
        settings=settings,
        encryptor=TokenEncryptor(settings.token_encryption_key),
        gmail=MagicMock(),
    )
    resolver = EntityResolver(db_session)

    acc1 = ContactAccumulator(
        email="friend@example.com",
        display_name="Name V1",
        last_seen_at=datetime(2025, 1, 1, tzinfo=UTC),
    )
    acc1.message_count = 2
    await service._upsert_person(user.id, user.email, acc1, source_id=source.id, resolver=resolver)
    await db_session.flush()

    acc2 = ContactAccumulator(
        email="friend@example.com",
        display_name="Name V2",
        last_seen_at=datetime(2025, 6, 1, tzinfo=UTC),
    )
    acc2.message_count = 5
    await service._upsert_person(user.id, user.email, acc2, source_id=source.id, resolver=resolver)
    await db_session.flush()

    result = await db_session.execute(select(func.count()).select_from(Person))
    assert result.scalar() == 1
