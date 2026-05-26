import json
import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from contactsafe_core.enums import (
    OAuthProvider,
    SessionStatus,
    SourceConnectionStatus,
    SourceType,
    SyncState,
)
from contactsafe_core.schemas import (
    ListSourcesResult,
    SourceStatusResult,
    SyncSourceResult,
)
from contactsafe_server.db.models import ConnectSession, OAuthCredential, Source, User
from contactsafe_server.services.source_service import SourceService, _STALE_SYNC_TIMEOUT
from contactsafe_server.utils import parse_connect_session_id, parse_source_id


# ---------------------------------------------------------------------------
# Existing tests (unchanged)
# ---------------------------------------------------------------------------


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


async def _connected_gmail_source(db_session: AsyncSession) -> tuple[User, Source]:
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
        external_account_id=user.email,
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

    async def fake_claim(_self: SourceService, _source: Source) -> bool:
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


# ---------------------------------------------------------------------------
# Helpers for mock-based unit tests
# ---------------------------------------------------------------------------


def _make_source(
    *,
    user_id: uuid.UUID | None = None,
    source_type: str = SourceType.GOOGLE_MAIL.value,
    connection_status: str = SourceConnectionStatus.CONNECTED.value,
    sync_state: str = SyncState.PENDING.value,
    contacts_found: int = 0,
    contacts_resolved: int = 0,
    contacts_pending: int = 0,
    sync_started_at: datetime | None = None,
    sync_error: str | None = None,
    external_account_id: str = "user@example.com",
    label: str = "Gmail",
) -> MagicMock:
    src: MagicMock = MagicMock(spec=Source)
    src.id = uuid.uuid4()
    src.user_id = user_id or uuid.uuid4()
    src.source_type = source_type
    src.label = label
    src.external_account_id = external_account_id
    src.connection_status = connection_status
    src.sync_state = sync_state
    src.contacts_found = contacts_found
    src.contacts_resolved = contacts_resolved
    src.contacts_pending = contacts_pending
    src.sync_started_at = sync_started_at
    src.sync_error = sync_error
    src.created_at = datetime.now(tz=UTC)
    src.updated_at = datetime.now(tz=UTC)
    return src


def _make_user(*, email: str = "user@example.com") -> MagicMock:
    u: MagicMock = MagicMock(spec=User)
    u.id = uuid.uuid4()
    u.email = email
    return u


def _make_connect_session(
    *,
    user_id: uuid.UUID | None = None,
    status: str = SessionStatus.PENDING.value,
) -> MagicMock:
    s: MagicMock = MagicMock(spec=ConnectSession)
    s.id = uuid.uuid4()
    s.user_id = user_id
    s.status = status
    s.state = str(uuid.uuid4())
    s.requested_scopes = []
    return s


def _make_credential(
    *,
    user_id: uuid.UUID,
    source_id: uuid.UUID | None = None,
    scopes: list[str] | None = None,
    is_valid: bool = True,
) -> MagicMock:
    c: MagicMock = MagicMock(spec=OAuthCredential)
    c.id = uuid.uuid4()
    c.user_id = user_id
    c.source_id = source_id
    c.provider = OAuthProvider.GOOGLE.value
    c.external_account_id = "user@example.com"
    c.scopes = scopes or ["https://www.googleapis.com/auth/gmail.readonly"]
    c.is_valid = is_valid
    return c


def _noop_scheduler(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "contactsafe_server.services.source_service.schedule_source_sync",
        lambda sid, uid: True,
    )
    monkeypatch.setattr(
        "contactsafe_server.services.source_service.is_source_sync_running",
        lambda sid: False,
    )
    monkeypatch.setattr(
        "contactsafe_server.services.source_service.is_user_sync_running",
        lambda uid: False,
    )
    monkeypatch.setattr(
        "contactsafe_server.services.source_service.release_sync_lock",
        lambda sid, uid: None,
    )


# ---------------------------------------------------------------------------
# ensure_google_contacts_source
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ensure_google_contacts_source_creates_new(db_session: AsyncSession) -> None:
    user: User = User(email="contacts@example.com")
    db_session.add(user)
    await db_session.flush()

    svc: SourceService = SourceService(db_session)
    source: Source = await svc.ensure_google_contacts_source(user.id, " Contacts@Example.COM ")

    assert source.source_type == SourceType.GOOGLE_CONTACTS.value
    assert source.external_account_id == "contacts@example.com"
    assert source.connection_status == SourceConnectionStatus.CONNECTED.value
    assert source.sync_state == SyncState.PENDING.value
    assert source.label == "contacts@example.com (contacts)"


