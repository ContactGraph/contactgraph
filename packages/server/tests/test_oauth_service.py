import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from contactsafe_core.enums import SessionStatus
from contactsafe_server.config import get_settings
from contactsafe_server.oauth.google import GoogleOAuthClient
from contactsafe_server.services.crypto import TokenEncryptor
from contactsafe_server.services.oauth_service import OAuthService


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
    assert result.session_id is not None


@pytest.mark.asyncio
async def test_get_import_status_pending(db_session: AsyncSession) -> None:
    settings = get_settings()
    service = OAuthService(
        db=db_session,
        settings=settings,
        encryptor=TokenEncryptor(settings.token_encryption_key),
        google=GoogleOAuthClient(settings),
    )
    connect = await service.create_connect_session()
    await db_session.commit()

    status = await service.get_import_status(connect.session_id)
    assert status.status == SessionStatus.PENDING
    assert status.email is None


@pytest.mark.asyncio
async def test_get_import_status_unknown_session(db_session: AsyncSession) -> None:
    settings = get_settings()
    service = OAuthService(
        db=db_session,
        settings=settings,
        encryptor=TokenEncryptor(settings.token_encryption_key),
        google=GoogleOAuthClient(settings),
    )
    with pytest.raises(ValueError, match="Unknown session_id"):
        await service.get_import_status(uuid.uuid4())
