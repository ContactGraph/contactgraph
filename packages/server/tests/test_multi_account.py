"""Tests for multi-Gmail account support.

Covers: UserIdentity model, OAuthCredential rekeying, user resolution
in OAuthService, credential-per-source lookups, and multi-source sync.
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from contactsafe_core.enums import (
    IdentityKind,
    OAuthProvider,
    SourceConnectionStatus,
    SourceType,
    SyncState,
)
from contactsafe_server.config import get_settings
from contactsafe_server.db.models import (
    ConnectSession,
    OAuthCredential,
    Source,
    User,
    UserIdentity,
)
from contactsafe_server.services.crypto import TokenEncryptor
from contactsafe_server.services.source_service import SourceService

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _make_user(
    db: AsyncSession,
    email: str,
    *,
    with_identity: bool = True,
) -> User:
    user = User(email=email)
    db.add(user)
    await db.flush()
    if with_identity:
        identity = UserIdentity(
            user_id=user.id,
            kind=IdentityKind.EMAIL.value,
            value=email,
            is_primary=True,
            verified_at=datetime.now(tz=UTC),
        )
        db.add(identity)
        await db.flush()
    return user


async def _make_source(
    db: AsyncSession,
    user_id: uuid.UUID,
    email: str,
    *,
    source_type: str = SourceType.GOOGLE_MAIL.value,
) -> Source:
    source = Source(
        user_id=user_id,
        source_type=source_type,
        label=email,
        external_account_id=email,
        connection_status=SourceConnectionStatus.CONNECTED.value,
        sync_state=SyncState.PENDING.value,
    )
    db.add(source)
    await db.flush()
    return source


async def _make_credential(
    db: AsyncSession,
    user_id: uuid.UUID,
    external_account_id: str,
    *,
    source_id: uuid.UUID | None = None,
) -> OAuthCredential:
    encryptor = TokenEncryptor(get_settings().token_encryption_key)
    cred = OAuthCredential(
        user_id=user_id,
        source_id=source_id,
        provider=OAuthProvider.GOOGLE.value,
        external_account_id=external_account_id,
        access_token_encrypted=encryptor.encrypt("access-" + external_account_id),
        refresh_token_encrypted=encryptor.encrypt("refresh-" + external_account_id),
        token_expires_at=datetime.now(tz=UTC) + timedelta(hours=1),
        scopes=["https://www.googleapis.com/auth/gmail.readonly"],
        is_valid=True,
    )
    db.add(cred)
    await db.flush()
    return cred


# ---------------------------------------------------------------------------
# UserIdentity model tests
# ---------------------------------------------------------------------------


async def test_user_identity_created_with_user(db_session: AsyncSession) -> None:
    user = await _make_user(db_session, "alice@example.com")
    result = await db_session.execute(
        select(UserIdentity).where(UserIdentity.user_id == user.id)
    )
    identities: list[UserIdentity] = list(result.scalars().all())
    assert len(identities) == 1
    assert identities[0].kind == IdentityKind.EMAIL.value
    assert identities[0].value == "alice@example.com"
    assert identities[0].is_primary is True
    assert identities[0].verified_at is not None


async def test_multiple_identities_per_user(db_session: AsyncSession) -> None:
    user = await _make_user(db_session, "primary@example.com")
    second = UserIdentity(
        user_id=user.id,
        kind=IdentityKind.EMAIL.value,
        value="secondary@example.com",
        is_primary=False,
        verified_at=datetime.now(tz=UTC),
    )
    db_session.add(second)
    await db_session.flush()

    result = await db_session.execute(
        select(UserIdentity).where(UserIdentity.user_id == user.id)
    )
    assert len(list(result.scalars().all())) == 2


async def test_identity_unique_constraint_prevents_duplicate(
    db_session: AsyncSession,
) -> None:
    """Two users cannot claim the same (kind, value)."""
    await _make_user(db_session, "shared@example.com")
    user2 = await _make_user(db_session, "other@example.com")
    dup = UserIdentity(
        user_id=user2.id,
        kind=IdentityKind.EMAIL.value,
        value="shared@example.com",
        is_primary=False,
    )
    db_session.add(dup)
    with pytest.raises(Exception):
        await db_session.flush()
    await db_session.rollback()


async def test_identity_different_kinds_same_value(
    db_session: AsyncSession,
) -> None:
    """Same value under different kinds is allowed (e.g. phone vs email)."""
    user = await _make_user(db_session, "test@example.com")
    phone = UserIdentity(
        user_id=user.id,
        kind=IdentityKind.PHONE.value,
        value="+15551234567",
        is_primary=False,
    )
    db_session.add(phone)
    await db_session.flush()

    result = await db_session.execute(
        select(UserIdentity).where(UserIdentity.user_id == user.id)
    )
    identities: list[UserIdentity] = list(result.scalars().all())
    assert len(identities) == 2
    kinds: set[str] = {i.kind for i in identities}
    assert kinds == {IdentityKind.EMAIL.value, IdentityKind.PHONE.value}


# ---------------------------------------------------------------------------
# OAuthCredential multi-account tests
# ---------------------------------------------------------------------------


async def test_multiple_credentials_per_user(db_session: AsyncSession) -> None:
    """One user can have credentials for two different Google accounts."""
    user = await _make_user(db_session, "alice@example.com")
    cred1 = await _make_credential(db_session, user.id, "alice@example.com")
    cred2 = await _make_credential(db_session, user.id, "alice@work.com")

    assert cred1.id != cred2.id
    assert cred1.external_account_id == "alice@example.com"
    assert cred2.external_account_id == "alice@work.com"


async def test_credential_unique_constraint(db_session: AsyncSession) -> None:
    """Cannot have two credentials for the same (user, provider, account)."""
    user = await _make_user(db_session, "dup@example.com")
    await _make_credential(db_session, user.id, "dup@example.com")
    with pytest.raises(Exception):
        await _make_credential(db_session, user.id, "dup@example.com")
    await db_session.rollback()


# ---------------------------------------------------------------------------
# Credential-per-source resolution tests
# ---------------------------------------------------------------------------


async def test_get_credential_for_source_matches_by_source_id(
    db_session: AsyncSession,
) -> None:
    user = await _make_user(db_session, "cred-test@example.com")
    source = await _make_source(db_session, user.id, "cred-test@example.com")
    cred = await _make_credential(
        db_session, user.id, "cred-test@example.com", source_id=source.id,
    )

    svc = SourceService(db_session)
    found: OAuthCredential | None = await svc._get_credential_for_source(source)
    assert found is not None
    assert found.id == cred.id


async def test_get_credential_for_source_fallback_by_external_account_id(
    db_session: AsyncSession,
) -> None:
    """When credential isn't linked by source_id, match via external_account_id."""
    user = await _make_user(db_session, "fallback@example.com")
    source = await _make_source(db_session, user.id, "fallback@example.com")
    cred = await _make_credential(db_session, user.id, "fallback@example.com")

    svc = SourceService(db_session)
    found: OAuthCredential | None = await svc._get_credential_for_source(source)
    assert found is not None
    assert found.id == cred.id