@pytest.mark.asyncio
async def test_ensure_google_contacts_source_idempotent(db_session: AsyncSession) -> None:
    user: User = User(email="contacts@example.com")
    db_session.add(user)
    await db_session.flush()

    svc: SourceService = SourceService(db_session)
    first: Source = await svc.ensure_google_contacts_source(user.id, "contacts@example.com")
    second: Source = await svc.ensure_google_contacts_source(user.id, "contacts@example.com")

    assert first.id == second.id
    assert second.connection_status == SourceConnectionStatus.CONNECTED.value


# ---------------------------------------------------------------------------
# link_credential_to_source
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_link_credential_to_source(db_session: AsyncSession) -> None:
    from contactsafe_server.services.crypto import TokenEncryptor
    from contactsafe_server.config import get_settings

    user: User = User(email="link@example.com")
    db_session.add(user)
    await db_session.flush()

    svc: SourceService = SourceService(db_session)
    source: Source = await svc.ensure_google_mail_source(user.id, user.email)

    encryptor: TokenEncryptor = TokenEncryptor(get_settings().token_encryption_key)
    cred: OAuthCredential = OAuthCredential(
        user_id=user.id,
        provider=OAuthProvider.GOOGLE.value,
        external_account_id=user.email,
        access_token_encrypted=encryptor.encrypt("access"),
        refresh_token_encrypted=encryptor.encrypt("refresh"),
        token_expires_at=datetime.now(tz=UTC) + timedelta(hours=1),
        scopes=["https://www.googleapis.com/auth/gmail.readonly"],
        is_valid=True,
    )
    db_session.add(cred)
    await db_session.flush()

    assert cred.source_id is None
    await svc.link_credential_to_source(cred, source)
    assert cred.source_id == source.id


# ---------------------------------------------------------------------------
# list_sources_for_user
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_sources_for_user_empty(db_session: AsyncSession) -> None:
    user: User = User(email="empty@example.com")
    db_session.add(user)
    await db_session.flush()

    svc: SourceService = SourceService(db_session)
    result: ListSourcesResult = await svc.list_sources_for_user(user.id)

    assert result.sources == []
    assert "No data sources" in result.message


@pytest.mark.asyncio
async def test_list_sources_for_user_populated(db_session: AsyncSession) -> None:
    user: User = User(email="pop@example.com")
    db_session.add(user)
    await db_session.flush()

    svc: SourceService = SourceService(db_session)
    await svc.ensure_google_mail_source(user.id, user.email)
    await svc.ensure_google_contacts_source(user.id, user.email)

    result: ListSourcesResult = await svc.list_sources_for_user(user.id)

    assert len(result.sources) == 2
    assert "2 source(s)" in result.message
    types: set[SourceType] = {s.source_type for s in result.sources}
    assert SourceType.GOOGLE_MAIL in types
    assert SourceType.GOOGLE_CONTACTS in types


# ---------------------------------------------------------------------------
# get_source_status
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_source_status_unknown_source(db_session: AsyncSession) -> None:
    svc: SourceService = SourceService(db_session)
    with pytest.raises(ValueError, match="Unknown source_id"):
        await svc.get_source_status(uuid.uuid4())


@pytest.mark.asyncio
async def test_get_source_status_without_connect_session(db_session: AsyncSession) -> None:
    user: User = User(email="status@example.com")
    db_session.add(user)
    await db_session.flush()

    svc: SourceService = SourceService(db_session)
    source: Source = await svc.ensure_google_mail_source(user.id, user.email)

    result: SourceStatusResult = await svc.get_source_status(source.id)

    assert result.source_id == source.id
    assert result.connect_session_id is None
    assert result.status == SessionStatus.PENDING
    assert result.connection_status == SourceConnectionStatus.CONNECTED
    assert result.sync_state == SyncState.PENDING
    assert result.email == user.email


@pytest.mark.asyncio
async def test_get_source_status_with_connect_session(db_session: AsyncSession) -> None:
    user: User = User(email="sess@example.com")
    db_session.add(user)
    await db_session.flush()

    session: ConnectSession = ConnectSession(
        user_id=user.id,
        state=str(uuid.uuid4()),
        status=SessionStatus.CONNECTED.value,
        requested_scopes=["openid"],
    )
    db_session.add(session)
    await db_session.flush()

    svc: SourceService = SourceService(db_session)
    source: Source = await svc.ensure_google_mail_source(user.id, user.email)

    result: SourceStatusResult = await svc.get_source_status(
        source.id, connect_session_id=session.id
    )

    assert result.connect_session_id == session.id
    assert result.status == SessionStatus.CONNECTED


