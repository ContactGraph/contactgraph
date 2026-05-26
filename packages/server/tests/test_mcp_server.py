"""Unit tests for contactsafe_server.mcp.server module.

Tests the module-level helpers and the tool functions by mocking
the MCP context/lifespan — no real MCP server or Postgres needed.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest

from mcp.server.transport_security import TransportSecuritySettings

from contactsafe_core.enums import SourceType
from contactsafe_core.query_plan import QueryPlan
from contactsafe_core.schemas import (
    ConnectSourceResult,
    DescribeGraphResult,
    ListSourcesResult,
    PersonMatch,
    QueryNetworkResult,
    SourceStatusResult,
    SyncSourceResult,
)
from contactsafe_server.mcp.server import (
    McpLifespanState,
    _get_user_id_from_ctx,
    _require_lifespan,
    _resolve_authenticated_user_id,
    create_mcp_server,
)


# ---------------------------------------------------------------------------
# Fixtures & helpers
# ---------------------------------------------------------------------------


def _make_app_context(
    *,
    base_url: str = "http://testserver",
) -> MagicMock:
    """Build a mock AppContext with an async session factory context manager."""
    app_ctx: MagicMock = MagicMock()
    app_ctx.settings.base_url = base_url

    db_session: AsyncMock = AsyncMock()
    db_session.commit = AsyncMock()

    @asynccontextmanager
    async def _session_factory():  # type: ignore[no-untyped-def]
        yield db_session

    app_ctx.session_factory = _session_factory
    app_ctx._db_session = db_session
    return app_ctx


def _make_lifespan(app_ctx: MagicMock | None = None) -> McpLifespanState:
    """Build a real McpLifespanState with a mocked AppContext."""
    if app_ctx is None:
        app_ctx = _make_app_context()
    return McpLifespanState(app_context=app_ctx)


def _make_ctx(
    user_id: UUID | None = None,
    lifespan: McpLifespanState | None = None,
) -> MagicMock:
    """Build a mock MCP Context object."""
    ctx: MagicMock = MagicMock()
    request: MagicMock = MagicMock()
    if user_id is not None:
        request.state.user_id = str(user_id)
    else:
        request.state = MagicMock(spec=[])
    ctx.request_context.request = request
    ctx.request_context.lifespan_context = lifespan
    return ctx


# ---------------------------------------------------------------------------
# _require_lifespan
# ---------------------------------------------------------------------------


class TestRequireLifespan:
    def test_raises_when_ctx_is_none(self) -> None:
        with pytest.raises(RuntimeError, match="MCP Context is required"):
            _require_lifespan(None)

    def test_raises_when_lifespan_not_initialized(self) -> None:
        ctx: MagicMock = _make_ctx(lifespan=None)
        ctx.request_context.lifespan_context = "not-a-lifespan"
        with pytest.raises(RuntimeError, match="lifespan context not initialized"):
            _require_lifespan(ctx)

    def test_raises_when_lifespan_is_none_value(self) -> None:
        ctx: MagicMock = _make_ctx(lifespan=None)
        ctx.request_context.lifespan_context = None
        with pytest.raises(RuntimeError, match="lifespan context not initialized"):
            _require_lifespan(ctx)

    def test_returns_lifespan_when_valid(self) -> None:
        lifespan: McpLifespanState = _make_lifespan()
        ctx: MagicMock = _make_ctx(lifespan=lifespan)
        result: McpLifespanState = _require_lifespan(ctx)
        assert result is lifespan


# ---------------------------------------------------------------------------
# _get_user_id_from_ctx
# ---------------------------------------------------------------------------


class TestGetUserIdFromCtx:
    def test_returns_none_when_request_is_none(self) -> None:
        ctx: MagicMock = MagicMock()
        ctx.request_context.request = None
        result: UUID | None = _get_user_id_from_ctx(ctx)
        assert result is None

    def test_returns_none_when_no_user_id_attr(self) -> None:
        ctx: MagicMock = _make_ctx(user_id=None)
        result: UUID | None = _get_user_id_from_ctx(ctx)
        assert result is None

    def test_extracts_uuid_when_present(self) -> None:
        uid: UUID = uuid4()
        ctx: MagicMock = _make_ctx(user_id=uid)
        result: UUID | None = _get_user_id_from_ctx(ctx)
        assert result == uid

    def test_handles_string_uuid(self) -> None:
        uid: UUID = uuid4()
        ctx: MagicMock = MagicMock()
        ctx.request_context.request.state.user_id = str(uid)
        result: UUID | None = _get_user_id_from_ctx(ctx)
        assert result == uid


# ---------------------------------------------------------------------------
# _resolve_authenticated_user_id
# ---------------------------------------------------------------------------


class TestResolveAuthenticatedUserId:
    @pytest.mark.asyncio
    async def test_returns_user_from_ctx(self) -> None:
        uid: UUID = uuid4()
        ctx: MagicMock = _make_ctx(user_id=uid)
        oauth: AsyncMock = AsyncMock()

        result_id: UUID | None
        from_session: bool
        result_id, from_session = await _resolve_authenticated_user_id(ctx, None, oauth)

        assert result_id == uid
        assert from_session is False

    @pytest.mark.asyncio
    async def test_returns_user_from_session(self) -> None:
        session_id: UUID = uuid4()
        user_id: UUID = uuid4()
        ctx: MagicMock = _make_ctx(user_id=None)

        session_mock: MagicMock = MagicMock()
        session_mock.user_id = user_id

        oauth: AsyncMock = AsyncMock()
        oauth.get_session_by_id = AsyncMock(return_value=session_mock)

        result_id: UUID | None
        from_session: bool
        result_id, from_session = await _resolve_authenticated_user_id(
            ctx, str(session_id), oauth
        )

        assert result_id == user_id
        assert from_session is True
        oauth.get_session_by_id.assert_called_once_with(session_id)

    @pytest.mark.asyncio
    async def test_returns_none_when_no_auth(self) -> None:
        ctx: MagicMock = _make_ctx(user_id=None)
        oauth: AsyncMock = AsyncMock()

        result_id: UUID | None
        from_session: bool
        result_id, from_session = await _resolve_authenticated_user_id(ctx, None, oauth)

        assert result_id is None
        assert from_session is False

    @pytest.mark.asyncio
    async def test_returns_none_when_ctx_is_none_and_no_session(self) -> None:
        oauth: AsyncMock = AsyncMock()

        result_id: UUID | None
        from_session: bool
        result_id, from_session = await _resolve_authenticated_user_id(None, None, oauth)

        assert result_id is None
        assert from_session is False

    @pytest.mark.asyncio
    async def test_returns_none_when_session_has_no_user(self) -> None:
        session_id: UUID = uuid4()
        ctx: MagicMock = _make_ctx(user_id=None)

        session_mock: MagicMock = MagicMock()
        session_mock.user_id = None

        oauth: AsyncMock = AsyncMock()
        oauth.get_session_by_id = AsyncMock(return_value=session_mock)

        result_id: UUID | None
        from_session: bool
        result_id, from_session = await _resolve_authenticated_user_id(
            ctx, str(session_id), oauth
        )

        assert result_id is None
        assert from_session is False

    @pytest.mark.asyncio
    async def test_returns_none_when_session_not_found(self) -> None:
        session_id: UUID = uuid4()
        ctx: MagicMock = _make_ctx(user_id=None)

        oauth: AsyncMock = AsyncMock()
        oauth.get_session_by_id = AsyncMock(return_value=None)

        result_id: UUID | None
        from_session: bool
        result_id, from_session = await _resolve_authenticated_user_id(
            ctx, str(session_id), oauth
        )

        assert result_id is None
        assert from_session is False


# ---------------------------------------------------------------------------
# create_mcp_server — verify it returns a FastMCP with registered tools
# ---------------------------------------------------------------------------


class TestCreateMcpServer:
    def test_creates_server_with_expected_tools(self) -> None:
        settings: MagicMock = MagicMock()
        settings.mcp_transport_security = TransportSecuritySettings(
            enable_dns_rebinding_protection=False
        )
        mcp = create_mcp_server(settings)
        assert mcp.name == "ContactGraph"


# ---------------------------------------------------------------------------
# Tool function tests (via invoking them through the server's tool registry)
# ---------------------------------------------------------------------------


def _get_tool_fn(mcp: Any, name: str) -> Any:
    """Extract a registered tool function from the FastMCP server."""
    tools: dict[str, Any] = mcp._tool_manager._tools
    tool_obj: Any = tools[name]
    return tool_obj.fn


def _build_mcp_and_lifespan() -> tuple[Any, McpLifespanState, MagicMock]:
    """Create a test MCP server and return (mcp, lifespan, app_ctx)."""
    settings: MagicMock = MagicMock()
    settings.mcp_transport_security = TransportSecuritySettings(
        enable_dns_rebinding_protection=False
    )
    settings.base_url = "http://testserver"
    mcp = create_mcp_server(settings)
    app_ctx: MagicMock = _make_app_context()
    lifespan: McpLifespanState = _make_lifespan(app_ctx)
    return mcp, lifespan, app_ctx


# ---------------------------------------------------------------------------
# connect_source tool
# ---------------------------------------------------------------------------


class TestConnectSourceTool:
    @pytest.mark.asyncio
    @patch("contactsafe_server.mcp.server.build_oauth_service")
    async def test_calls_create_connect_session(
        self, mock_build_oauth: MagicMock
    ) -> None:
        mcp, lifespan, app_ctx = _build_mcp_and_lifespan()
        connect_source_fn = _get_tool_fn(mcp, "connect_source")

        session_id: UUID = uuid4()
        expected_result: ConnectSourceResult = ConnectSourceResult(
            connect_session_id=session_id,
            oauth_url="http://testserver/oauth/start",
            status="pending",  # type: ignore[arg-type]
            message="Connect via OAuth",
            already_connected=False,
        )
        mock_oauth: AsyncMock = AsyncMock()
        mock_oauth.create_connect_session = AsyncMock(return_value=expected_result)
        mock_build_oauth.return_value = mock_oauth

        ctx: MagicMock = _make_ctx(user_id=None, lifespan=lifespan)
        result: ConnectSourceResult = await connect_source_fn(
            source_type="google_mail", user_token=None, ctx=ctx
        )

        assert result.connect_session_id == session_id
        assert result.already_connected is False
        mock_oauth.create_connect_session.assert_called_once()

    @pytest.mark.asyncio
    async def test_raises_on_unknown_source_type(self) -> None:
        mcp, lifespan, _app_ctx = _build_mcp_and_lifespan()
        connect_source_fn = _get_tool_fn(mcp, "connect_source")
        ctx: MagicMock = _make_ctx(user_id=None, lifespan=lifespan)

        with pytest.raises(ValueError, match="Unknown source_type"):
            await connect_source_fn(
                source_type="invalid_source", user_token=None, ctx=ctx
            )

    @pytest.mark.asyncio
    @patch("contactsafe_server.mcp.server.build_oauth_server_service")
    @patch("contactsafe_server.mcp.server.build_source_service")
    @patch("contactsafe_server.mcp.server.build_oauth_service")
    async def test_mints_tokens_when_already_connected(
        self,
        mock_build_oauth: MagicMock,
        mock_build_source: MagicMock,
        mock_build_oauth_server: MagicMock,
    ) -> None:
        mcp, lifespan, app_ctx = _build_mcp_and_lifespan()
        connect_source_fn = _get_tool_fn(mcp, "connect_source")

        source_id: UUID = uuid4()
        user_id: UUID = uuid4()

        connect_result: ConnectSourceResult = ConnectSourceResult(
            connect_session_id=uuid4(),
            oauth_url="http://testserver/oauth/start",
            status="pending",  # type: ignore[arg-type]
            message="Already connected",
            already_connected=True,
            source_id=source_id,
        )
        mock_oauth: AsyncMock = AsyncMock()
        mock_oauth.create_connect_session = AsyncMock(return_value=connect_result)
        mock_build_oauth.return_value = mock_oauth

        mock_sources: AsyncMock = AsyncMock()
        mock_sources.resolve_user_id = AsyncMock(return_value=user_id)
        mock_build_source.return_value = mock_sources

        token_response: MagicMock = MagicMock()
        token_response.access_token = "access-tok"
        token_response.refresh_token = "refresh-tok"
        mock_oauth_server: AsyncMock = AsyncMock()
        mock_oauth_server.mint_tokens_for_user = AsyncMock(return_value=token_response)
        mock_build_oauth_server.return_value = mock_oauth_server

        ctx: MagicMock = _make_ctx(user_id=None, lifespan=lifespan)
        result: ConnectSourceResult = await connect_source_fn(
            source_type="google_mail", user_token=None, ctx=ctx
        )

        assert result.access_token == "access-tok"
        assert result.refresh_token == "refresh-tok"
        mock_sources.resolve_user_id.assert_called_once_with(source_id=source_id)
        mock_oauth_server.mint_tokens_for_user.assert_called_once_with(user_id)

    @pytest.mark.asyncio
    @patch("contactsafe_server.mcp.server.build_oauth_service")
    async def test_passes_authenticated_user_id(
        self, mock_build_oauth: MagicMock
    ) -> None:
        mcp, lifespan, _app_ctx = _build_mcp_and_lifespan()
        connect_source_fn = _get_tool_fn(mcp, "connect_source")

        user_id: UUID = uuid4()
        expected_result: ConnectSourceResult = ConnectSourceResult(
            connect_session_id=uuid4(),
            oauth_url="http://testserver/oauth/start",
            status="pending",  # type: ignore[arg-type]
            message="Connect",
            already_connected=False,
        )
        mock_oauth: AsyncMock = AsyncMock()
        mock_oauth.create_connect_session = AsyncMock(return_value=expected_result)
        mock_build_oauth.return_value = mock_oauth

        ctx: MagicMock = _make_ctx(user_id=user_id, lifespan=lifespan)
        await connect_source_fn(source_type="google_contacts", user_token=None, ctx=ctx)

        call_kwargs: dict[str, Any] = mock_oauth.create_connect_session.call_args.kwargs
        assert call_kwargs["authenticated_user_id"] == user_id
        assert call_kwargs["source_type"] == SourceType.GOOGLE_CONTACTS


# ---------------------------------------------------------------------------
# list_sources tool
# ---------------------------------------------------------------------------


class TestListSourcesTool:
    @pytest.mark.asyncio
    @patch("contactsafe_server.mcp.server._resolve_authenticated_user_id")
    @patch("contactsafe_server.mcp.server.build_oauth_service")
    async def test_returns_auth_message_when_no_user(
        self,
        mock_build_oauth: MagicMock,
        mock_resolve: AsyncMock,
    ) -> None:
        mcp, lifespan, _app_ctx = _build_mcp_and_lifespan()
        list_sources_fn = _get_tool_fn(mcp, "list_sources")

        mock_resolve.return_value = (None, False)
        mock_build_oauth.return_value = AsyncMock()

        ctx: MagicMock = _make_ctx(user_id=None, lifespan=lifespan)
        result: ListSourcesResult = await list_sources_fn(ctx=ctx)

        assert result.sources == []
        assert "Authentication required" in result.message

    @pytest.mark.asyncio
    @patch("contactsafe_server.mcp.server.build_source_service")
    @patch("contactsafe_server.mcp.server._resolve_authenticated_user_id")
    @patch("contactsafe_server.mcp.server.build_oauth_service")
    async def test_returns_sources_for_authenticated_user(
        self,
        mock_build_oauth: MagicMock,
        mock_resolve: AsyncMock,
        mock_build_source: MagicMock,
    ) -> None:
        mcp, lifespan, _app_ctx = _build_mcp_and_lifespan()
        list_sources_fn = _get_tool_fn(mcp, "list_sources")

        user_id: UUID = uuid4()
        mock_resolve.return_value = (user_id, False)
        mock_build_oauth.return_value = AsyncMock()

        expected: ListSourcesResult = ListSourcesResult(sources=[], message="OK")
        mock_sources: AsyncMock = AsyncMock()
        mock_sources.list_sources_for_user = AsyncMock(return_value=expected)
        mock_build_source.return_value = mock_sources

        ctx: MagicMock = _make_ctx(user_id=user_id, lifespan=lifespan)
        result: ListSourcesResult = await list_sources_fn(ctx=ctx)

        assert result is expected
        mock_sources.list_sources_for_user.assert_called_once_with(user_id)


# ---------------------------------------------------------------------------
# get_source_status tool
# ---------------------------------------------------------------------------


class TestGetSourceStatusTool:
    @pytest.mark.asyncio
    @patch("contactsafe_server.mcp.server.parse_source_id")
    @patch("contactsafe_server.mcp.server.build_source_service")
    @patch("contactsafe_server.mcp.server._resolve_authenticated_user_id")
    @patch("contactsafe_server.mcp.server.build_oauth_service")
    async def test_with_source_id(
        self,
        mock_build_oauth: MagicMock,
        mock_resolve: AsyncMock,
        mock_build_source: MagicMock,
        mock_parse: MagicMock,
    ) -> None:
        mcp, lifespan, _app_ctx = _build_mcp_and_lifespan()
        fn = _get_tool_fn(mcp, "get_source_status")

        source_uuid: UUID = uuid4()
        mock_parse.return_value = source_uuid
        mock_resolve.return_value = (None, False)
        mock_build_oauth.return_value = AsyncMock()

        status_result: MagicMock = MagicMock(spec=SourceStatusResult)
        mock_sources: AsyncMock = AsyncMock()
        mock_sources.get_source_status = AsyncMock(return_value=status_result)
        mock_build_source.return_value = mock_sources

        ctx: MagicMock = _make_ctx(user_id=None, lifespan=lifespan)
        result = await fn(source_id=str(source_uuid), ctx=ctx)

        assert result is status_result
        mock_sources.get_source_status.assert_called_once_with(source_uuid)

    @pytest.mark.asyncio
    @patch("contactsafe_server.mcp.server.build_source_service")
    @patch("contactsafe_server.mcp.server._resolve_authenticated_user_id")
    @patch("contactsafe_server.mcp.server.build_oauth_service")
    async def test_with_user_id(
        self,
        mock_build_oauth: MagicMock,
        mock_resolve: AsyncMock,
        mock_build_source: MagicMock,
    ) -> None:
        mcp, lifespan, _app_ctx = _build_mcp_and_lifespan()
        fn = _get_tool_fn(mcp, "get_source_status")

        user_id: UUID = uuid4()
        mock_resolve.return_value = (user_id, False)
        mock_build_oauth.return_value = AsyncMock()

        status_result: MagicMock = MagicMock(spec=SourceStatusResult)
        mock_sources: AsyncMock = AsyncMock()
        mock_sources.get_source_status_for_user = AsyncMock(return_value=status_result)
        mock_build_source.return_value = mock_sources

        ctx: MagicMock = _make_ctx(user_id=user_id, lifespan=lifespan)
        result = await fn(source_id=None, ctx=ctx)

        assert result is status_result
        mock_sources.get_source_status_for_user.assert_called_once_with(user_id)

    @pytest.mark.asyncio
    @patch("contactsafe_server.mcp.server.build_source_service")
    @patch("contactsafe_server.mcp.server._resolve_authenticated_user_id")
    @patch("contactsafe_server.mcp.server.build_oauth_service")
    async def test_raises_when_no_source_id_or_user(
        self,
        mock_build_oauth: MagicMock,
        mock_resolve: AsyncMock,
        mock_build_source: MagicMock,
    ) -> None:
        mcp, lifespan, _app_ctx = _build_mcp_and_lifespan()
        fn = _get_tool_fn(mcp, "get_source_status")

        mock_resolve.return_value = (None, False)
        mock_build_oauth.return_value = AsyncMock()
        mock_build_source.return_value = AsyncMock()

        ctx: MagicMock = _make_ctx(user_id=None, lifespan=lifespan)
        with pytest.raises(ValueError, match="Authentication required"):
            await fn(source_id=None, ctx=ctx)


# ---------------------------------------------------------------------------
# sync_source tool
# ---------------------------------------------------------------------------


class TestSyncSourceTool:
    @pytest.mark.asyncio
    @patch("contactsafe_server.mcp.server.parse_source_id")
    @patch("contactsafe_server.mcp.server.build_source_service")
    @patch("contactsafe_server.mcp.server._resolve_authenticated_user_id")
    @patch("contactsafe_server.mcp.server.build_oauth_service")
    async def test_with_source_id_calls_request_sync(
        self,
        mock_build_oauth: MagicMock,
        mock_resolve: AsyncMock,
        mock_build_source: MagicMock,
        mock_parse: MagicMock,
    ) -> None:
        mcp, lifespan, _app_ctx = _build_mcp_and_lifespan()
        fn = _get_tool_fn(mcp, "sync_source")

        source_uuid: UUID = uuid4()
        mock_parse.return_value = source_uuid
        mock_resolve.return_value = (None, False)
        mock_build_oauth.return_value = AsyncMock()

        sync_result: MagicMock = MagicMock(spec=SyncSourceResult)
        mock_sources: AsyncMock = AsyncMock()
        mock_sources.request_sync = AsyncMock(return_value=sync_result)
        mock_build_source.return_value = mock_sources

        ctx: MagicMock = _make_ctx(user_id=None, lifespan=lifespan)
        result = await fn(source_id=str(source_uuid), ctx=ctx)

        assert result is sync_result
        mock_sources.request_sync.assert_called_once_with(source_uuid)

    @pytest.mark.asyncio
    @patch("contactsafe_server.mcp.server.build_source_service")
    @patch("contactsafe_server.mcp.server._resolve_authenticated_user_id")
    @patch("contactsafe_server.mcp.server.build_oauth_service")
    async def test_without_source_id_calls_request_sync_for_user(
        self,
        mock_build_oauth: MagicMock,
        mock_resolve: AsyncMock,
        mock_build_source: MagicMock,
    ) -> None:
        mcp, lifespan, _app_ctx = _build_mcp_and_lifespan()
        fn = _get_tool_fn(mcp, "sync_source")

        user_id: UUID = uuid4()
        mock_resolve.return_value = (user_id, False)
        mock_build_oauth.return_value = AsyncMock()

        sync_result: MagicMock = MagicMock(spec=SyncSourceResult)
        mock_sources: AsyncMock = AsyncMock()
        mock_sources.request_sync_for_user = AsyncMock(return_value=sync_result)
        mock_build_source.return_value = mock_sources

        ctx: MagicMock = _make_ctx(user_id=user_id, lifespan=lifespan)
        result = await fn(source_id=None, ctx=ctx)

        assert result is sync_result
        mock_sources.request_sync_for_user.assert_called_once_with(user_id)

    @pytest.mark.asyncio
    @patch("contactsafe_server.mcp.server.build_source_service")
    @patch("contactsafe_server.mcp.server._resolve_authenticated_user_id")
    @patch("contactsafe_server.mcp.server.build_oauth_service")
    async def test_raises_when_no_auth(
        self,
        mock_build_oauth: MagicMock,
        mock_resolve: AsyncMock,
        mock_build_source: MagicMock,
    ) -> None:
        mcp, lifespan, _app_ctx = _build_mcp_and_lifespan()
        fn = _get_tool_fn(mcp, "sync_source")

        mock_resolve.return_value = (None, False)
        mock_build_oauth.return_value = AsyncMock()
        mock_build_source.return_value = AsyncMock()

        ctx: MagicMock = _make_ctx(user_id=None, lifespan=lifespan)
        with pytest.raises(ValueError, match="Authentication required"):
            await fn(source_id=None, ctx=ctx)


# ---------------------------------------------------------------------------
# query_network tool
# ---------------------------------------------------------------------------


class TestQueryNetworkTool:
    @pytest.mark.asyncio
    @patch("contactsafe_server.mcp.server._resolve_authenticated_user_id")
    @patch("contactsafe_server.mcp.server.build_oauth_service")
    async def test_no_auth_returns_message(
        self,
        mock_build_oauth: MagicMock,
        mock_resolve: AsyncMock,
    ) -> None:
        mcp, lifespan, _app_ctx = _build_mcp_and_lifespan()
        fn = _get_tool_fn(mcp, "query_network")

        mock_resolve.return_value = (None, False)
        mock_build_oauth.return_value = AsyncMock()

        ctx: MagicMock = _make_ctx(user_id=None, lifespan=lifespan)
        result: QueryNetworkResult = await fn(question="who do I know?", ctx=ctx)

        assert "Authentication required" in result.message
        assert result.question == "who do I know?"

    @pytest.mark.asyncio
    @patch("contactsafe_server.mcp.server.build_source_service")
    @patch("contactsafe_server.mcp.server._resolve_authenticated_user_id")
    @patch("contactsafe_server.mcp.server.build_oauth_service")
    async def test_no_queryable_graph_returns_sync_message(
        self,
        mock_build_oauth: MagicMock,
        mock_resolve: AsyncMock,
        mock_build_source: MagicMock,
    ) -> None:
        mcp, lifespan, _app_ctx = _build_mcp_and_lifespan()
        fn = _get_tool_fn(mcp, "query_network")

        user_id: UUID = uuid4()
        mock_resolve.return_value = (user_id, False)
        mock_build_oauth.return_value = AsyncMock()

        mock_sources: AsyncMock = AsyncMock()
        mock_sources.user_has_queryable_graph = AsyncMock(return_value=False)
        mock_build_source.return_value = mock_sources

        ctx: MagicMock = _make_ctx(user_id=user_id, lifespan=lifespan)
        result: QueryNetworkResult = await fn(question="find VCs", ctx=ctx)

        assert "Sync still running" in result.message

    @pytest.mark.asyncio
    @patch("contactsafe_server.mcp.server.NetworkQueryService")
    @patch("contactsafe_server.mcp.server.QueryPlanner")
    @patch("contactsafe_server.mcp.server.build_source_service")
    @patch("contactsafe_server.mcp.server._resolve_authenticated_user_id")
    @patch("contactsafe_server.mcp.server.build_oauth_service")
    async def test_plans_and_executes_query(
        self,
        mock_build_oauth: MagicMock,
        mock_resolve: AsyncMock,
        mock_build_source: MagicMock,
        mock_planner_cls: MagicMock,
        mock_executor_cls: MagicMock,
    ) -> None:
        mcp, lifespan, app_ctx = _build_mcp_and_lifespan()
        fn = _get_tool_fn(mcp, "query_network")

        user_id: UUID = uuid4()
        mock_resolve.return_value = (user_id, False)
        mock_build_oauth.return_value = AsyncMock()

        mock_sources: AsyncMock = AsyncMock()
        mock_sources.user_has_queryable_graph = AsyncMock(return_value=True)
        mock_build_source.return_value = mock_sources

        plan: QueryPlan = QueryPlan(name_tokens=["alice"])
        mock_planner: AsyncMock = AsyncMock()
        mock_planner.plan = AsyncMock(return_value=plan)
        mock_planner_cls.return_value = mock_planner

        matches: list[PersonMatch] = [
            PersonMatch(
                person_id=uuid4(),
                name="Alice Smith",
                emails=["alice@example.com"],
            )
        ]
        mock_executor: AsyncMock = AsyncMock()
        mock_executor.execute = AsyncMock(return_value=matches)
        mock_executor_cls.return_value = mock_executor

        ctx: MagicMock = _make_ctx(user_id=user_id, lifespan=lifespan)
        result: QueryNetworkResult = await fn(question="find alice", ctx=ctx)

        assert len(result.matches) == 1
        assert result.matches[0].name == "Alice Smith"
        assert result.applied_plan == plan
        assert "1 matching contact" in result.message

    @pytest.mark.asyncio
    @patch("contactsafe_server.mcp.server.NetworkQueryService")
    @patch("contactsafe_server.mcp.server.QueryPlanner")
    @patch("contactsafe_server.mcp.server.build_source_service")
    @patch("contactsafe_server.mcp.server._resolve_authenticated_user_id")
    @patch("contactsafe_server.mcp.server.build_oauth_service")
    async def test_empty_results_with_filters(
        self,
        mock_build_oauth: MagicMock,
        mock_resolve: AsyncMock,
        mock_build_source: MagicMock,
        mock_planner_cls: MagicMock,
        mock_executor_cls: MagicMock,
    ) -> None:
        mcp, lifespan, _app_ctx = _build_mcp_and_lifespan()
        fn = _get_tool_fn(mcp, "query_network")

        user_id: UUID = uuid4()
        mock_resolve.return_value = (user_id, False)
        mock_build_oauth.return_value = AsyncMock()

        mock_sources: AsyncMock = AsyncMock()
        mock_sources.user_has_queryable_graph = AsyncMock(return_value=True)
        mock_build_source.return_value = mock_sources

        plan: QueryPlan = QueryPlan(org_names=["Acme Corp"])
        mock_planner: AsyncMock = AsyncMock()
        mock_planner.plan = AsyncMock(return_value=plan)
        mock_planner_cls.return_value = mock_planner

        mock_executor: AsyncMock = AsyncMock()
        mock_executor.execute = AsyncMock(return_value=[])
        mock_executor_cls.return_value = mock_executor

        ctx: MagicMock = _make_ctx(user_id=user_id, lifespan=lifespan)
        result: QueryNetworkResult = await fn(question="who works at Acme?", ctx=ctx)

        assert result.matches == []
        assert "No matching contacts" in result.message

    @pytest.mark.asyncio
    @patch("contactsafe_server.mcp.server.NetworkQueryService")
    @patch("contactsafe_server.mcp.server.QueryPlanner")
    @patch("contactsafe_server.mcp.server.build_source_service")
    @patch("contactsafe_server.mcp.server._resolve_authenticated_user_id")
    @patch("contactsafe_server.mcp.server.build_oauth_service")
    async def test_empty_results_without_filters(
        self,
        mock_build_oauth: MagicMock,
        mock_resolve: AsyncMock,
        mock_build_source: MagicMock,
        mock_planner_cls: MagicMock,
        mock_executor_cls: MagicMock,
    ) -> None:
        mcp, lifespan, _app_ctx = _build_mcp_and_lifespan()
        fn = _get_tool_fn(mcp, "query_network")

        user_id: UUID = uuid4()
        mock_resolve.return_value = (user_id, False)
        mock_build_oauth.return_value = AsyncMock()

        mock_sources: AsyncMock = AsyncMock()
        mock_sources.user_has_queryable_graph = AsyncMock(return_value=True)
        mock_build_source.return_value = mock_sources

        plan: QueryPlan = QueryPlan()
        mock_planner: AsyncMock = AsyncMock()
        mock_planner.plan = AsyncMock(return_value=plan)
        mock_planner_cls.return_value = mock_planner

        mock_executor: AsyncMock = AsyncMock()
        mock_executor.execute = AsyncMock(return_value=[])
        mock_executor_cls.return_value = mock_executor

        ctx: MagicMock = _make_ctx(user_id=user_id, lifespan=lifespan)
        result: QueryNetworkResult = await fn(question="blah", ctx=ctx)

        assert result.matches == []
        assert "Could not translate" in result.message


# ---------------------------------------------------------------------------
# describe_graph tool
# ---------------------------------------------------------------------------


class TestDescribeGraphTool:
    @pytest.mark.asyncio
    @patch("contactsafe_server.mcp.server._resolve_authenticated_user_id")
    @patch("contactsafe_server.mcp.server.build_oauth_service")
    async def test_no_auth_returns_message(
        self,
        mock_build_oauth: MagicMock,
        mock_resolve: AsyncMock,
    ) -> None:
        mcp, lifespan, _app_ctx = _build_mcp_and_lifespan()
        fn = _get_tool_fn(mcp, "describe_graph")

        mock_resolve.return_value = (None, False)
        mock_build_oauth.return_value = AsyncMock()

        ctx: MagicMock = _make_ctx(user_id=None, lifespan=lifespan)
        result: DescribeGraphResult = await fn(ctx=ctx)

        assert "Authentication required" in result.message

    @pytest.mark.asyncio
    @patch("contactsafe_server.mcp.server.build_source_service")
    @patch("contactsafe_server.mcp.server._resolve_authenticated_user_id")
    @patch("contactsafe_server.mcp.server.build_oauth_service")
    async def test_no_queryable_graph_returns_sync_message(
        self,
        mock_build_oauth: MagicMock,
        mock_resolve: AsyncMock,
        mock_build_source: MagicMock,
    ) -> None:
        mcp, lifespan, _app_ctx = _build_mcp_and_lifespan()
        fn = _get_tool_fn(mcp, "describe_graph")

        user_id: UUID = uuid4()
        mock_resolve.return_value = (user_id, False)
        mock_build_oauth.return_value = AsyncMock()

        mock_sources: AsyncMock = AsyncMock()
        mock_sources.user_has_queryable_graph = AsyncMock(return_value=False)
        mock_build_source.return_value = mock_sources

        ctx: MagicMock = _make_ctx(user_id=user_id, lifespan=lifespan)
        result: DescribeGraphResult = await fn(ctx=ctx)

        assert "Sync still running" in result.message

    @pytest.mark.asyncio
    @patch("contactsafe_server.mcp.server.GraphSummaryService")
    @patch("contactsafe_server.mcp.server.build_source_service")
    @patch("contactsafe_server.mcp.server._resolve_authenticated_user_id")
    @patch("contactsafe_server.mcp.server.build_oauth_service")
    async def test_returns_summary(
        self,
        mock_build_oauth: MagicMock,
        mock_resolve: AsyncMock,
        mock_build_source: MagicMock,
        mock_graph_cls: MagicMock,
    ) -> None:
        mcp, lifespan, _app_ctx = _build_mcp_and_lifespan()
        fn = _get_tool_fn(mcp, "describe_graph")

        user_id: UUID = uuid4()
        mock_resolve.return_value = (user_id, False)
        mock_build_oauth.return_value = AsyncMock()

        mock_sources: AsyncMock = AsyncMock()
        mock_sources.user_has_queryable_graph = AsyncMock(return_value=True)
        mock_build_source.return_value = mock_sources

        expected: DescribeGraphResult = DescribeGraphResult(
            total_contacts=42,
            message="Your graph has 42 contacts.",
        )
        mock_graph: AsyncMock = AsyncMock()
        mock_graph.describe = AsyncMock(return_value=expected)
        mock_graph_cls.return_value = mock_graph

        ctx: MagicMock = _make_ctx(user_id=user_id, lifespan=lifespan)
        result: DescribeGraphResult = await fn(ctx=ctx)

        assert result.total_contacts == 42
        mock_graph.describe.assert_called_once_with(user_id)
