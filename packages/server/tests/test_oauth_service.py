"""Comprehensive tests for OAuthService."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from contactsafe_core.enums import (
    IdentityKind,
    OAuthProvider,
    SessionStatus,
    SourceConnectionStatus,
    SourceType,
    SyncState,
)
from contactsafe_core.schemas import ConnectSourceResult
from contactsafe_server.config import get_settings, Settings
from contactsafe_server.db.models import (
    ConnectSession,
    OAuthCredential,
    Source,
    User,
    UserIdentity,
)
from contactsafe_server.oauth.google import GoogleOAuthClient, GoogleTokens, GoogleUserInfo
from contactsafe_server.services.crypto import TokenEncryptor
from contactsafe_server.services.oauth_service import OAuthService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _settings() -> Settings:
    return get_settings()


def _encryptor(settings: Settings | None = None) -> TokenEncryptor:
    s: Settings = settings or _settings()
    return TokenEncryptor(s.token_encryption_key)


def _mock_google() -> AsyncMock:
    """Return a fully-mocked GoogleOAuthClient."""
    mock: AsyncMock = AsyncMock(spec=GoogleOAuthClient)
    mock.build_authorization_url = MagicMock(return_value="https://accounts.google.com/authorize?state=abc")
    return mock


def _make_tokens(
    access: str = "access-tok",
    refresh: str = "refresh-tok",
    scopes: list[str] | None = None,
) -> GoogleTokens:
    return GoogleTokens(
        access_token=access,
        refresh_token=refresh,
        expires_at=datetime.now(tz=UTC) + timedelta(hours=1),
        scopes=scopes or ["openid", "email"],
    )


def _make_userinfo(
    email: str = "alice@example.com",
    name: str | None = "Alice",
    picture: str | None = "https://img.example.com/alice.png",
) -> GoogleUserInfo:
    info: GoogleUserInfo = {"sub": "google-sub-123", "email": email, "email_verified": True}
    if name is not None:
        info["name"] = name
    if picture is not None:
        info["picture"] = picture
    return info


def _build_service(
    db: AsyncSession,
    settings: Settings | None = None,
    google: AsyncMock | None = None,
) -> OAuthService:
    s: Settings = settings or _settings()
    return OAuthService(
        db=db,
        settings=s,
        encryptor=_encryptor(s),
        google=google or _mock_google(),
    )


async def _seed_user(
    db: AsyncSession,
    email: str = "alice@example.com",
    *,
    with_identity: bool = True,
) -> User:
    user: User = User(email=email, google_profile_name="Alice")
    db.add(user)
    await db.flush()
    if with_identity:
        identity: UserIdentity = UserIdentity(
            user_id=user.id,
            kind=IdentityKind.EMAIL.value,
            value=email,
            is_primary=True,
            verified_at=datetime.now(tz=UTC),
        )
        db.add(identity)
        await db.flush()
    return user


async def _seed_credential(
    db: AsyncSession,
    user_id: uuid.UUID,
    email: str = "alice@example.com",
    *,
    is_valid: bool = True,
) -> OAuthCredential:
    enc: TokenEncryptor = _encryptor()
    cred: OAuthCredential = OAuthCredential(
        user_id=user_id,
        provider=OAuthProvider.GOOGLE.value,
        external_account_id=email,
        access_token_encrypted=enc.encrypt("access-tok"),
        refresh_token_encrypted=enc.encrypt("refresh-tok"),
        token_expires_at=datetime.now(tz=UTC) + timedelta(hours=1),
        scopes=["openid", "email"],
        is_valid=is_valid,
    )
    db.add(cred)
    await db.flush()
    return cred


async def _seed_source(
    db: AsyncSession,
    user_id: uuid.UUID,
    email: str = "alice@example.com",
    *,
    source_type: str = SourceType.GOOGLE_MAIL.value,
    sync_state: str = SyncState.PENDING.value,
    sync_error: str | None = None,
) -> Source:
    source: Source = Source(
        user_id=user_id,
        source_type=source_type,
        label=email,
        external_account_id=email,
        connection_status=SourceConnectionStatus.CONNECTED.value,
        sync_state=sync_state,
        sync_error=sync_error,
    )
    db.add(source)
    await db.flush()
    return source


# ===================================================================
# create_connect_session
# ===================================================================


class TestCreateConnectSession:
    """Tests for OAuthService.create_connect_session."""

    async def test_new_session_without_user_token(self, db_session: AsyncSession) -> None:
        svc: OAuthService = _build_service(db_session)

        result: ConnectSourceResult = await svc.create_connect_session()

        assert result.status == SessionStatus.PENDING
        assert result.already_connected is False
        assert result.connect_session_id is not None
        assert "oauth/start" in result.oauth_url

    async def test_new_session_creates_db_row(self, db_session: AsyncSession) -> None:
        svc: OAuthService = _build_service(db_session)

        result: ConnectSourceResult = await svc.create_connect_session()

        row: ConnectSession | None = await db_session.get(ConnectSession, result.connect_session_id)
        assert row is not None
        assert row.status == SessionStatus.PENDING.value

    async def test_new_session_with_user_token_no_existing_user(self, db_session: AsyncSession) -> None:
        svc: OAuthService = _build_service(db_session)

        result: ConnectSourceResult = await svc.create_connect_session(user_token="unknown@example.com")

        assert result.status == SessionStatus.PENDING
        assert result.already_connected is False

    async def test_existing_user_with_valid_cred_returns_already_connected(self, db_session: AsyncSession) -> None:
        user: User = await _seed_user(db_session)
        await _seed_credential(db_session, user.id)
        await _seed_source(db_session, user.id)

        svc: OAuthService = _build_service(db_session)
        result: ConnectSourceResult = await svc.create_connect_session(user_token="alice@example.com")

        assert result.already_connected is True
        assert result.status == SessionStatus.CONNECTED
        assert result.email == "alice@example.com"
        assert result.source_id is not None
        assert result.poll_secret is None

    async def test_existing_user_with_invalid_cred_creates_new_session(self, db_session: AsyncSession) -> None:
        user: User = await _seed_user(db_session)
        await _seed_credential(db_session, user.id, is_valid=False)

        svc: OAuthService = _build_service(db_session)
        result: ConnectSourceResult = await svc.create_connect_session(user_token="alice@example.com")

        assert result.already_connected is False
        assert result.status == SessionStatus.PENDING

    async def test_unsupported_source_type_raises(self, db_session: AsyncSession) -> None:
        svc: OAuthService = _build_service(db_session)

        with pytest.raises(ValueError, match="not implemented"):
            await svc.create_connect_session(source_type=SourceType.LINKEDIN_CONNECTIONS_UPLOAD)

    async def test_google_contacts_source_type_accepted(self, db_session: AsyncSession) -> None:
        svc: OAuthService = _build_service(db_session)

        result: ConnectSourceResult = await svc.create_connect_session(
            source_type=SourceType.GOOGLE_CONTACTS
        )

        assert result.status == SessionStatus.PENDING

    async def test_authenticated_user_id_stored_on_session(self, db_session: AsyncSession) -> None:
        user: User = await _seed_user(db_session)
        svc: OAuthService = _build_service(db_session)

        result: ConnectSourceResult = await svc.create_connect_session(
            authenticated_user_id=user.id,
        )

        row: ConnectSession | None = await db_session.get(ConnectSession, result.connect_session_id)
        assert row is not None
        assert row.user_id == user.id

    async def test_email_normalization_on_user_token(self, db_session: AsyncSession) -> None:
        user: User = await _seed_user(db_session, email="bob@example.com")
        await _seed_credential(db_session, user.id, email="bob@example.com")
        await _seed_source(db_session, user.id, email="bob@example.com")

        svc: OAuthService = _build_service(db_session)
        result: ConnectSourceResult = await svc.create_connect_session(
            user_token="  Bob@Example.COM  "
        )

        assert result.already_connected is True


# ===================================================================
# get_session_by_id / get_session_by_state
# ===================================================================


class TestGetSession:
    async def test_get_session_by_id_found(self, db_session: AsyncSession) -> None:
        svc: OAuthService = _build_service(db_session)
        result: ConnectSourceResult = await svc.create_connect_session()

        session: ConnectSession | None = await svc.get_session_by_id(result.connect_session_id)

        assert session is not None
        assert session.id == result.connect_session_id

    async def test_get_session_by_id_not_found(self, db_session: AsyncSession) -> None:
        svc: OAuthService = _build_service(db_session)

        session: ConnectSession | None = await svc.get_session_by_id(uuid.uuid4())

        assert session is None

    async def test_get_session_by_state_found(self, db_session: AsyncSession) -> None:
        svc: OAuthService = _build_service(db_session)
        result: ConnectSourceResult = await svc.create_connect_session()

        created: ConnectSession | None = await svc.get_session_by_id(result.connect_session_id)
        assert created is not None

        found: ConnectSession | None = await svc.get_session_by_state(created.state)

        assert found is not None
        assert found.id == created.id

    async def test_get_session_by_state_not_found(self, db_session: AsyncSession) -> None:
        svc: OAuthService = _build_service(db_session)

        found: ConnectSession | None = await svc.get_session_by_state("nonexistent-state")

        assert found is None


# ===================================================================
# build_google_authorization_url
# ===================================================================


class TestBuildAuthorizationUrl:
    async def test_delegates_to_google_client(self, db_session: AsyncSession) -> None:
        google: AsyncMock = _mock_google()
        svc: OAuthService = _build_service(db_session, google=google)

        result: ConnectSourceResult = await svc.create_connect_session()
        session: ConnectSession | None = await svc.get_session_by_id(result.connect_session_id)
        assert session is not None

        url: str = svc.build_google_authorization_url(session)

        google.build_authorization_url.assert_called_once_with(state=session.state)
        assert url == "https://accounts.google.com/authorize?state=abc"


# ===================================================================
# complete_oauth
# ===================================================================


class TestCompleteOauth:
    async def _setup_oauth(
        self,
        db: AsyncSession,
        *,
        email: str = "newuser@example.com",
        name: str | None = "New User",
        pre_seed_user: bool = False,
        session_user_id: uuid.UUID | None = None,
    ) -> tuple[OAuthService, ConnectSession, AsyncMock]:
        google: AsyncMock = _mock_google()
        tokens: GoogleTokens = _make_tokens()
        userinfo: GoogleUserInfo = _make_userinfo(email=email, name=name)
        google.exchange_code = AsyncMock(return_value=tokens)
        google.fetch_userinfo = AsyncMock(return_value=userinfo)

        if pre_seed_user:
            await _seed_user(db, email=email)

        svc: OAuthService = _build_service(db, google=google)
        result: ConnectSourceResult = await svc.create_connect_session(
            authenticated_user_id=session_user_id,
        )
        session: ConnectSession | None = await svc.get_session_by_id(result.connect_session_id)
        assert session is not None
        return svc, session, google

    async def test_creates_new_user_and_source(self, db_session: AsyncSession) -> None:
        svc, session, google = await self._setup_oauth(db_session)

        user, source = await svc.complete_oauth(session, "auth-code-123")

        assert user.email == "newuser@example.com"
        assert user.google_profile_name == "New User"
        assert source.source_type == SourceType.GOOGLE_MAIL.value
        assert source.external_account_id == "newuser@example.com"
        google.exchange_code.assert_awaited_once_with("auth-code-123")
        google.fetch_userinfo.assert_awaited_once()

    async def test_marks_session_connected(self, db_session: AsyncSession) -> None:
        svc, session, _ = await self._setup_oauth(db_session)

        await svc.complete_oauth(session, "code")

        assert session.status == SessionStatus.CONNECTED.value
        assert session.completed_at is not None
        assert session.user_id is not None

    async def test_stores_encrypted_credentials(self, db_session: AsyncSession) -> None:
        svc, session, _ = await self._setup_oauth(db_session)

        user, _ = await svc.complete_oauth(session, "code")

        result = await db_session.execute(
            select(OAuthCredential).where(OAuthCredential.user_id == user.id)
        )
        cred: OAuthCredential | None = result.scalar_one_or_none()
        assert cred is not None
        assert cred.provider == OAuthProvider.GOOGLE.value
        assert cred.is_valid is True
        assert len(cred.access_token_encrypted) > 0
        assert len(cred.refresh_token_encrypted) > 0

    async def test_reconnect_existing_user(self, db_session: AsyncSession) -> None:
        svc, session, _ = await self._setup_oauth(
            db_session, email="alice@example.com", pre_seed_user=True
        )

        user, source = await svc.complete_oauth(session, "code")

        assert user.email == "alice@example.com"
        assert source is not None

    async def test_updates_profile_on_reconnect(self, db_session: AsyncSession) -> None:
        svc, session, _ = await self._setup_oauth(
            db_session, email="alice@example.com", name="Alice Updated", pre_seed_user=True,
        )

        user, _ = await svc.complete_oauth(session, "code")

        assert user.google_profile_name == "Alice Updated"

    async def test_links_new_email_to_authenticated_user(self, db_session: AsyncSession) -> None:
        existing: User = await _seed_user(db_session, email="existing@example.com")

        svc, session, _ = await self._setup_oauth(
            db_session,
            email="newemail@example.com",
            session_user_id=existing.id,
        )

        user, _ = await svc.complete_oauth(session, "code")

        assert user.id == existing.id
        result = await db_session.execute(
            select(UserIdentity).where(
                UserIdentity.user_id == existing.id,
                UserIdentity.value == "newemail@example.com",
            )
        )
        linked_identity: UserIdentity | None = result.scalar_one_or_none()
        assert linked_identity is not None
        assert linked_identity.is_primary is False

    async def test_raises_on_missing_email(self, db_session: AsyncSession) -> None:
        google: AsyncMock = _mock_google()
        google.exchange_code = AsyncMock(return_value=_make_tokens())
        google.fetch_userinfo = AsyncMock(return_value={"sub": "x", "email": "", "email_verified": True})

        svc: OAuthService = _build_service(db_session, google=google)
        result: ConnectSourceResult = await svc.create_connect_session()
        session: ConnectSession | None = await svc.get_session_by_id(result.connect_session_id)
        assert session is not None

        with pytest.raises(ValueError, match="email"):
            await svc.complete_oauth(session, "code")

    async def test_does_not_create_google_contacts_source(self, db_session: AsyncSession) -> None:
        svc, session, _ = await self._setup_oauth(db_session, email="contacts@example.com")

        user, _ = await svc.complete_oauth(session, "code")

        result = await db_session.execute(
            select(Source).where(
                Source.user_id == user.id,
                Source.source_type == SourceType.GOOGLE_CONTACTS.value,
            )
        )
        contacts_source: Source | None = result.scalar_one_or_none()
        assert contacts_source is None

        mail_result = await db_session.execute(
            select(Source).where(
                Source.user_id == user.id,
                Source.source_type == SourceType.GOOGLE_MAIL.value,
            )
        )
        assert mail_result.scalar_one_or_none() is not None

    async def test_session_references_nonexistent_user_raises(self, db_session: AsyncSession) -> None:
        """The DB FK constraint prevents a session from referencing a
        non-existent user, so _resolve_or_create_user raising ValueError
        for this case is tested via a mock session below."""
        fake_id: uuid.UUID = uuid.uuid4()
        google: AsyncMock = _mock_google()
        google.exchange_code = AsyncMock(return_value=_make_tokens())
        google.fetch_userinfo = AsyncMock(return_value=_make_userinfo(email="orphan@example.com"))

        svc: OAuthService = _build_service(db_session, google=google)

        mock_session: MagicMock = MagicMock(spec=ConnectSession)
        mock_session.user_id = fake_id
        mock_session.state = "mock-state"
        mock_session.status = SessionStatus.PENDING.value

        with pytest.raises(ValueError, match="non-existent user"):
            await svc._resolve_or_create_user(
                "orphan@example.com",
                _make_userinfo(email="orphan@example.com"),
                mock_session,
            )


# ===================================================================
# mark_session_failed
# ===================================================================


class TestMarkSessionFailed:
    async def test_sets_failed_status_and_timestamp(self, db_session: AsyncSession) -> None:
        svc: OAuthService = _build_service(db_session)
        result: ConnectSourceResult = await svc.create_connect_session()
        session: ConnectSession | None = await svc.get_session_by_id(result.connect_session_id)
        assert session is not None

        await svc.mark_session_failed(session)

        assert session.status == SessionStatus.FAILED.value
        assert session.completed_at is not None


# ===================================================================
# _check_existing_by_email
# ===================================================================


class TestCheckExistingByEmail:
    async def test_returns_none_when_user_not_found(self, db_session: AsyncSession) -> None:
        svc: OAuthService = _build_service(db_session)

        result: ConnectSourceResult | None = await svc._check_existing_by_email("nobody@example.com")

        assert result is None

    async def test_returns_none_when_no_valid_credential(self, db_session: AsyncSession) -> None:
        user: User = await _seed_user(db_session, email="nocred@example.com")

        svc: OAuthService = _build_service(db_session)
        result: ConnectSourceResult | None = await svc._check_existing_by_email("nocred@example.com")

        assert result is None

    async def test_returns_none_when_credential_is_invalid(self, db_session: AsyncSession) -> None:
        user: User = await _seed_user(db_session, email="invalidcred@example.com")
        await _seed_credential(db_session, user.id, email="invalidcred@example.com", is_valid=False)

        svc: OAuthService = _build_service(db_session)
        result: ConnectSourceResult | None = await svc._check_existing_by_email("invalidcred@example.com")

        assert result is None

    async def test_returns_result_when_user_has_valid_cred(self, db_session: AsyncSession) -> None:
        user: User = await _seed_user(db_session, email="valid@example.com")
        await _seed_credential(db_session, user.id, email="valid@example.com")

        svc: OAuthService = _build_service(db_session)
        result: ConnectSourceResult | None = await svc._check_existing_by_email("valid@example.com")

        assert result is not None
        assert result.already_connected is True
        assert result.status == SessionStatus.CONNECTED
        assert result.email == "valid@example.com"
        assert result.poll_secret is None
        row: ConnectSession | None = await db_session.get(
            ConnectSession, result.connect_session_id
        )
        assert row is not None
        assert row.poll_secret_hash is None

    async def test_triggers_sync_for_pending_source(self, db_session: AsyncSession) -> None:
        user: User = await _seed_user(db_session, email="sync@example.com")
        await _seed_credential(db_session, user.id, email="sync@example.com")
        source: Source = await _seed_source(
            db_session, user.id, email="sync@example.com",
            sync_state=SyncState.PENDING.value,
        )

        svc: OAuthService = _build_service(db_session)

        with patch.object(svc._sources, "request_sync", new_callable=AsyncMock) as mock_sync:
            await svc._check_existing_by_email("sync@example.com")
            mock_sync.assert_awaited_once_with(source.id)

    async def test_triggers_sync_for_failed_source(self, db_session: AsyncSession) -> None:
        user: User = await _seed_user(db_session, email="failed@example.com")
        await _seed_credential(db_session, user.id, email="failed@example.com")
        source: Source = await _seed_source(
            db_session, user.id, email="failed@example.com",
            sync_state=SyncState.FAILED.value,
        )

        svc: OAuthService = _build_service(db_session)

        with patch.object(svc._sources, "request_sync", new_callable=AsyncMock) as mock_sync:
            await svc._check_existing_by_email("failed@example.com")
            mock_sync.assert_awaited_once_with(source.id)

    async def test_triggers_sync_when_source_has_sync_error(self, db_session: AsyncSession) -> None:
        user: User = await _seed_user(db_session, email="errored@example.com")
        await _seed_credential(db_session, user.id, email="errored@example.com")
        await _seed_source(
            db_session, user.id, email="errored@example.com",
            sync_state=SyncState.COMPLETE.value,
            sync_error="something broke",
        )

        svc: OAuthService = _build_service(db_session)

        with patch.object(svc._sources, "request_sync", new_callable=AsyncMock) as mock_sync:
            await svc._check_existing_by_email("errored@example.com")
            mock_sync.assert_awaited_once()

    async def test_no_sync_for_complete_healthy_source(self, db_session: AsyncSession) -> None:
        user: User = await _seed_user(db_session, email="healthy@example.com")
        await _seed_credential(db_session, user.id, email="healthy@example.com")
        await _seed_source(
            db_session, user.id, email="healthy@example.com",
            sync_state=SyncState.COMPLETE.value,
        )

        svc: OAuthService = _build_service(db_session)

        with patch.object(svc._sources, "request_sync", new_callable=AsyncMock) as mock_sync:
            await svc._check_existing_by_email("healthy@example.com")
            mock_sync.assert_not_awaited()


# ===================================================================
# _resolve_or_create_user
# ===================================================================


class TestResolveOrCreateUser:
    async def test_known_email_returns_existing_user(self, db_session: AsyncSession) -> None:
        user: User = await _seed_user(db_session, email="known@example.com")
        svc: OAuthService = _build_service(db_session)
        session: ConnectSession = ConnectSession(
            state="s1", status=SessionStatus.PENDING.value, requested_scopes=["openid"],
        )
        db_session.add(session)
        await db_session.flush()

        userinfo: GoogleUserInfo = _make_userinfo(email="known@example.com", name="Updated")

        resolved: User = await svc._resolve_or_create_user("known@example.com", userinfo, session)

        assert resolved.id == user.id
        assert resolved.google_profile_name == "Updated"
        assert resolved.display_name == "Updated"

    async def test_reconnect_does_not_overwrite_custom_display_name(
        self, db_session: AsyncSession
    ) -> None:
        user: User = await _seed_user(db_session, email="known@example.com")
        user.display_name = "Custom Name"
        await db_session.flush()

        svc: OAuthService = _build_service(db_session)
        session: ConnectSession = ConnectSession(
            state="s1b", status=SessionStatus.PENDING.value, requested_scopes=["openid"],
        )
        db_session.add(session)
        await db_session.flush()

        userinfo: GoogleUserInfo = _make_userinfo(email="known@example.com", name="Updated")

        resolved: User = await svc._resolve_or_create_user("known@example.com", userinfo, session)

        assert resolved.google_profile_name == "Updated"
        assert resolved.display_name == "Custom Name"

    async def test_session_user_id_links_new_email(self, db_session: AsyncSession) -> None:
        user: User = await _seed_user(db_session, email="primary@example.com")
        svc: OAuthService = _build_service(db_session)
        session: ConnectSession = ConnectSession(
            state="s2", status=SessionStatus.PENDING.value,
            requested_scopes=["openid"], user_id=user.id,
        )
        db_session.add(session)
        await db_session.flush()

        userinfo: GoogleUserInfo = _make_userinfo(email="secondary@example.com")

        resolved: User = await svc._resolve_or_create_user("secondary@example.com", userinfo, session)

        assert resolved.id == user.id

        result = await db_session.execute(
            select(UserIdentity).where(UserIdentity.value == "secondary@example.com")
        )
        identity: UserIdentity | None = result.scalar_one_or_none()
        assert identity is not None
        assert identity.is_primary is False

    async def test_brand_new_user_created(self, db_session: AsyncSession) -> None:
        svc: OAuthService = _build_service(db_session)
        session: ConnectSession = ConnectSession(
            state="s3", status=SessionStatus.PENDING.value, requested_scopes=["openid"],
        )
        db_session.add(session)
        await db_session.flush()

        userinfo: GoogleUserInfo = _make_userinfo(email="brand-new@example.com", name="Brand New")

        resolved: User = await svc._resolve_or_create_user("brand-new@example.com", userinfo, session)

        assert resolved.email == "brand-new@example.com"
        assert resolved.google_profile_name == "Brand New"
        assert resolved.display_name == "Brand New"

        result = await db_session.execute(
            select(UserIdentity).where(UserIdentity.value == "brand-new@example.com")
        )
        identity: UserIdentity | None = result.scalar_one_or_none()
        assert identity is not None
        assert identity.is_primary is True

    async def test_session_references_deleted_user_raises(self, db_session: AsyncSession) -> None:
        """FK constraint prevents inserting a session with a non-existent user_id.
        Test the ValueError path via a mock session with a fake user_id."""
        svc: OAuthService = _build_service(db_session)
        fake_id: uuid.UUID = uuid.uuid4()

        mock_session: MagicMock = MagicMock(spec=ConnectSession)
        mock_session.user_id = fake_id

        userinfo: GoogleUserInfo = _make_userinfo(email="orphan@example.com")

        with pytest.raises(ValueError, match="non-existent user"):
            await svc._resolve_or_create_user("orphan@example.com", userinfo, mock_session)


# ===================================================================
# _upsert_credentials
# ===================================================================


class TestUpsertCredentials:
    async def test_creates_new_credential(self, db_session: AsyncSession) -> None:
        user: User = await _seed_user(db_session, email="cred-new@example.com")
        svc: OAuthService = _build_service(db_session)
        tokens: GoogleTokens = _make_tokens()

        cred: OAuthCredential = await svc._upsert_credentials(user.id, "cred-new@example.com", tokens)

        assert cred.user_id == user.id
        assert cred.provider == OAuthProvider.GOOGLE.value
        assert cred.external_account_id == "cred-new@example.com"
        assert cred.is_valid is True
        assert cred.scopes == tokens.scopes

    async def test_updates_existing_credential(self, db_session: AsyncSession) -> None:
        user: User = await _seed_user(db_session, email="cred-upd@example.com")
        old_cred: OAuthCredential = await _seed_credential(
            db_session, user.id, email="cred-upd@example.com", is_valid=False
        )
        old_id: uuid.UUID = old_cred.id

        svc: OAuthService = _build_service(db_session)
        new_tokens: GoogleTokens = _make_tokens(access="new-access", refresh="new-refresh", scopes=["a", "b"])

        updated: OAuthCredential = await svc._upsert_credentials(user.id, "cred-upd@example.com", new_tokens)

        assert updated.id == old_id
        assert updated.is_valid is True
        assert updated.scopes == ["a", "b"]

    async def test_new_cred_persisted_in_db(self, db_session: AsyncSession) -> None:
        user: User = await _seed_user(db_session, email="persist@example.com")
        svc: OAuthService = _build_service(db_session)
        tokens: GoogleTokens = _make_tokens()

        cred: OAuthCredential = await svc._upsert_credentials(user.id, "persist@example.com", tokens)

        result = await db_session.execute(
            select(OAuthCredential).where(OAuthCredential.id == cred.id)
        )
        from_db: OAuthCredential | None = result.scalar_one_or_none()
        assert from_db is not None
        assert from_db.external_account_id == "persist@example.com"


# ===================================================================
# _get_valid_credential
# ===================================================================


class TestGetValidCredential:
    async def test_returns_valid_credential(self, db_session: AsyncSession) -> None:
        user: User = await _seed_user(db_session, email="val@example.com")
        cred: OAuthCredential = await _seed_credential(db_session, user.id, email="val@example.com")

        svc: OAuthService = _build_service(db_session)
        found: OAuthCredential | None = await svc._get_valid_credential(
            user.id, external_account_id="val@example.com",
        )

        assert found is not None
        assert found.id == cred.id

    async def test_returns_none_for_invalid_credential(self, db_session: AsyncSession) -> None:
        user: User = await _seed_user(db_session, email="inv@example.com")
        await _seed_credential(db_session, user.id, email="inv@example.com", is_valid=False)

        svc: OAuthService = _build_service(db_session)
        found: OAuthCredential | None = await svc._get_valid_credential(
            user.id, external_account_id="inv@example.com",
        )

        assert found is None

    async def test_returns_none_for_nonexistent_user(self, db_session: AsyncSession) -> None:
        svc: OAuthService = _build_service(db_session)

        found: OAuthCredential | None = await svc._get_valid_credential(
            uuid.uuid4(), external_account_id="nope@example.com",
        )

        assert found is None

    async def test_finds_without_external_account_id(self, db_session: AsyncSession) -> None:
        user: User = await _seed_user(db_session, email="any@example.com")
        cred: OAuthCredential = await _seed_credential(db_session, user.id, email="any@example.com")

        svc: OAuthService = _build_service(db_session)
        found: OAuthCredential | None = await svc._get_valid_credential(user.id)

        assert found is not None
        assert found.id == cred.id