# ---------------------------------------------------------------------------
# get_source_status_for_connect_session
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_source_status_for_connect_session_unknown(db_session: AsyncSession) -> None:
    svc: SourceService = SourceService(db_session)
    with pytest.raises(ValueError, match="Unknown connect_session_id"):
        await svc.get_source_status_for_connect_session(uuid.uuid4())


@pytest.mark.asyncio
async def test_get_source_status_for_connect_session_pending(db_session: AsyncSession) -> None:
    session: ConnectSession = ConnectSession(
        state=str(uuid.uuid4()),
        status=SessionStatus.PENDING.value,
        requested_scopes=["openid"],
    )
    db_session.add(session)
    await db_session.flush()

    svc: SourceService = SourceService(db_session)
    result: SourceStatusResult = await svc.get_source_status_for_connect_session(session.id)

    assert result.status == SessionStatus.PENDING
    assert result.connection_status == SourceConnectionStatus.PENDING_OAUTH
    assert "OAuth" in result.message


@pytest.mark.asyncio
async def test_get_source_status_for_connect_session_connected_no_source(
    db_session: AsyncSession,
) -> None:
    user: User = User(email="nosource@example.com")
    db_session.add(user)
    await db_session.flush()

    session: ConnectSession = ConnectSession(
        user_id=user.id,
        state=str(uuid.uuid4()),
        status=SessionStatus.CONNECTED.value,
        requested_scopes=["openid"],
    )
    db_session.add(session)
    await db_session.flush()

    svc: SourceService = SourceService(db_session)
    result: SourceStatusResult = await svc.get_source_status_for_connect_session(session.id)

    assert result.status == SessionStatus.CONNECTED
    assert result.connection_status == SourceConnectionStatus.PENDING_OAUTH
    assert result.email == user.email
    assert "no mail source" in result.message.lower()


@pytest.mark.asyncio
async def test_get_source_status_for_connect_session_connected_with_source(
    db_session: AsyncSession,
) -> None:
    user: User = User(email="withsrc@example.com")
    db_session.add(user)
    await db_session.flush()

    session: ConnectSession = ConnectSession(
        user_id=user.id,
        state=str(uuid.uuid4()),
        status=SessionStatus.CONNECTED.value,
        requested_scopes=["openid"],
    )
    db_session.add(session)
    await db_session.flush()

    svc: SourceService = SourceService(db_session)
    await svc.ensure_google_mail_source(user.id, user.email)

    result: SourceStatusResult = await svc.get_source_status_for_connect_session(session.id)

    assert result.status == SessionStatus.CONNECTED
    assert result.connection_status == SourceConnectionStatus.CONNECTED


@pytest.mark.asyncio
async def test_get_source_status_for_connect_session_failed_overrides_message(
    db_session: AsyncSession,
) -> None:
    user: User = User(email="failed@example.com")
    db_session.add(user)
    await db_session.flush()

    session: ConnectSession = ConnectSession(
        user_id=user.id,
        state=str(uuid.uuid4()),
        status=SessionStatus.FAILED.value,
        requested_scopes=["openid"],
    )
    db_session.add(session)
    await db_session.flush()

    svc: SourceService = SourceService(db_session)
    await svc.ensure_google_mail_source(user.id, user.email)

    result: SourceStatusResult = await svc.get_source_status_for_connect_session(session.id)

    assert result.status == SessionStatus.FAILED
    assert "OAuth failed" in result.message


# ---------------------------------------------------------------------------
# get_source_status_for_user
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_source_status_for_user_no_source(db_session: AsyncSession) -> None:
    user: User = User(email="nomail@example.com")
    db_session.add(user)
    await db_session.flush()

    svc: SourceService = SourceService(db_session)
    result: SourceStatusResult = await svc.get_source_status_for_user(user.id)

    assert result.source_id == user.id
    assert result.status == SessionStatus.CONNECTED
    assert result.connection_status == SourceConnectionStatus.PENDING_OAUTH
    assert result.email == user.email


@pytest.mark.asyncio
async def test_get_source_status_for_user_with_source(db_session: AsyncSession) -> None:
    user: User = User(email="hasmail@example.com")
    db_session.add(user)
    await db_session.flush()

    svc: SourceService = SourceService(db_session)
    source: Source = await svc.ensure_google_mail_source(user.id, user.email)

    result: SourceStatusResult = await svc.get_source_status_for_user(user.id)

    assert result.source_id == source.id
    assert result.status == SessionStatus.CONNECTED
    assert result.connection_status == SourceConnectionStatus.CONNECTED


# ---------------------------------------------------------------------------
# request_sync_for_user
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_request_sync_for_user_no_sources(db_session: AsyncSession) -> None:
    user: User = User(email="nosync@example.com")
    db_session.add(user)
    await db_session.flush()

    svc: SourceService = SourceService(db_session)
    with pytest.raises(ValueError, match="No google_mail source"):
        await svc.request_sync_for_user(user.id)


