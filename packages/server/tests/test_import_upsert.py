import uuid
from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from contactsafe_core.enums import SourceConnectionStatus, SourceType, SyncState
from contactsafe_server.config import get_settings
from contactsafe_server.db.models import Person, PersonEdge, Source, User
from contactsafe_server.services.crypto import TokenEncryptor
from contactsafe_server.services.email_parse import ContactAccumulator
from contactsafe_server.services.import_service import ImportService


@pytest.mark.asyncio
async def test_upsert_person_updates_existing_contact_by_email(
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

    existing = Person(
        user_id=user.id,
        canonical_name="Old Name",
        email_addresses=["friend@example.com"],
        last_seen_in_email=datetime(2024, 1, 1, tzinfo=UTC),
    )
    db_session.add(existing)
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

    await service._upsert_person(
        user.id,
        user.email,
        accumulator,
        source_id=source.id,
    )
    await db_session.flush()

    count_result = await db_session.execute(
        select(func.count())
        .select_from(Person)
        .where(Person.user_id == user.id)
    )
    assert count_result.scalar_one() == 1

    await db_session.refresh(existing)
    assert existing.canonical_name == "Fresh Name"
    assert existing.last_seen_in_email == datetime(2025, 6, 1, tzinfo=UTC)

    edge_result = await db_session.execute(
        select(PersonEdge).where(
            PersonEdge.user_id == user.id,
            PersonEdge.person_id == existing.id,
        )
    )
    edge = edge_result.scalar_one()
    assert edge.email_count == 4
    assert edge.source_id == source.id


@pytest.mark.asyncio
async def test_upsert_person_leaves_unrelated_contacts_untouched(
    db_session: AsyncSession,
) -> None:
    user = User(email=f"other-{uuid.uuid4()}@example.com")
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

    phone_only = Person(
        user_id=user.id,
        canonical_name="WhatsApp Friend",
        email_addresses=[],
        phone_numbers=["+15551234567"],
    )
    db_session.add(phone_only)
    await db_session.flush()

    settings = get_settings()
    service = ImportService(
        db=db_session,
        settings=settings,
        encryptor=TokenEncryptor(settings.token_encryption_key),
        gmail=MagicMock(),
    )
    accumulator = ContactAccumulator(
        email="gmail-friend@example.com",
        display_name="Gmail Friend",
        last_seen_at=datetime(2025, 6, 1, tzinfo=UTC),
    )
    accumulator.message_count = 1

    await service._upsert_person(
        user.id,
        user.email,
        accumulator,
        source_id=source.id,
    )
    await db_session.flush()

    people_result = await db_session.execute(
        select(Person).where(Person.user_id == user.id).order_by(Person.canonical_name)
    )
    people = list(people_result.scalars().all())
    assert len(people) == 2
    assert people[0].canonical_name == "Gmail Friend"
    assert people[1].canonical_name == "WhatsApp Friend"
