import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from contactsafe_core.enums import SessionStatus, SyncState
from contactsafe_server.config import get_settings
from contactsafe_server.oauth.google import GoogleOAuthClient
from contactsafe_server.services.crypto import TokenEncryptor
from contactsafe_server.services.oauth_service import OAuthService
from contactsafe_server.services.source_service import SourceService


@pytest.mark.asyncio
async def test_create_connect_session(db_session: AsyncSession) -> None:
    settings = get_settings()
    service = OAuthService(
        db=db_session,
        settings=settings,
        encryptor=TokenEncryptor(settings.token_encryption_key),
        google=GoogleOAuthClient(settings),
    )
    result = await service.create_connect_session()
    await db_session.commit()

    assert result.status == SessionStatus.PENDING
    assert result.already_connected is False
    assert "oauth/start" in result.oauth_url
    assert result.connect_session_id is not None


@pytest.mark.asyncio
async def test_get_source_status_pending(db_session: AsyncSession) -> None:
    settings = get_settings()
    oauth = OAuthService(
        db=db_session,
        settings=settings,
        encryptor=TokenEncryptor(settings.token_encryption_key),
        google=GoogleOAuthClient(settings),
    )
    connect = await oauth.create_connect_session()
    await db_session.commit()

    sources = SourceService(db_session)
    status = await sources.get_source_status_for_connect_session(connect.connect_session_id)
    assert status.status == SessionStatus.PENDING
    assert status.sync_state == SyncState.PENDING
    assert status.email is None


@pytest.mark.asyncio
async def test_get_source_status_unknown_session(db_session: AsyncSession) -> None:
    sources = SourceService(db_session)
    with pytest.raises(ValueError, match="Unknown connect_session_id"):
        await sources.get_source_status_for_connect_session(uuid.uuid4())


@pytest.mark.asyncio
async def test_complete_oauth_requires_calendar_and_gmail_scopes(
    db_session: AsyncSession,
) -> None:
    settings = get_settings()
    service = OAuthService(
        db=db_session,
        settings=settings,
        encryptor=TokenEncryptor(settings.token_encryption_key),
        google=GoogleOAuthClient(settings),
    )

    with pytest.raises(ValueError, match="Missing required Google permissions"):
        service._validate_required_scopes(["openid", "email"])  # pyright: ignore[reportPrivateUsage]
