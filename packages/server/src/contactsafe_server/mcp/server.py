from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any

from mcp.server.fastmcp import Context, FastMCP

from contactsafe_core.enums import ImportState, SessionStatus
from contactsafe_core.schemas import ConnectGmailResult, ImportStatus, PersonMatch, QueryNetworkResult
from contactsafe_server.db.models import Person, User
from contactsafe_server.deps import AppContext, build_app_context, build_oauth_service
from contactsafe_server.services.import_scheduler import schedule_gmail_import
from contactsafe_server.services.import_service import QueryService
from contactsafe_server.services.oauth_service import OAuthService
from contactsafe_server.utils import parse_session_id


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
            "Use connect_gmail to start OAuth, get_import_status to track import progress, "
            "and query_network to search contacts (e.g. 'who do I know at Stripe?')."
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
            if result.already_connected and result.session_id:
                session = await service.get_session_by_id(result.session_id)
                if session is not None and session.user_id is not None:
                    user: User | None = await db.get(User, session.user_id)
                    if user is not None and (
                        user.import_state == ImportState.PENDING.value or user.import_error
                    ):
                        schedule_gmail_import(session.user_id)
            await db.commit()
            return result

    @mcp.tool()  # pyright: ignore[reportUnusedFunction]
    async def get_import_status(
        session_id: str,
        ctx: Context[Any, Any, Any] | None = None,
    ) -> ImportStatus:
        """Check OAuth / import status for a connect session."""
        lifespan: McpLifespanState = _require_lifespan(ctx)
        session_uuid = parse_session_id(session_id)

        async with lifespan.app_context.session_factory() as db:
            service: OAuthService = build_oauth_service(db, lifespan.app_context)
            return await service.get_import_status(session_uuid)

    @mcp.tool()  # pyright: ignore[reportUnusedFunction]
    async def query_network(
        question: str,
        session_id: str,
        ctx: Context[Any, Any, Any] | None = None,
    ) -> QueryNetworkResult:
        """Search the user's contact graph using a natural-language question."""
        lifespan: McpLifespanState = _require_lifespan(ctx)
        session_uuid = parse_session_id(session_id)

        async with lifespan.app_context.session_factory() as db:
            oauth: OAuthService = build_oauth_service(db, lifespan.app_context)
            status: ImportStatus = await oauth.get_import_status(session_uuid)
            if status.status != SessionStatus.CONNECTED:
                return QueryNetworkResult(
                    question=question,
                    message="Connect Gmail first, then wait for import to finish.",
                )
            session = await oauth.get_session_by_id(session_uuid)
            if session is None or session.user_id is None:
                return QueryNetworkResult(question=question, message="Unknown session.")

            if status.import_state not in {ImportState.PARTIAL, ImportState.COMPLETE}:
                return QueryNetworkResult(
                    question=question,
                    message=(
                        "Import still running. Call get_import_status and retry when "
                        "import_state is partial or complete."
                    ),
                )

            query: QueryService = QueryService(db)
            people: list[Person] = await query.query_by_session(
                session_user_id=session.user_id,
                question=question,
            )
            matches: list[PersonMatch] = [
                PersonMatch(
                    person_id=person.id,
                    name=person.canonical_name,
                    emails=list(person.email_addresses),
                    org_name=person.current_org_name,
                    last_seen_in_email=person.last_seen_in_email,
                    tie_strength_score=person.edge.tie_strength_score if person.edge else 0.0,
                    relevance=_relevance_note(person),
                )
                for person in people
            ]
            if not matches:
                return QueryNetworkResult(
                    question=question,
                    matches=[],
                    message="No matching contacts found in your graph for that question.",
                )
            return QueryNetworkResult(
                question=question,
                matches=matches,
                message=f"Found {len(matches)} matching contact(s).",
            )

    return mcp


def _relevance_note(person: Person) -> str:
    parts: list[str] = []
    if person.current_org_name:
        parts.append(f"org: {person.current_org_name}")
    if person.last_seen_in_email:
        parts.append(f"last email: {person.last_seen_in_email.date().isoformat()}")
    if person.edge and person.edge.tie_strength_score:
        parts.append(f"tie strength: {person.edge.tie_strength_score:.2f}")
    return "; ".join(parts) if parts else "contact from Gmail"


def _require_lifespan(ctx: Context[Any, Any, Any] | None) -> McpLifespanState:
    if ctx is None:
        raise RuntimeError("MCP Context is required")
    lifespan: object | None = ctx.request_context.lifespan_context  # pyright: ignore[reportUnknownMemberType]
    if not isinstance(lifespan, McpLifespanState):
        raise RuntimeError("MCP lifespan context not initialized")
    return lifespan
