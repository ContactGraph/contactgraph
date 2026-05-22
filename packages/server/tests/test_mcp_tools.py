"""MCP tool integration tests (require Postgres)."""

import pytest

from contactsafe_core.enums import SessionStatus
from contactsafe_server.deps import build_app_context, build_oauth_service
from contactsafe_server.services.source_service import SourceService


@pytest.mark.asyncio
async def test_connect_source_returns_oauth_url(postgres_available: bool) -> None:
    if not postgres_available:
        pytest.skip("Postgres not available")

    ctx = build_app_context()
    async with ctx.session_factory() as db:
        service = build_oauth_service(db, ctx)
        result = await service.create_connect_session()
        await db.commit()

    assert result.status == SessionStatus.PENDING
    assert str(result.connect_session_id) in result.oauth_url
    assert result.oauth_url.startswith(ctx.settings.base_url)


@pytest.mark.asyncio
async def test_source_status_lifecycle(postgres_available: bool) -> None:
    if not postgres_available:
        pytest.skip("Postgres not available")

    ctx = build_app_context()
    async with ctx.session_factory() as db:
        oauth = build_oauth_service(db, ctx)
        connect = await oauth.create_connect_session()
        await db.commit()

    async with ctx.session_factory() as db:
        sources = SourceService(db)
        status = await sources.get_source_status_for_connect_session(
            connect.connect_session_id
        )

    assert status.connect_session_id == connect.connect_session_id
    assert status.status == SessionStatus.PENDING
    assert status.email is None
