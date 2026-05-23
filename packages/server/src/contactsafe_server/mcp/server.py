from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from mcp.server.fastmcp import Context, FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from starlette.requests import Request

from contactsafe_core.enums import SessionStatus, SourceConnectionStatus, SourceType
from contactsafe_server.config import Settings
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
    build_oauth_server_service,
    build_oauth_service,
    build_source_service,
)
from contactsafe_server.services.network_query_service import NetworkQueryService
from contactsafe_server.services.query_planner import QueryPlanner
from contactsafe_server.services.oauth_service import OAuthService
from contactsafe_server.services.source_service import SourceService
from contactsafe_server.utils import parse_connect_session_id, parse_source_id

_DEPRECATION_SUFFIX: str = (
    " Deprecated: use Authorization: Bearer <access_token> instead of connect_session_id."
)


@dataclass(frozen=True, slots=True)
class McpLifespanState:
    app_context: AppContext


@asynccontextmanager
async def _mcp_lifespan(_server: FastMCP) -> AsyncGenerator[McpLifespanState, None]:
    ctx: AppContext = build_app_context()
    yield McpLifespanState(app_context=ctx)


def create_mcp_server(settings: Settings) -> FastMCP:
    transport_security: TransportSecuritySettings = settings.mcp_transport_security
    mcp: FastMCP = FastMCP(
        "ContactSafe",
        instructions=(
            "ContactSafe builds a private contact graph from connected data sources. "
            "Authenticate with OAuth 2.1 Bearer tokens (see /.well-known/oauth-protected-resource). "
            "Use connect_source to start OAuth, list_sources to see connections, "
            "sync_source to (re)start ingestion, get_source_status for progress, "
            "and query_network to search contacts."
        ),
        json_response=True,
        stateless_http=True,
        host="0.0.0.0",
        transport_security=transport_security,
        lifespan=_mcp_lifespan,
    )

    @mcp.tool()  # pyright: ignore[reportUnusedFunction]
    async def connect_source(
        source_type: str = SourceType.GOOGLE_MAIL.value,
        user_token: str | None = None,
        ctx: Context[Any, Any, Any] | None = None,
    ) -> ConnectSourceResult:
        """Connect a data source (google_mail supported today).

        Returns oauth_url when browser authorization is needed, or access_token when
        the account is already connected.
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
            if result.already_connected and result.source_id is not None:
                sources: SourceService = build_source_service(db)
                user_id: UUID = await sources.resolve_user_id(source_id=result.source_id)
                token_response = await build_oauth_server_service(
                    db, lifespan.app_context
                ).mint_tokens_for_user(user_id)
                result = result.model_copy(
                    update={
                        "access_token": token_response.access_token,
                        "refresh_token": token_response.refresh_token,
                    }
                )
            await db.commit()
            return result

    @mcp.tool()  # pyright: ignore[reportUnusedFunction]
    async def list_sources(
        connect_session_id: str | None = None,
        ctx: Context[Any, Any, Any] | None = None,
    ) -> ListSourcesResult:
        """List connected data sources for the authenticated user."""
        lifespan: McpLifespanState = _require_lifespan(ctx)
        async with lifespan.app_context.session_factory() as db:
            oauth: OAuthService = build_oauth_service(db, lifespan.app_context)
            user_id, deprecated = await _resolve_authenticated_user_id(
                ctx, connect_session_id, oauth
            )
            if user_id is None:
                return ListSourcesResult(
                    sources=[],
                    message=(
                        "Authentication required. Obtain a Bearer token via OAuth "
                        f"({lifespan.app_context.settings.base_url.rstrip('/')}"
                        "/.well-known/oauth-protected-resource)."
                    ),
                )
            sources: SourceService = build_source_service(db)
            result = await sources.list_sources_for_user(user_id)
            if deprecated:
                result = result.model_copy(
                    update={"message": _with_deprecation(result.message)}
                )
            return result

    @mcp.tool()  # pyright: ignore[reportUnusedFunction]
    async def get_source_status(
        source_id: str | None = None,
        connect_session_id: str | None = None,
        ctx: Context[Any, Any, Any] | None = None,
    ) -> SourceStatusResult:
        """Check connection and sync status for a data source."""
        lifespan: McpLifespanState = _require_lifespan(ctx)
        async with lifespan.app_context.session_factory() as db:
            oauth: OAuthService = build_oauth_service(db, lifespan.app_context)
            user_id, deprecated = await _resolve_authenticated_user_id(
                ctx, connect_session_id, oauth
            )
            sources: SourceService = build_source_service(db)
            if source_id is not None:
                source_uuid = parse_source_id(source_id)
                connect_uuid = (
                    parse_connect_session_id(connect_session_id)
                    if connect_session_id
                    else None
                )
                result = await sources.get_source_status(
                    source_uuid,
                    connect_session_id=connect_uuid,
                )
            elif user_id is not None:
                result = await sources.get_source_status_for_user(user_id)
            else:
                raise ValueError(
                    "Authentication required (Bearer token) or provide source_id"
                )
            if deprecated:
                result = result.model_copy(
                    update={"message": _with_deprecation(result.message)}
                )
            return result

    @mcp.tool()  # pyright: ignore[reportUnusedFunction]
    async def sync_source(
        source_id: str | None = None,
        connect_session_id: str | None = None,
        ctx: Context[Any, Any, Any] | None = None,
    ) -> SyncSourceResult:
        """Start or restart ingestion for a connected source (no browser step)."""
        lifespan: McpLifespanState = _require_lifespan(ctx)
        async with lifespan.app_context.session_factory() as db:
            oauth: OAuthService = build_oauth_service(db, lifespan.app_context)
            user_id, deprecated = await _resolve_authenticated_user_id(
                ctx, connect_session_id, oauth
            )
            sources: SourceService = build_source_service(db)
            if source_id is not None:
                source_uuid = parse_source_id(source_id)
                result = await sources.request_sync(source_uuid)
            elif user_id is not None:
                result = await sources.request_sync_for_user(user_id)
            else:
                raise ValueError(
                    "Authentication required (Bearer token) or provide source_id"
                )
            await db.commit()
            if deprecated:
                result = result.model_copy(
                    update={"message": _with_deprecation(result.message)}
                )
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
            oauth: OAuthService = build_oauth_service(db, lifespan.app_context)
            auth_user_id, deprecated = await _resolve_authenticated_user_id(
                ctx, connect_session_id, oauth
            )
            sources: SourceService = build_source_service(db)

            resolved_user_id: UUID | None = auth_user_id
            if resolved_user_id is None and source_id is not None:
                source_uuid = parse_source_id(source_id)
                status = await sources.get_source_status(source_uuid)
                if status.connection_status != SourceConnectionStatus.CONNECTED:
                    return QueryNetworkResult(
                        question=question,
                        message="Source is not connected.",
                    )
                resolved_user_id = await sources.resolve_user_id(source_id=source_uuid)
            elif resolved_user_id is None:
                return QueryNetworkResult(
                    question=question,
                    message=(
                        "Authentication required. Provide a Bearer token or source_id."
                    ),
                )

            if resolved_user_id is None:
                return QueryNetworkResult(
                    question=question,
                    message="Unable to resolve user for query.",
                )

            if not await sources.user_has_queryable_graph(resolved_user_id):
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
                user_id=resolved_user_id,
                plan=plan,
            )
            deprecation_note: str = _DEPRECATION_SUFFIX if deprecated else ""
            if not matches:
                return QueryNetworkResult(
                    question=question,
                    matches=[],
                    applied_plan=plan,
                    message=(
                        "No matching contacts found in your graph for that question."
                        f"{deprecation_note}"
                    ),
                )
            return QueryNetworkResult(
                question=question,
                matches=matches,
                applied_plan=plan,
                message=f"Found {len(matches)} matching contact(s).{deprecation_note}",
            )

    return mcp


async def _resolve_authenticated_user_id(
    ctx: Context[Any, Any, Any] | None,
    connect_session_id: str | None,
    oauth: OAuthService,
) -> tuple[UUID | None, bool]:
    deprecated: bool = connect_session_id is not None
    if ctx is not None:
        user_id: UUID | None = _get_user_id_from_ctx(ctx)
        if user_id is not None:
            return user_id, deprecated
    if connect_session_id is None:
        return None, False
    session_uuid: UUID = parse_connect_session_id(connect_session_id)
    session = await oauth.get_session_by_id(session_uuid)
    if session is None or session.user_id is None:
        return None, True
    return session.user_id, True


def _get_user_id_from_ctx(ctx: Context[Any, Any, Any]) -> UUID | None:
    request: Request | None = ctx.request_context.request  # pyright: ignore[reportUnknownMemberType]
    if request is None:
        return None
    user_id_raw: object | None = getattr(request.state, "user_id", None)
    if user_id_raw is None:
        return None
    return UUID(str(user_id_raw))


def _with_deprecation(message: str) -> str:
    if _DEPRECATION_SUFFIX.strip() in message:
        return message
    return f"{message}{_DEPRECATION_SUFFIX}"


def _require_lifespan(ctx: Context[Any, Any, Any] | None) -> McpLifespanState:
    if ctx is None:
        raise RuntimeError("MCP Context is required")
    lifespan: object | None = ctx.request_context.lifespan_context  # pyright: ignore[reportUnknownMemberType]
    if not isinstance(lifespan, McpLifespanState):
        raise RuntimeError("MCP lifespan context not initialized")
    return lifespan
