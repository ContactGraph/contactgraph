from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from mcp.server.fastmcp import Context, FastMCP

from contactsafe_core.schemas import ConnectGmailResult, ImportStatus
from contactsafe_server.deps import AppContext, build_app_context, build_oauth_service
from contactsafe_server.services.oauth_service import OAuthService


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
            "ContactSafe builds a private contact graph from the user's Gmail and Calendar. "
            "Use connect_gmail to start OAuth, then get_import_status to confirm the connection."
        ),
        json_response=True,
        stateless_http=True,
        lifespan=_mcp_lifespan,
    )

    @mcp.tool()  # pyright: ignore[reportUnusedFunction]
    async def connect_gmail(
        user_token: str | None = None,
        ctx: Context[Any, Any, Any] | None = None,
    ) -> ConnectGmailResult:
        """Start Google OAuth for Gmail and Calendar read access.

        Returns a one-time OAuth URL the user must open in a browser.
        Pass user_token (email) if reconnecting a known account.
        """
        lifespan: McpLifespanState = _require_lifespan(ctx)
        async with lifespan.app_context.session_factory() as db:
            service: OAuthService = build_oauth_service(db, lifespan.app_context)
            result: ConnectGmailResult = await service.create_connect_session(user_token)
            await db.commit()
            return result

    @mcp.tool()  # pyright: ignore[reportUnusedFunction]
    async def get_import_status(
        session_id: str,
        ctx: Context[Any, Any, Any] | None = None,
    ) -> ImportStatus:
        """Check OAuth / import status for a connect session."""
        lifespan: McpLifespanState = _require_lifespan(ctx)
        try:
            session_uuid: UUID = UUID(session_id)
        except ValueError as exc:
            raise ValueError(f"Invalid session_id: {session_id}") from exc

        async with lifespan.app_context.session_factory() as db:
            service: OAuthService = build_oauth_service(db, lifespan.app_context)
            return await service.get_import_status(session_uuid)

    return mcp


def _require_lifespan(ctx: Context[Any, Any, Any] | None) -> McpLifespanState:
    if ctx is None:
        raise RuntimeError("MCP Context is required")
    lifespan: object | None = ctx.request_context.lifespan_context  # pyright: ignore[reportUnknownMemberType]
    if not isinstance(lifespan, McpLifespanState):
        raise RuntimeError("MCP lifespan context not initialized")
    return lifespan
