"""REST API that mirrors the MCP tool surface.

Every route delegates to the shared action functions in ``actions.py``.
Authentication uses the same JWT tokens as the MCP endpoint.  Admin users
(scope ``contactsafe:admin``) may act on behalf of another user via the
``X-On-Behalf-Of`` header (email address or user UUID).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, Request, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from contactsafe_core.contact_schemas import (
    DedupPersonsResult,
    GetOrgRequest,
    GetPersonRequest,
    ListOrgsResult,
    ListPeopleResult,
    OrgDetailResult,
    PersonDetailResult,
)
from contactsafe_core.schemas import (
    ConnectSourceRequest,
    ConnectSourceResult,
    DescribeGraphResult,
    EditTrustedUsersRequest,
    EditTrustedUsersResult,
    EnrichmentStatusResult,
    GetSourceStatusRequest,
    ListSourcesResult,
    PollConnectResult,
    QueryNetworkRequest,
    QueryNetworkResult,
    SourceStatusResult,
    StartEnrichmentResult,
    SyncSourceRequest,
    SyncSourceResult,
    UpdateUserProfileRequest,
    UploadSourceRequest,
    UploadSourceResult,
    UserProfileResult,
    ViewTrustedUsersResult,
)
from contactsafe_server import actions
from contactsafe_server.db.models import User
from contactsafe_server.deps import AppContext
from contactsafe_server.services.jwt_service import JWTService

logger: logging.Logger = logging.getLogger(__name__)

router: APIRouter = APIRouter()


# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------

_ADMIN_SCOPE: str = "contactsafe:admin"


@dataclass(frozen=True, slots=True)
class AuthenticatedUser:
    user_id: UUID
    scopes: str
    is_admin: bool


def _get_app_context(request: Request) -> AppContext:
    ctx: AppContext | None = getattr(request.app.state, "app_context", None)
    if ctx is None:
        raise HTTPException(status_code=503, detail="Application not initialized")
    return ctx


def _get_jwt_service(request: Request) -> JWTService:
    return _get_app_context(request).jwt_service


async def _authenticate(
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
) -> AuthenticatedUser:
    if authorization is None or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=401,
            detail="Bearer token required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token: str = authorization[7:].strip()
    if not token:
        raise HTTPException(
            status_code=401,
            detail="Bearer token required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    jwt_service: JWTService = _get_jwt_service(request)
    try:
        claims: dict[str, Any] = jwt_service.decode_token(token)
    except ValueError:
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if claims.get("typ") == "refresh":
        raise HTTPException(status_code=401, detail="Refresh tokens cannot be used for API access")

    sub: str = str(claims.get("sub", ""))
    if not sub:
        raise HTTPException(status_code=401, detail="Token missing subject")

    scopes: str = str(claims.get("scope", ""))
    return AuthenticatedUser(
        user_id=UUID(sub),
        scopes=scopes,
        is_admin=_ADMIN_SCOPE in scopes,
    )


async def _resolve_effective_user(
    request: Request,
    auth: AuthenticatedUser = Depends(_authenticate),
    x_on_behalf_of: Annotated[str | None, Header()] = None,
) -> UUID:
    """Return the effective user_id, honoring admin impersonation."""
    if x_on_behalf_of is None:
        return auth.user_id

    if not auth.is_admin:
        raise HTTPException(
            status_code=403,
            detail="X-On-Behalf-Of requires contactsafe:admin scope",
        )

    # Try as UUID first, then fall back to email lookup.
    try:
        return UUID(x_on_behalf_of)
    except ValueError:
        pass

    ctx: AppContext = _get_app_context(request)
    async with ctx.session_factory() as db:
        session: AsyncSession = db
        row = (
            await session.execute(
                select(User.id).where(User.email == x_on_behalf_of)
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(
                status_code=404,
                detail=f"User not found: {x_on_behalf_of}",
            )
        return row  # type: ignore[return-value]


EffectiveUser = Annotated[UUID, Depends(_resolve_effective_user)]
Ctx = Annotated[AppContext, Depends(_get_app_context)]


# ---------------------------------------------------------------------------
# Optional-auth helper (for connect-source)
# ---------------------------------------------------------------------------


async def _optional_authenticate(
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
) -> AuthenticatedUser | None:
    """Like ``_authenticate`` but returns ``None`` when no token is sent."""
    if authorization is None or not authorization.lower().startswith("bearer "):
        return None
    token: str = authorization[7:].strip()
    if not token:
        return None
    jwt_service: JWTService = _get_jwt_service(request)
    try:
        claims: dict[str, Any] = jwt_service.decode_token(token)
    except ValueError:
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if claims.get("typ") == "refresh":
        raise HTTPException(status_code=401, detail="Refresh tokens cannot be used for API access")
    sub: str = str(claims.get("sub", ""))
    if not sub:
        raise HTTPException(status_code=401, detail="Token missing subject")
    scopes: str = str(claims.get("scope", ""))
    return AuthenticatedUser(user_id=UUID(sub), scopes=scopes, is_admin=_ADMIN_SCOPE in scopes)


# ---------------------------------------------------------------------------
# Routes (unauthenticated)
# ---------------------------------------------------------------------------


@router.post("/connect-source", response_model=ConnectSourceResult)
async def api_connect_source(
    ctx: Ctx,
    body: ConnectSourceRequest | None = None,
    auth: AuthenticatedUser | None = Depends(_optional_authenticate),
) -> ConnectSourceResult:
    b: ConnectSourceRequest = body or ConnectSourceRequest()
    user_id: UUID | None = auth.user_id if auth else None
    return await actions.connect_source(
        ctx,
        user_id,
        source_type=b.source_type,
        user_token=b.user_token,
    )


@router.post("/poll-connect/{connect_session_id}", response_model=PollConnectResult)
async def api_poll_connect(
    ctx: Ctx,
    connect_session_id: UUID,
) -> PollConnectResult:
    try:
        return await actions.poll_connect(ctx, connect_session_id=connect_session_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("/list-sources", response_model=ListSourcesResult)
async def api_list_sources(ctx: Ctx, user_id: EffectiveUser) -> ListSourcesResult:
    return await actions.list_sources(ctx, user_id)


@router.post("/get-source-status", response_model=SourceStatusResult)
async def api_get_source_status(
    ctx: Ctx,
    user_id: EffectiveUser,
    body: GetSourceStatusRequest | None = None,
) -> SourceStatusResult:
    b: GetSourceStatusRequest = body or GetSourceStatusRequest()
    return await actions.get_source_status(ctx, user_id, source_id=b.source_id)


@router.post("/sync-source", response_model=SyncSourceResult)
async def api_sync_source(
    ctx: Ctx,
    user_id: EffectiveUser,
    body: SyncSourceRequest | None = None,
) -> SyncSourceResult:
    b: SyncSourceRequest = body or SyncSourceRequest()
    return await actions.sync_source(ctx, user_id, source_id=b.source_id)


@router.post("/start-enrichment", response_model=StartEnrichmentResult)
async def api_start_enrichment(ctx: Ctx, user_id: EffectiveUser) -> StartEnrichmentResult:
    return await actions.start_enrichment(ctx, user_id)


@router.post("/get-enrichment-status", response_model=EnrichmentStatusResult)
async def api_get_enrichment_status(
    ctx: Ctx,
    user_id: EffectiveUser,
) -> EnrichmentStatusResult:
    return await actions.get_enrichment_status(ctx, user_id)


@router.post("/get-user-profile", response_model=UserProfileResult)
async def api_get_user_profile(ctx: Ctx, user_id: EffectiveUser) -> UserProfileResult:
    return await actions.get_user_profile(ctx, user_id)


@router.post("/update-user-profile", response_model=UserProfileResult)
async def api_update_user_profile(
    ctx: Ctx,
    user_id: EffectiveUser,
    body: UpdateUserProfileRequest,
) -> UserProfileResult:
    return await actions.update_user_profile(
        ctx,
        user_id,
        display_name=body.display_name,
        location=body.location,
    )


@router.post("/upload-source", response_model=UploadSourceResult)
async def api_upload_source(
    ctx: Ctx,
    user_id: EffectiveUser,
    body: UploadSourceRequest,
) -> UploadSourceResult:
    try:
        return await actions.upload_source(
            ctx,
            user_id,
            source_type=body.source_type,
            filename=body.filename,
            content=body.content,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/upload-contacts", response_model=SyncSourceResult)
async def api_upload_contacts(
    ctx: Ctx,
    user_id: EffectiveUser,
    file: UploadFile = File(...),
    source_id: str = Form(...),
) -> SyncSourceResult:
    raw: bytes = await file.read()
    max_bytes: int = ctx.settings.upload_max_file_size_bytes
    if len(raw) > max_bytes:
        raise HTTPException(
            status_code=400,
            detail=f"File exceeds {ctx.settings.upload_max_file_size_mb}MB limit",
        )
    filename: str = file.filename or "contacts.vcf"
    try:
        content: str = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise HTTPException(status_code=400, detail="File must be UTF-8 text") from exc
    try:
        return await actions.upload_contacts(
            ctx,
            user_id,
            source_id=source_id,
            filename=filename,
            content=content,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/query-network", response_model=QueryNetworkResult)
async def api_query_network(
    ctx: Ctx,
    user_id: EffectiveUser,
    body: QueryNetworkRequest,
) -> QueryNetworkResult:
    return await actions.query_network(ctx, user_id, question=body.question)


@router.post("/describe-graph", response_model=DescribeGraphResult)
async def api_describe_graph(ctx: Ctx, user_id: EffectiveUser) -> DescribeGraphResult:
    return await actions.describe_graph(ctx, user_id)


@router.post("/view-trusted-users", response_model=ViewTrustedUsersResult)
async def api_view_trusted_users(ctx: Ctx, user_id: EffectiveUser) -> ViewTrustedUsersResult:
    return await actions.view_trusted_users(ctx, user_id)


@router.post("/edit-trusted-users", response_model=EditTrustedUsersResult)
async def api_edit_trusted_users(
    ctx: Ctx,
    user_id: EffectiveUser,
    body: EditTrustedUsersRequest,
) -> EditTrustedUsersResult:
    return await actions.edit_trusted_users(
        ctx,
        user_id,
        add=body.add,
        remove=body.remove,
        accept=body.accept,
        decline=body.decline,
        set_privacy=body.set_privacy,
    )


@router.post("/list-people", response_model=ListPeopleResult)
async def api_list_people(ctx: Ctx, user_id: EffectiveUser) -> ListPeopleResult:
    return await actions.list_people(ctx, user_id)


@router.post("/get-person", response_model=PersonDetailResult)
async def api_get_person(
    ctx: Ctx,
    user_id: EffectiveUser,
    body: GetPersonRequest,
) -> PersonDetailResult:
    try:
        return await actions.get_person(ctx, user_id, person_id=body.person_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("/list-orgs", response_model=ListOrgsResult)
async def api_list_orgs(ctx: Ctx, user_id: EffectiveUser) -> ListOrgsResult:
    return await actions.list_orgs(ctx, user_id)


@router.post("/get-org", response_model=OrgDetailResult)
async def api_get_org(
    ctx: Ctx,
    user_id: EffectiveUser,
    body: GetOrgRequest,
) -> OrgDetailResult:
    try:
        return await actions.get_org(ctx, user_id, org_id=body.org_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("/dedup-persons", response_model=DedupPersonsResult)
async def api_dedup_persons(ctx: Ctx, user_id: EffectiveUser) -> DedupPersonsResult:
    try:
        return await actions.dedup_persons(ctx, user_id)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=str(exc))
