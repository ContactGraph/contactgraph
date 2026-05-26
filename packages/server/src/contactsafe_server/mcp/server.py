import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from contactsafe_core.enums import SourceType
from contactsafe_core.schemas import (
    ConnectSourceResult,
    DescribeGraphResult,
    EditTrustedUsersResult,
    ListSourcesResult,
    QueryNetworkResult,
    SourceStatusResult,
    SyncSourceResult,
    ViewTrustedUsersResult,
)
from mcp.server.fastmcp import Context, FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from starlette.requests import Request

from contactsafe_server import actions
from contactsafe_server.config import Settings
from contactsafe_server.deps import AppContext, build_app_context

logger: logging.Logger = logging.getLogger(__name__)



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
        "ContactGraph",
        instructions=(
            "ContactGraph builds a private contact graph from connected data "
            "sources. Authenticate with OAuth 2.1 Bearer tokens "
            "(see /.well-known/oauth-protected-resource). "
            "Available source types: google_mail (Gmail metadata), "
            "google_contacts (Google Contacts / People API). "
            "Both share one Google OAuth consent — connecting either "
            "auto-creates both sources. "
            "Multiple Gmail accounts can be linked to a single user: call "
            "connect_source while authenticated to add another Google account. "
            "All contacts merge into one graph. "
            "Use connect_source to start OAuth, list_sources to see "
            "connections, sync_source to (re)start ingestion, "
            "get_source_status for progress, "
            "describe_graph for a high-level graph summary, "
            "query_network to search contacts (includes 2nd-degree results "
            "from trusted connections), "
            "view_trusted_users / edit_trusted_users to manage your "
            "trust list."
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
        """Connect a data source. Available source_type values: "google_mail", "google_contacts".

        Both share one Google OAuth consent flow. Connecting either auto-creates both
        sources. Returns oauth_url when browser authorization is needed, or
        access_token when the account is already connected.

        To add a second/third Gmail account, call this while authenticated with a
        Bearer token. The new Google account will be linked to the existing user.
        """
        lifespan: McpLifespanState = _require_lifespan(ctx)
        user_id: UUID | None = _get_user_id_from_ctx(ctx) if ctx is not None else None
        return await actions.connect_source(
            lifespan.app_context,
            user_id,
            source_type=source_type,
            user_token=user_token,
        )

    @mcp.tool()  # pyright: ignore[reportUnusedFunction]
    async def list_sources(
        ctx: Context[Any, Any, Any] | None = None,
    ) -> ListSourcesResult:
        """List connected data sources for the authenticated user."""
        lifespan: McpLifespanState = _require_lifespan(ctx)
        user_id: UUID | None = _get_user_id_from_ctx(ctx) if ctx is not None else None
        return await actions.list_sources(lifespan.app_context, user_id)

    @mcp.tool()  # pyright: ignore[reportUnusedFunction]
    async def get_source_status(
        source_id: str | None = None,
        ctx: Context[Any, Any, Any] | None = None,
    ) -> SourceStatusResult:
        """Check connection and sync status for a data source."""
        lifespan: McpLifespanState = _require_lifespan(ctx)
        user_id: UUID | None = _get_user_id_from_ctx(ctx) if ctx is not None else None
        return await actions.get_source_status(
            lifespan.app_context, user_id, source_id=source_id
        )

    @mcp.tool()  # pyright: ignore[reportUnusedFunction]
    async def sync_source(
        source_id: str | None = None,
        ctx: Context[Any, Any, Any] | None = None,
    ) -> SyncSourceResult:
        """Start or restart ingestion for a connected source (no browser step).

        When called without source_id, syncs all connected Gmail sources for the user.
        """
        lifespan: McpLifespanState = _require_lifespan(ctx)
        user_id: UUID | None = _get_user_id_from_ctx(ctx) if ctx is not None else None
        return await actions.sync_source(
            lifespan.app_context, user_id, source_id=source_id
        )

    @mcp.tool()  # pyright: ignore[reportUnusedFunction]
    async def query_network(
        question: str,
        ctx: Context[Any, Any, Any] | None = None,
    ) -> QueryNetworkResult:
        """Search the user's contact graph using a natural-language question.

        Results include both first-degree contacts (full detail) and second-degree
        contacts visible through your trust list (name, org, role only). For
        second-degree matches, ask your trusted connection for contact info directly.
        """
        lifespan: McpLifespanState = _require_lifespan(ctx)
        user_id: UUID | None = _get_user_id_from_ctx(ctx) if ctx is not None else None
        return await actions.query_network(
            lifespan.app_context, user_id, question=question
        )

    @mcp.tool()  # pyright: ignore[reportUnusedFunction]
    async def describe_graph(
        ctx: Context[Any, Any, Any] | None = None,
    ) -> DescribeGraphResult:
        """Summarize the user's contact graph (counts, top categories/orgs, strongest ties).

        Use this for broad questions like "who do I know?" before drilling down with
        query_network.
        """
        lifespan: McpLifespanState = _require_lifespan(ctx)
        user_id: UUID | None = _get_user_id_from_ctx(ctx) if ctx is not None else None
        return await actions.describe_graph(lifespan.app_context, user_id)

    @mcp.tool()  # pyright: ignore[reportUnusedFunction]
    async def view_trusted_users(
        ctx: Context[Any, Any, Any] | None = None,
    ) -> ViewTrustedUsersResult:
        """View your trust list: active members, pending invites you've sent, and
        invites waiting for your response.

        Trust list members can see each other's contacts (name, org, role) in
        query_network results. Max 20 members.
        """
        lifespan: McpLifespanState = _require_lifespan(ctx)
        user_id: UUID | None = _get_user_id_from_ctx(ctx) if ctx is not None else None
        return await actions.view_trusted_users(lifespan.app_context, user_id)

    @mcp.tool()  # pyright: ignore[reportUnusedFunction]
    async def edit_trusted_users(
        add: list[str] | None = None,
        remove: list[str] | None = None,
        accept: list[str] | None = None,
        decline: list[str] | None = None,
        set_privacy: list[dict[str, str]] | None = None,
        ctx: Context[Any, Any, Any] | None = None,
    ) -> EditTrustedUsersResult:
        """Manage your trust list (max 20 mutual connections).

        Parameters:
          add: Email addresses to invite to your trust list.
          remove: Email addresses to remove from your trust list.
          accept: Invite IDs to accept (from view_trusted_users inbound_invites).
          decline: Invite IDs to decline.
          set_privacy: List of {"person_id": "...", "label": "private"|"standard"}
                       to hide/unhide specific contacts from trust list queries.

        When adding someone not yet on ContactGraph, returns suggested invite copy
        you can send them via text or email.
        """
        lifespan: McpLifespanState = _require_lifespan(ctx)
        user_id: UUID | None = _get_user_id_from_ctx(ctx) if ctx is not None else None
        return await actions.edit_trusted_users(
            lifespan.app_context,
            user_id,
            add=add,
            remove=remove,
            accept=accept,
            decline=decline,
            set_privacy=set_privacy,
        )

    return mcp


def _get_user_id_from_ctx(ctx: Context[Any, Any, Any]) -> UUID | None:
    request: Request | None = ctx.request_context.request  # pyright: ignore[reportUnknownMemberType]
    if request is None:
        return None
    user_id_raw: object | None = getattr(request.state, "user_id", None)
    if user_id_raw is None:
        return None
    return UUID(str(user_id_raw))


def _require_lifespan(ctx: Context[Any, Any, Any] | None) -> McpLifespanState:
    if ctx is None:
        raise RuntimeError("MCP Context is required")
    lifespan: object | None = ctx.request_context.lifespan_context  # pyright: ignore[reportUnknownMemberType]
    if not isinstance(lifespan, McpLifespanState):
        raise RuntimeError("MCP lifespan context not initialized")
    return lifespan
