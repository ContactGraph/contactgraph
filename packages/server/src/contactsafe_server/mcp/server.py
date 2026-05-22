from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any

from mcp.server.fastmcp import Context, FastMCP

from contactsafe_core.enums import SessionStatus, SourceConnectionStatus, SourceType
from contactsafe_core.schemas import (
    ConnectSourceResult,
    ListSourcesResult,
    PersonMatch,
    QueryNetworkResult,
    SourceStatusResult,
    SyncSourceResult,
)
from contactsafe_server.deps import (
    AppContext,
    build_app_context,
    build_oauth_service,
    build_source_service,
)
from contactsafe_server.services.network_query_service import NetworkQueryService
from contactsafe_server.services.query_planner import QueryPlanner
from contactsafe_server.services.oauth_service import OAuthService
from contactsafe_server.services.source_service import SourceService
from contactsafe_server.utils import parse_connect_session_id, parse_source_id


@dataclass(frozen=True, slots=True)
class McpLifespanState:
    app_context: AppContext


@asynccontextmanager
async def _mcp_lifespan(_server: FastMCP) -> AsyncGenerator[McpLifespanState, None]:
    ctx: AppContext = build_app_context()
    yield McpLifespanState(app_context=ctx)


def create_mcp_server() -> FastMCP:
    mcp: FastMCP = FastMCP(
        "ContactSafe",
        instructions=(
            "ContactSafe builds a private contact graph from connected data sources. "
            "Use connect_source to start OAuth, list_sources to see connections, "
            "sync_source to (re)start ingestion, get_source_status for progress, "
            "and query_network to search contacts."
        ),
        json_response=True,
        stateless_http=True,
        lifespan=_mcp_lifespan,
    )

    @mcp.tool()  # pyright: ignore[reportUnusedFunction]
    async def connect_source(
        source_type: str = SourceType.GOOGLE_MAIL.value,
        user_token: str | None = None,
        ctx: Context[Any, Any, Any] | None = None,
    ) -> ConnectSourceResult:
        """Connect a data source (google_mail supported today).

        Returns connect_session_id and oauth_url when browser authorization is needed.
        """
        lifespan: McpLifespanState = _require_lifespan(ctx)
        try:
            parsed_type: SourceType = SourceType(source_type)
        except ValueError as exc:
            raise ValueError(f"Unknown source_type: {source_type}") from exc

        async with lifespan.app_context.session_factory() as db:
            oauth: OAuthService = build_oauth_service(db, lifespan.app_context)
            result: ConnectSourceResult = await oauth.create_connect_session(
                user_token,
                source_type=parsed_type,
            )
            await db.commit()
            return result

    @mcp.tool()  # pyright: ignore[reportUnusedFunction]
    async def list_sources(
        connect_session_id: str,
        ctx: Context[Any, Any, Any] | None = None,
    ) -> ListSourcesResult:
        """List connected data sources for the user linked to a connect session."""
        lifespan: McpLifespanState = _require_lifespan(ctx)
        session_uuid = parse_connect_session_id(connect_session_id)
        async with lifespan.app_context.session_factory() as db:
            oauth: OAuthService = build_oauth_service(db, lifespan.app_context)
            session = await oauth.get_session_by_id(session_uuid)
            if session is None or session.user_id is None:
                return ListSourcesResult(
                    sources=[],
                    message="Unknown session or OAuth not completed yet.",
                )
            sources: SourceService = build_source_service(db)
            return await sources.list_sources_for_user(session.user_id)

    @mcp.tool()  # pyright: ignore[reportUnusedFunction]
    async def get_source_status(
        source_id: str | None = None,
        connect_session_id: str | None = None,
        ctx: Context[Any, Any, Any] | None = None,
    ) -> SourceStatusResult:
        """Check connection and sync status for a data source."""
        lifespan: McpLifespanState = _require_lifespan(ctx)
        async with lifespan.app_context.session_factory() as db:
            sources: SourceService = build_source_service(db)
            if source_id is not None:
                source_uuid = parse_source_id(source_id)
                connect_uuid = (
                    parse_connect_session_id(connect_session_id)
                    if connect_session_id
                    else None
                )
                return await sources.get_source_status(
                    source_uuid,
                    connect_session_id=connect_uuid,
                )
            if connect_session_id is None:
                raise ValueError("Provide source_id or connect_session_id")
            session_uuid = parse_connect_session_id(connect_session_id)
            return await sources.get_source_status_for_connect_session(session_uuid)

    @mcp.tool()  # pyright: ignore[reportUnusedFunction]
    async def sync_source(
        source_id: str | None = None,
        connect_session_id: str | None = None,
        ctx: Context[Any, Any, Any] | None = None,
    ) -> SyncSourceResult:
        """Start or restart ingestion for a connected source (no browser step)."""
        lifespan: McpLifespanState = _require_lifespan(ctx)
        async with lifespan.app_context.session_factory() as db:
            sources: SourceService = build_source_service(db)
            if source_id is not None:
                source_uuid = parse_source_id(source_id)
                result = await sources.request_sync(source_uuid)
            elif connect_session_id is not None:
                session_uuid = parse_connect_session_id(connect_session_id)
                result = await sources.request_sync_for_connect_session(session_uuid)
            else:
                raise ValueError("Provide source_id or connect_session_id")
            await db.commit()
            return result

    @mcp.tool()  # pyright: ignore[reportUnusedFunction]
    async def query_network(
        question: str,
        connect_session_id: str | None = None,
        source_id: str | None = None,
        ctx: Context[Any, Any, Any] | None = None,
    ) -> QueryNetworkResult:
        """Search the user's contact graph using a natural-language question."""
        lifespan: McpLifespanState = _require_lifespan(ctx)
        async with lifespan.app_context.session_factory() as db:
            sources: SourceService = build_source_service(db)

            if connect_session_id is not None:
                session_uuid = parse_connect_session_id(connect_session_id)
                status: SourceStatusResult = (
                    await sources.get_source_status_for_connect_session(session_uuid)
                )
                if status.status != SessionStatus.CONNECTED:
                    return QueryNetworkResult(
                        question=question,
                        message="Connect a source first, then wait for sync to finish.",
                    )
                user_id = await sources.resolve_user_id(
                    connect_session_id=session_uuid
                )
            elif source_id is not None:
                source_uuid = parse_source_id(source_id)
                status = await sources.get_source_status(source_uuid)
                if status.connection_status != SourceConnectionStatus.CONNECTED:
                    return QueryNetworkResult(
                        question=question,
                        message="Source is not connected.",
                    )
                user_id = await sources.resolve_user_id(source_id=source_uuid)
            else:
                return QueryNetworkResult(
                    question=question,
                    message="Provide connect_session_id or source_id.",
                )

            if not await sources.user_has_queryable_graph(user_id):
                return QueryNetworkResult(
                    question=question,
                    message=(
                        "Sync still running or not started. Call sync_source, then "
                        "get_source_status until sync_state is partial or complete."
                    ),
                )

            planner = QueryPlanner(lifespan.app_context.settings)
            plan = await planner.plan(question)
            executor = NetworkQueryService(db)
            matches: list[PersonMatch] = await executor.execute(
                user_id=user_id,
                plan=plan,
            )
            if not matches:
                return QueryNetworkResult(
                    question=question,
                    matches=[],
                    applied_plan=plan,
                    message="No matching contacts found in your graph for that question.",
                )
            return QueryNetworkResult(
                question=question,
                matches=matches,
                applied_plan=plan,
                message=f"Found {len(matches)} matching contact(s).",
            )

    return mcp


def _require_lifespan(ctx: Context[Any, Any, Any] | None) -> McpLifespanState:
    if ctx is None:
        raise RuntimeError("MCP Context is required")
    lifespan: object | None = ctx.request_context.lifespan_context  # pyright: ignore[reportUnknownMemberType]
    if not isinstance(lifespan, McpLifespanState):
        raise RuntimeError("MCP lifespan context not initialized")
    return lifespan