@pytest.mark.asyncio
async def test_request_sync_for_user_multiple_sources(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from contactsafe_server.services.crypto import TokenEncryptor
    from contactsafe_server.config import get_settings

    user: User = User(email="multi@example.com")
    db_session.add(user)
    await db_session.flush()

    encryptor: TokenEncryptor = TokenEncryptor(get_settings().token_encryption_key)

    svc: SourceService = SourceService(db_session)
    s1: Source = await svc.ensure_google_mail_source(user.id, "a@example.com")
    s2: Source = await svc.ensure_google_mail_source(user.id, "b@example.com")

    for s in (s1, s2):
        cred: OAuthCredential = OAuthCredential(
            user_id=user.id,
            source_id=s.id,
            provider=OAuthProvider.GOOGLE.value,
            external_account_id=s.external_account_id,
            access_token_encrypted=encryptor.encrypt("access"),
            refresh_token_encrypted=encryptor.encrypt("refresh"),
            token_expires_at=datetime.now(tz=UTC) + timedelta(hours=1),
            scopes=["https://www.googleapis.com/auth/gmail.readonly"],
            is_valid=True,
        )
        db_session.add(cred)
    await db_session.flush()

    scheduled_ids: list[uuid.UUID] = []

    def fake_schedule(source_id: uuid.UUID, user_id: uuid.UUID) -> bool:
        scheduled_ids.append(source_id)
        return True

    monkeypatch.setattr(
        "contactsafe_server.services.source_service.schedule_source_sync",
        fake_schedule,
    )
    monkeypatch.setattr(
        "contactsafe_server.services.source_service.is_source_sync_running",
        lambda sid: False,
    )
    monkeypatch.setattr(
        "contactsafe_server.services.source_service.is_user_sync_running",
        lambda uid: False,
    )

    result: SyncSourceResult = await svc.request_sync_for_user(user.id)

    assert len(scheduled_ids) >= 1
    assert s1.id in scheduled_ids


# ---------------------------------------------------------------------------
# resolve_source_id
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_resolve_source_id_by_source_id(db_session: AsyncSession) -> None:
    user: User = User(email="resolve@example.com")
    db_session.add(user)
    await db_session.flush()

    svc: SourceService = SourceService(db_session)
    source: Source = await svc.ensure_google_mail_source(user.id, user.email)

    resolved: uuid.UUID = await svc.resolve_source_id(source_id=source.id)
    assert resolved == source.id


@pytest.mark.asyncio
async def test_resolve_source_id_by_source_id_unknown(db_session: AsyncSession) -> None:
    svc: SourceService = SourceService(db_session)
    with pytest.raises(ValueError, match="Unknown source_id"):
        await svc.resolve_source_id(source_id=uuid.uuid4())


@pytest.mark.asyncio
async def test_resolve_source_id_by_user_id(db_session: AsyncSession) -> None:
    user: User = User(email="resolve-user@example.com")
    db_session.add(user)
    await db_session.flush()

    svc: SourceService = SourceService(db_session)
    source: Source = await svc.ensure_google_mail_source(user.id, user.email)

    resolved: uuid.UUID = await svc.resolve_source_id(user_id=user.id)
    assert resolved == source.id


@pytest.mark.asyncio
async def test_resolve_source_id_by_user_id_no_source(db_session: AsyncSession) -> None:
    user: User = User(email="resolve-none@example.com")
    db_session.add(user)
    await db_session.flush()

    svc: SourceService = SourceService(db_session)
    with pytest.raises(ValueError, match="No google_mail source"):
        await svc.resolve_source_id(user_id=user.id)


@pytest.mark.asyncio
async def test_resolve_source_id_by_connect_session(db_session: AsyncSession) -> None:
    user: User = User(email="resolve-sess@example.com")
    db_session.add(user)
    await db_session.flush()

    session: ConnectSession = ConnectSession(
        user_id=user.id,
        state=str(uuid.uuid4()),
        status=SessionStatus.CONNECTED.value,
        requested_scopes=["openid"],
    )
    db_session.add(session)
    await db_session.flush()

    svc: SourceService = SourceService(db_session)
    source: Source = await svc.ensure_google_mail_source(user.id, user.email)

    resolved: uuid.UUID = await svc.resolve_source_id(connect_session_id=session.id)
    assert resolved == source.id


@pytest.mark.asyncio
async def test_resolve_source_id_by_connect_session_unknown(db_session: AsyncSession) -> None:
    svc: SourceService = SourceService(db_session)
    with pytest.raises(ValueError, match="Unknown connect_session_id"):
        await svc.resolve_source_id(connect_session_id=uuid.uuid4())


@pytest.mark.asyncio
async def test_resolve_source_id_by_connect_session_no_user(db_session: AsyncSession) -> None:
    session: ConnectSession = ConnectSession(
        state=str(uuid.uuid4()),
        status=SessionStatus.PENDING.value,
        requested_scopes=["openid"],
    )
    db_session.add(session)
    await db_session.flush()

    svc: SourceService = SourceService(db_session)
    with pytest.raises(ValueError, match="no linked user"):
        await svc.resolve_source_id(connect_session_id=session.id)


@pytest.mark.asyncio
async def test_resolve_source_id_no_identifiers(db_session: AsyncSession) -> None:
    svc: SourceService = SourceService(db_session)
    with pytest.raises(ValueError, match="Provide source_id"):
        await svc.resolve_source_id()


# ---------------------------------------------------------------------------
# resolve_user_id
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_resolve_user_id_direct(db_session: AsyncSession) -> None:
    uid: uuid.UUID = uuid.uuid4()
    svc: SourceService = SourceService(db_session)
    assert await svc.resolve_user_id(user_id=uid) == uid


@pytest.mark.asyncio
async def test_resolve_user_id_via_source(db_session: AsyncSession) -> None:
    user: User = User(email="resolve-uid@example.com")
    db_session.add(user)
    await db_session.flush()

    svc: SourceService = SourceService(db_session)
    source: Source = await svc.ensure_google_mail_source(user.id, user.email)

    resolved: uuid.UUID = await svc.resolve_user_id(source_id=source.id)
    assert resolved == user.id


# ---------------------------------------------------------------------------
# request_sync — edge cases (no cred, unsyncable, not connected)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_request_sync_unknown_source(db_session: AsyncSession) -> None:
    svc: SourceService = SourceService(db_session)
    with pytest.raises(ValueError, match="Unknown source_id"):
        await svc.request_sync(uuid.uuid4())


@pytest.mark.asyncio
async def test_request_sync_unsyncable_type(db_session: AsyncSession) -> None:
    user: User = User(email="unsyncable@example.com")
    db_session.add(user)
    await db_session.flush()

    source: Source = Source(
        user_id=user.id,
        source_type=SourceType.LINKEDIN_CONNECTIONS_UPLOAD.value,
        label="LinkedIn",
        external_account_id="linkedin",
        connection_status=SourceConnectionStatus.CONNECTED.value,
        sync_state=SyncState.PENDING.value,
    )
    db_session.add(source)
    await db_session.flush()

    svc: SourceService = SourceService(db_session)
    result: SyncSourceResult = await svc.request_sync(source.id)

    assert result.scheduled is False
    assert "not implemented" in result.message.lower()


@pytest.mark.asyncio
async def test_request_sync_not_connected(db_session: AsyncSession) -> None:
    user: User = User(email="notconn@example.com")
    db_session.add(user)
    await db_session.flush()

    source: Source = Source(
        user_id=user.id,
        source_type=SourceType.GOOGLE_MAIL.value,
        label="Gmail",
        external_account_id=user.email,
        connection_status=SourceConnectionStatus.PENDING_OAUTH.value,
        sync_state=SyncState.PENDING.value,
    )
    db_session.add(source)
    await db_session.flush()

    svc: SourceService = SourceService(db_session)
    result: SyncSourceResult = await svc.request_sync(source.id)

    assert result.scheduled is False
    assert "not connected" in result.message.lower()


@pytest.mark.asyncio
async def test_request_sync_no_credential(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user: User = User(email="nocred@example.com")
    db_session.add(user)
    await db_session.flush()

    source: Source = Source(
        user_id=user.id,
        source_type=SourceType.GOOGLE_MAIL.value,
        label="Gmail",
        external_account_id=user.email,
        connection_status=SourceConnectionStatus.CONNECTED.value,
        sync_state=SyncState.PENDING.value,
    )
    db_session.add(source)
    await db_session.flush()

    _noop_scheduler(monkeypatch)

    svc: SourceService = SourceService(db_session)
    result: SyncSourceResult = await svc.request_sync(source.id)

    assert result.scheduled is False
    assert "no valid credentials" in result.message.lower()


# ---------------------------------------------------------------------------
# request_sync_for_connect_session
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_request_sync_for_connect_session_unknown(db_session: AsyncSession) -> None:
    svc: SourceService = SourceService(db_session)
    with pytest.raises(ValueError, match="Unknown connect_session_id"):
        await svc.request_sync_for_connect_session(uuid.uuid4())


@pytest.mark.asyncio
async def test_request_sync_for_connect_session_not_connected(db_session: AsyncSession) -> None:
    session: ConnectSession = ConnectSession(
        state=str(uuid.uuid4()),
        status=SessionStatus.PENDING.value,
        requested_scopes=["openid"],
    )
    db_session.add(session)
    await db_session.flush()

    svc: SourceService = SourceService(db_session)
    result: SyncSourceResult = await svc.request_sync_for_connect_session(session.id)

    assert result.scheduled is False
    assert "not connected" in result.message.lower()


@pytest.mark.asyncio
async def test_request_sync_for_connect_session_no_user(db_session: AsyncSession) -> None:
    session: ConnectSession = ConnectSession(
        state=str(uuid.uuid4()),
        status=SessionStatus.CONNECTED.value,
        requested_scopes=["openid"],
    )
    db_session.add(session)
    await db_session.flush()

    svc: SourceService = SourceService(db_session)
    result: SyncSourceResult = await svc.request_sync_for_connect_session(session.id)

    assert result.scheduled is False
    assert "no linked user" in result.message.lower()


@pytest.mark.asyncio
async def test_request_sync_for_connect_session_happy_path(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user, source = await _connected_gmail_source(db_session)

    session: ConnectSession = ConnectSession(
        user_id=user.id,
        state=str(uuid.uuid4()),
        status=SessionStatus.CONNECTED.value,
        requested_scopes=["openid"],
    )
    db_session.add(session)
    await db_session.flush()

    _noop_scheduler(monkeypatch)

    svc: SourceService = SourceService(db_session)
    result: SyncSourceResult = await svc.request_sync_for_connect_session(session.id)

    assert result.scheduled is True
    assert result.sync_state == SyncState.SYNCING


# ---------------------------------------------------------------------------
# user_has_queryable_graph
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_user_has_queryable_graph_no_sources(db_session: AsyncSession) -> None:
    user: User = User(email="nograph@example.com")
    db_session.add(user)
    await db_session.flush()

    svc: SourceService = SourceService(db_session)
    assert await svc.user_has_queryable_graph(user.id) is False


@pytest.mark.asyncio
async def test_user_has_queryable_graph_pending(db_session: AsyncSession) -> None:
    user: User = User(email="pendgraph@example.com")
    db_session.add(user)
    await db_session.flush()

    svc: SourceService = SourceService(db_session)
    await svc.ensure_google_mail_source(user.id, user.email)

    assert await svc.user_has_queryable_graph(user.id) is False


@pytest.mark.asyncio
async def test_user_has_queryable_graph_partial(db_session: AsyncSession) -> None:
    user: User = User(email="partgraph@example.com")
    db_session.add(user)
    await db_session.flush()

    svc: SourceService = SourceService(db_session)
    source: Source = await svc.ensure_google_mail_source(user.id, user.email)
    source.sync_state = SyncState.PARTIAL.value
    await db_session.flush()

    assert await svc.user_has_queryable_graph(user.id) is True


@pytest.mark.asyncio
async def test_user_has_queryable_graph_complete(db_session: AsyncSession) -> None:
    user: User = User(email="compgraph@example.com")
    db_session.add(user)
    await db_session.flush()

    svc: SourceService = SourceService(db_session)
    source: Source = await svc.ensure_google_mail_source(user.id, user.email)
    source.sync_state = SyncState.COMPLETE.value
    await db_session.flush()

    assert await svc.user_has_queryable_graph(user.id) is True


@pytest.mark.asyncio
async def test_user_has_queryable_graph_contacts_source(db_session: AsyncSession) -> None:
    user: User = User(email="ctgraph@example.com")
    db_session.add(user)
    await db_session.flush()

    svc: SourceService = SourceService(db_session)
    source: Source = await svc.ensure_google_contacts_source(user.id, user.email)
    source.sync_state = SyncState.PARTIAL.value
    await db_session.flush()

    assert await svc.user_has_queryable_graph(user.id) is True


# ---------------------------------------------------------------------------
# _sync_in_progress (static — no DB needed)
# ---------------------------------------------------------------------------


class TestSyncInProgress:
    def test_user_sync_running(self, monkeypatch: pytest.MonkeyPatch) -> None:
        source: Source = _make_source(sync_state=SyncState.PENDING.value)
        monkeypatch.setattr(
            "contactsafe_server.services.source_service.is_user_sync_running",
            lambda uid: True,
        )
        monkeypatch.setattr(
            "contactsafe_server.services.source_service.is_source_sync_running",
            lambda sid: False,
        )
        assert SourceService._sync_in_progress(source, source.user_id) is True

    def test_source_sync_running(self, monkeypatch: pytest.MonkeyPatch) -> None:
        source: Source = _make_source(sync_state=SyncState.PENDING.value)
        monkeypatch.setattr(
            "contactsafe_server.services.source_service.is_user_sync_running",
            lambda uid: False,
        )
        monkeypatch.setattr(
            "contactsafe_server.services.source_service.is_source_sync_running",
            lambda sid: True,
        )
        assert SourceService._sync_in_progress(source, source.user_id) is True

    def test_no_lock_not_syncing_state(self, monkeypatch: pytest.MonkeyPatch) -> None:
        source: Source = _make_source(sync_state=SyncState.PENDING.value)
        monkeypatch.setattr(
            "contactsafe_server.services.source_service.is_user_sync_running",
            lambda uid: False,
        )
        monkeypatch.setattr(
            "contactsafe_server.services.source_service.is_source_sync_running",
            lambda sid: False,
        )
        assert SourceService._sync_in_progress(source, source.user_id) is False

    def test_syncing_state_no_lock_within_timeout(self, monkeypatch: pytest.MonkeyPatch) -> None:
        source: Source = _make_source(
            sync_state=SyncState.SYNCING.value,
            sync_started_at=datetime.now(tz=UTC) - timedelta(minutes=5),
        )
        monkeypatch.setattr(
            "contactsafe_server.services.source_service.is_user_sync_running",
            lambda uid: False,
        )
        monkeypatch.setattr(
            "contactsafe_server.services.source_service.is_source_sync_running",
            lambda sid: False,
        )
        assert SourceService._sync_in_progress(source, source.user_id) is True

    def test_syncing_state_stale_timeout(self, monkeypatch: pytest.MonkeyPatch) -> None:
        source: Source = _make_source(
            sync_state=SyncState.SYNCING.value,
            sync_started_at=datetime.now(tz=UTC) - _STALE_SYNC_TIMEOUT - timedelta(minutes=1),
        )
        monkeypatch.setattr(
            "contactsafe_server.services.source_service.is_user_sync_running",
            lambda uid: False,
        )
        monkeypatch.setattr(
            "contactsafe_server.services.source_service.is_source_sync_running",
            lambda sid: False,
        )
        assert SourceService._sync_in_progress(source, source.user_id) is False

    def test_syncing_state_no_started_at(self, monkeypatch: pytest.MonkeyPatch) -> None:
        source: Source = _make_source(
            sync_state=SyncState.SYNCING.value,
            sync_started_at=None,
        )
        monkeypatch.setattr(
            "contactsafe_server.services.source_service.is_user_sync_running",
            lambda uid: False,
        )
        monkeypatch.setattr(
            "contactsafe_server.services.source_service.is_source_sync_running",
            lambda sid: False,
        )
        assert SourceService._sync_in_progress(source, source.user_id) is True


# ---------------------------------------------------------------------------
# _sync_message (static — no DB needed)
# ---------------------------------------------------------------------------


class TestSyncMessage:
    def test_sync_error(self) -> None:
        source: Source = _make_source(sync_error="disk full")
        msg: str = SourceService._sync_message(source)
        assert msg == "Sync failed: disk full"

    def test_syncing_no_contacts(self) -> None:
        source: Source = _make_source(sync_state=SyncState.SYNCING.value)
        msg: str = SourceService._sync_message(source)
        assert "Scanning Gmail" in msg

    def test_syncing_contacts_found(self) -> None:
        source: Source = _make_source(
            sync_state=SyncState.SYNCING.value, contacts_found=50
        )
        msg: str = SourceService._sync_message(source)
        assert "50 contacts found" in msg

    def test_syncing_contacts_resolved(self) -> None:
        source: Source = _make_source(
            sync_state=SyncState.SYNCING.value,
            contacts_found=100,
            contacts_resolved=42,
        )
        msg: str = SourceService._sync_message(source)
        assert "42/100" in msg

    def test_syncing_google_contacts_label(self) -> None:
        source: Source = _make_source(
            source_type=SourceType.GOOGLE_CONTACTS.value,
            sync_state=SyncState.SYNCING.value,
        )
        msg: str = SourceService._sync_message(source)
        assert "Google Contacts" in msg

    def test_partial(self) -> None:
        source: Source = _make_source(
            sync_state=SyncState.PARTIAL.value, contacts_resolved=25
        )
        msg: str = SourceService._sync_message(source)
        assert "Partial" in msg
        assert "25 contacts" in msg

    def test_complete(self) -> None:
        source: Source = _make_source(
            sync_state=SyncState.COMPLETE.value, contacts_resolved=200
        )
        msg: str = SourceService._sync_message(source)
        assert "complete" in msg.lower()
        assert "200" in msg

    def test_failed_with_error(self) -> None:
        source: Source = _make_source(
            sync_state=SyncState.FAILED.value, sync_error="token expired"
        )
        msg: str = SourceService._sync_message(source)
        assert "token expired" in msg

    def test_failed_no_error(self) -> None:
        source: Source = _make_source(sync_state=SyncState.FAILED.value)
        msg: str = SourceService._sync_message(source)
        assert "unknown error" in msg

    def test_pending_default(self) -> None:
        source: Source = _make_source(sync_state=SyncState.PENDING.value)
        msg: str = SourceService._sync_message(source)
        assert "sync_source" in msg.lower()


# ---------------------------------------------------------------------------
# _oauth_session_message (static — no DB needed)
# ---------------------------------------------------------------------------


class TestOAuthSessionMessage:
    def test_pending(self) -> None:
        msg: str = SourceService._oauth_session_message(SessionStatus.PENDING)
        assert "Waiting" in msg

    def test_failed(self) -> None:
        msg: str = SourceService._oauth_session_message(SessionStatus.FAILED)
        assert "failed" in msg.lower()

    def test_connected(self) -> None:
        msg: str = SourceService._oauth_session_message(SessionStatus.CONNECTED)
        assert "connected" in msg.lower()


# ---------------------------------------------------------------------------
# request_sync — in-progress via scheduler lock
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_request_sync_rejects_when_scheduler_lock_held(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user, source = await _connected_gmail_source(db_session)

    monkeypatch.setattr(
        "contactsafe_server.services.source_service.is_source_sync_running",
        lambda sid: False,
    )
    monkeypatch.setattr(
        "contactsafe_server.services.source_service.is_user_sync_running",
        lambda uid: True,
    )

    svc: SourceService = SourceService(db_session)
    result: SyncSourceResult = await svc.request_sync(source.id)

    assert result.scheduled is False
    assert "already running" in result.message.lower()


@pytest.mark.asyncio
async def test_request_sync_rejects_when_schedule_returns_false(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user, source = await _connected_gmail_source(db_session)

    monkeypatch.setattr(
        "contactsafe_server.services.source_service.is_source_sync_running",
        lambda sid: False,
    )
    monkeypatch.setattr(
        "contactsafe_server.services.source_service.is_user_sync_running",
        lambda uid: False,
    )
    monkeypatch.setattr(
        "contactsafe_server.services.source_service.schedule_source_sync",
        lambda sid, uid: False,
    )

    svc: SourceService = SourceService(db_session)
    result: SyncSourceResult = await svc.request_sync(source.id)

    assert result.scheduled is False
    assert "already running" in result.message.lower()


# ---------------------------------------------------------------------------
# ensure_google_mail_source — normalizes + updates on re-ensure
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ensure_google_mail_source_normalizes_email(db_session: AsyncSession) -> None:
    user: User = User(email="norm@example.com")
    db_session.add(user)
    await db_session.flush()

    svc: SourceService = SourceService(db_session)
    source: Source = await svc.ensure_google_mail_source(user.id, "  Norm@Example.COM  ")

    assert source.external_account_id == "norm@example.com"
    assert source.label == "norm@example.com"


@pytest.mark.asyncio
async def test_ensure_google_mail_source_updates_status_on_re_ensure(
    db_session: AsyncSession,
) -> None:
    user: User = User(email="reconn@example.com")
    db_session.add(user)
    await db_session.flush()

    source: Source = Source(
        user_id=user.id,
        source_type=SourceType.GOOGLE_MAIL.value,
        label="old-label",
        external_account_id=user.email,
        connection_status=SourceConnectionStatus.DISCONNECTED.value,
        sync_state=SyncState.FAILED.value,
    )
    db_session.add(source)
    await db_session.flush()

    svc: SourceService = SourceService(db_session)
    updated: Source = await svc.ensure_google_mail_source(user.id, user.email)

    assert updated.id == source.id
    assert updated.connection_status == SourceConnectionStatus.CONNECTED.value


# ---------------------------------------------------------------------------
# _to_summary (static)
# ---------------------------------------------------------------------------


def test_to_summary() -> None:
    source: Source = _make_source(
        contacts_found=10,
        contacts_resolved=5,
        contacts_pending=3,
    )
    summary = SourceService._to_summary(source)

    assert summary.source_id == source.id
    assert summary.source_type == SourceType.GOOGLE_MAIL
    assert summary.contacts_found == 10
    assert summary.contacts_resolved == 5
    assert summary.contacts_pending == 3
    assert summary.connection_status == SourceConnectionStatus.CONNECTED
    assert summary.sync_state == SyncState.PENDING