async def test_get_credential_for_source_two_accounts_resolves_correctly(
    db_session: AsyncSession,
) -> None:
    """With two Google accounts, each source should get its own credential."""
    user = await _make_user(db_session, "multi@personal.com")
    src_personal = await _make_source(db_session, user.id, "multi@personal.com")
    src_work = await _make_source(db_session, user.id, "multi@work.com")
    cred_personal = await _make_credential(
        db_session, user.id, "multi@personal.com", source_id=src_personal.id,
    )
    cred_work = await _make_credential(
        db_session, user.id, "multi@work.com", source_id=src_work.id,
    )

    svc = SourceService(db_session)
    found_personal = await svc._get_credential_for_source(src_personal)
    found_work = await svc._get_credential_for_source(src_work)
    assert found_personal is not None
    assert found_work is not None
    assert found_personal.id == cred_personal.id
    assert found_work.id == cred_work.id


# ---------------------------------------------------------------------------
# Source service multi-source tests
# ---------------------------------------------------------------------------


async def test_get_default_google_mail_source_returns_oldest(
    db_session: AsyncSession,
) -> None:
    user = await _make_user(db_session, "default-src@example.com")
    first = await _make_source(db_session, user.id, "default-src@example.com")
    _second = await _make_source(db_session, user.id, "second@example.com")

    svc = SourceService(db_session)
    default: Source | None = await svc._get_default_google_mail_source(user.id)
    assert default is not None
    assert default.id == first.id


