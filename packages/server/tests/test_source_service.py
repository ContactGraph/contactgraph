import json
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from contactsafe_core.enums import (
    OAuthProvider,
    SourceConnectionStatus,
    SourceType,
    SyncState,
)
from contactsafe_server.services.source_service import SourceService
from contactsafe_server.utils import parse_connect_session_id, parse_source_id


def test_parse_connect_session_id_json() -> None:
    session_id = uuid.uuid4()
    raw = json.dumps({"session_id": str(session_id)})
    assert parse_connect_session_id(raw) == session_id


def test_parse_source_id_json() -> None:
    source_id = uuid.uuid4()
    raw = json.dumps({"source_id": str(source_id)})
    assert parse_source_id(raw) == source_id


@pytest.mark.asyncio
async def test_ensure_google_mail_source(db_session: AsyncSession) -> None:
    from contactsafe_server.db.models import User

    user = User(email="test@example.com")
    db_session.add(user)
    await db_session.flush()

    service = SourceService(db_session)
    source = await service.ensure_google_mail_source(user.id, user.email)
    await db_session.commit()

    assert source.source_type == SourceType.GOOGLE_MAIL.value
    assert source.external_account_id == "test@example.com"
    assert source.connection_status == SourceConnectionStatus.CONNECTED.value
    assert source.sync_state == SyncState.PENDING.value

    again = await service.ensure_google_mail_source(user.id, user.email)
    assert again.id == source.id


async def _connected_gmail_source(db_session: AsyncSession) -> tuple:
    from contactsafe_server.db.models import OAuthCredential, Source, User
    from contactsafe_server.services.crypto import TokenEncryptor
    from contactsafe_server.config import get_settings

    user = User(email="sync-test@example.com")
    db_session.add(user)
    await db_session.flush()

    source = Source(
        user_id=user.id,
        source_type=SourceType.GOOGLE_MAIL.value,
        label="Gmail",
        external_account_id=user.email,
        connection_status=SourceConnectionStatus.CONNECTED.value,
        sync_state=SyncState.PENDING.value,
    )
    db_session.add(source)
    await db_session.flush()

    encryptor = TokenEncryptor(get_settings().token_encryption_key)
    cred = OAuthCredential(
        user_id=user.id,
        source_id=source.id,
        provider=OAuthProvider.GOOGLE.value,
        access_token_encrypted=encryptor.encrypt("access"),
        refresh_token_encrypted=encryptor.encrypt("refresh"),
        token_expires_at=datetime.now(tz=UTC) + timedelta(hours=1),
        scopes=["https://www.googleapis.com/auth/gmail.readonly"],
        is_valid=True,
    )
    db_session.add(cred)
    await db_session.flush()
    return user, source


@pytest.mark.asyncio
async def test_request_sync_rejects_when_db_sync_in_progress(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, source = await _connected_gmail_source(db_session)
    source.sync_state = SyncState.SYNCING.value
    await db_session.flush()

    scheduled_calls: list[tuple[uuid.UUID, uuid.UUID]] = []

    def fake_schedule(source_id: uuid.UUID, user_id: uuid.UUID) -> bool:
        scheduled_calls.append((source_id, user_id))
        return True

    monkeypatch.setattr(
        "contactsafe_server.services.source_service.schedule_source_sync",
        fake_schedule,
    )

    service = SourceService(db_session)
    result = await service.request_sync(source.id)

    assert result.scheduled is False
    assert result.sync_state == SyncState.SYNCING
    assert "already running" in result.message.lower()
    assert scheduled_calls == []


@pytest.mark.asyncio
async def test_request_sync_claims_sync_before_scheduling(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user, source = await _connected_gmail_source(db_session)

    scheduled_calls: list[tuple[uuid.UUID, uuid.UUID]] = []

    def fake_schedule(source_id: uuid.UUID, user_id: uuid.UUID) -> bool:
        scheduled_calls.append((source_id, user_id))
        return True

    monkeypatch.setattr(
        "contactsafe_server.services.source_service.schedule_source_sync",
        fake_schedule,
    )

    service = SourceService(db_session)
    result = await service.request_sync(source.id)

    assert result.scheduled is True
    assert result.sync_state == SyncState.SYNCING
    assert scheduled_calls == [(source.id, user.id)]
    await db_session.refresh(source)
    assert source.sync_state == SyncState.SYNCING.value
    assert source.sync_error is None


@pytest.mark.asyncio
async def test_request_sync_rejects_when_claim_fails(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user, source = await _connected_gmail_source(db_session)

    released: list[tuple[uuid.UUID, uuid.UUID]] = []

    def fake_schedule(source_id: uuid.UUID, user_id: uuid.UUID) -> bool:
        return True

    async def fake_claim(_self: SourceService, _source) -> bool:
        return False

    def fake_release(source_id: uuid.UUID, user_id: uuid.UUID) -> None:
        released.append((source_id, user_id))

    monkeypatch.setattr(
        "contactsafe_server.services.source_service.schedule_source_sync",
        fake_schedule,
    )
    monkeypatch.setattr(SourceService, "_try_claim_sync", fake_claim)
    monkeypatch.setattr(
        "contactsafe_server.services.source_service.release_sync_lock",
        fake_release,
    )

    service = SourceService(db_session)
    result = await service.request_sync(source.id)

    assert result.scheduled is False
    assert "already running" in result.message.lower()
    assert released == [(source.id, user.id)]
