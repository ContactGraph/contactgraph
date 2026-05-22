"""MCP tool integration tests (require Postgres)."""

import pytest

from contactsafe_core.enums import SessionStatus
from contactsafe_server.config import get_settings
from contactsafe_server.deps import build_app_context, build_oauth_service
from contactsafe_server.oauth.google import GoogleOAuthClient
from contactsafe_server.services.crypto import TokenEncryptor
from contactsafe_server.services.oauth_service import OAuthService


@pytest.mark.asyncio
async def test_connect_gmail_returns_oauth_url(postgres_available: bool) -> None:
    if not postgres_available:
        pytest.skip("Postgres not available")

    ctx = build_app_context()
    async with ctx.session_factory() as db:
        service = OAuthService(
            db=db,
            settings=ctx.settings,
            encryptor=ctx.encryptor,
            google=GoogleOAuthClient(ctx.settings),
        )
        result = await service.create_connect_session()
        await db.commit()

    assert result.status == SessionStatus.PENDING
    assert str(result.session_id) in result.oauth_url
    assert result.oauth_url.startswith(ctx.settings.base_url)


@pytest.mark.asyncio
async def test_import_status_lifecycle(postgres_available: bool) -> None:
    if not postgres_available:
        pytest.skip("Postgres not available")

    settings = get_settings()
    ctx = build_app_context()
    async with ctx.session_factory() as db:
        service = build_oauth_service(db, ctx)
        connect = await service.create_connect_session()
        await db.commit()

    async with ctx.session_factory() as db:
        service = build_oauth_service(db, ctx)
        status = await service.get_import_status(connect.session_id)

    assert status.session_id == connect.session_id
    assert status.status == SessionStatus.PENDING
    assert status.email is None