async def test_request_sync_for_user_schedules_all_sources(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """request_sync_for_user should schedule sync for every mail source."""
    user = await _make_user(db_session, "sync-all@example.com")
    src1 = await _make_source(db_session, user.id, "sync-all@example.com")
    src2 = await _make_source(db_session, user.id, "sync-all@work.com")
    await _make_credential(
        db_session, user.id, "sync-all@example.com", source_id=src1.id,
    )
    await _make_credential(
        db_session, user.id, "sync-all@work.com", source_id=src2.id,
    )

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
        lambda _: False,
    )

    svc = SourceService(db_session)
    await svc.request_sync_for_user(user.id)

    assert src1.id in scheduled_ids
    assert src2.id in scheduled_ids


# ---------------------------------------------------------------------------
# OAuthService connect session with authenticated_user_id
# ---------------------------------------------------------------------------


async def test_create_connect_session_stores_authenticated_user_id(
    db_session: AsyncSession,
) -> None:
    from contactsafe_server.oauth.google import GoogleOAuthClient
    from contactsafe_server.services.oauth_service import OAuthService

    user = await _make_user(db_session, "existing@example.com")
    settings = get_settings()
    svc = OAuthService(
        db=db_session,
        settings=settings,
        encryptor=TokenEncryptor(settings.token_encryption_key),
        google=GoogleOAuthClient(settings),
    )
    result = await svc.create_connect_session(
        authenticated_user_id=user.id,
    )
    await db_session.flush()

    session: ConnectSession | None = await svc.get_session_by_id(
        result.connect_session_id,
    )
    assert session is not None
    assert session.user_id == user.id


# ---------------------------------------------------------------------------
# OAuthService._find_user_by_email via user_identities
# ---------------------------------------------------------------------------


async def test_find_user_by_email_via_identity(db_session: AsyncSession) -> None:
    from contactsafe_server.oauth.google import GoogleOAuthClient
    from contactsafe_server.services.oauth_service import OAuthService

    user = await _make_user(db_session, "find-me@example.com")
    settings = get_settings()
    svc = OAuthService(
        db=db_session,
        settings=settings,
        encryptor=TokenEncryptor(settings.token_encryption_key),
        google=GoogleOAuthClient(settings),
    )

    found: User | None = await svc._find_user_by_email("find-me@example.com")
    assert found is not None
    assert found.id == user.id


async def test_find_user_by_email_returns_none_for_unknown(
    db_session: AsyncSession,
) -> None:
    from contactsafe_server.oauth.google import GoogleOAuthClient
    from contactsafe_server.services.oauth_service import OAuthService

    settings = get_settings()
    svc = OAuthService(
        db=db_session,
        settings=settings,
        encryptor=TokenEncryptor(settings.token_encryption_key),
        google=GoogleOAuthClient(settings),
    )
    found: User | None = await svc._find_user_by_email("nobody@example.com")
    assert found is None


async def test_find_user_by_secondary_email(db_session: AsyncSession) -> None:
    """A user can be found via a non-primary linked email."""
    from contactsafe_server.oauth.google import GoogleOAuthClient
    from contactsafe_server.services.oauth_service import OAuthService

    user = await _make_user(db_session, "primary@example.com")
    secondary = UserIdentity(
        user_id=user.id,
        kind=IdentityKind.EMAIL.value,
        value="secondary@example.com",
        is_primary=False,
        verified_at=datetime.now(tz=UTC),
    )
    db_session.add(secondary)
    await db_session.flush()

    settings = get_settings()
    svc = OAuthService(
        db=db_session,
        settings=settings,
        encryptor=TokenEncryptor(settings.token_encryption_key),
        google=GoogleOAuthClient(settings),
    )
    found: User | None = await svc._find_user_by_email("secondary@example.com")
    assert found is not None
    assert found.id == user.id
