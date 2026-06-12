"""REST API that mirrors the MCP tool surface.

Every route delegates to the shared action functions in ``actions.py``.
Authentication uses the same JWT tokens as the MCP endpoint.  Admin users
(scope ``contactsafe:admin``) may act on behalf of another user via the
``X-On-Behalf-Of`` header (email address or user UUID).
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, Query, Request, UploadFile
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from contactsafe_core.contact_schemas import (
    CancelOrgEnrichmentResult,
    CreateOrgListRequest,
    CreateOrgListResult,
    DedupPersonsResult,
    DeleteOrgListRequest,
    DeleteOrgListResult,
    EnrichOrgsResult,
    EnrichPersonRequest,
    EnrichPersonResult,
    EnrichStrongTiesResult,
    GetOrgRequest,
    GetPersonRequest,
    ListOrgListsResult,
    ListOrgsRequest,
    ListOrgsResult,
    ListPeopleRequest,
    ListPeopleResult,
    ListStrongTiesResult,
    FlatJobListResult,
    JobDetailResult,
    JobMonitorConfigResult,
    JobScanStatusResult,
    JobPreferencesResult,
    JobTargetScope,
    ListOrgJobsResult,
    NotificationPreferencesResult,
    SetNotificationPreferencesRequest,
    ModifyOrgListMembershipRequest,
    ModifyOrgListMembershipResult,
    NetworkStatusResult,
    SetJobMonitorConfigRequest,
    SetJobPreferencesRequest,
    SetJobTargetScopeRequest,
    StartSingleOrgDiscoveryRequest,
    StartSingleOrgDiscoveryResult,
    OrgDetailResult,
    OrgEnrichmentStatusResult,
    PersonDetailResult,
    RenameOrgListRequest,
    RenameOrgListResult,
    ScrapingDogEnrichmentStatusResult,
    StrongTieCompaniesResult,
    StrongTieCountResult,
    UpdateOrgRequest,
    UpdatePersonRequest,
)
from contactsafe_core.schemas import (
    CancelSyncRequest,
    CancelSyncResult,
    ConnectSourceRequest,
    ConnectSourceResult,
    DeleteUserExperienceRequest,
    DeleteUserAccountResult,
    DescribeGraphResult,
    EditTrustedUsersRequest,
    EditTrustedUsersResult,
    EnrichmentStatusResult,
    GetSourceStatusRequest,
    ListContactEnrichmentStatusResult,
    ListSourcesResult,
    PollConnectResult,
    QueryNetworkRequest,
    QueryNetworkResult,
    SaveUserExperienceRequest,
    SecondDegreeTargetCompaniesResult,
    SourceStatusResult,
    StartEnrichmentResult,
    SyncSourceRequest,
    SyncSourceResult,
    TargetCompaniesResult,
    UpdateUserProfileRequest,
    UploadSourceRequest,
    UploadSourceResult,
    UserProfileResult,
    ViewTrustedUsersResult,
)
from contactsafe_server import actions
from contactsafe_server.db.models import User
from contactsafe_server.deps import AppContext
from contactsafe_server.events import GraphEvent, JobEvent, graph_event_bus, job_event_bus
from contactsafe_server.services.jwt_service import JWTService
from contactsafe_server.services.job_digest_service import JobDigestService

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

    ctx: AppContext = _get_app_context(request)
    effective_id: UUID
    try:
        effective_id = UUID(x_on_behalf_of)
        async with ctx.session_factory() as db:
            if await db.get(User, effective_id) is None:
                raise HTTPException(
                    status_code=404,
                    detail=f"User not found: {x_on_behalf_of}",
                )
    except ValueError:
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
            effective_id = row  # type: ignore[assignment]

    logger.warning(
        "Admin impersonation",
        extra={
            "admin_user_id": str(auth.user_id),
            "effective_user_id": str(effective_id),
            "path": request.url.path,
            "method": request.method,
        },
    )
    return effective_id


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
    poll_secret: Annotated[str, Header(alias="X-Poll-Secret")],
) -> PollConnectResult:
    if not poll_secret.strip():
        raise HTTPException(status_code=401, detail="X-Poll-Secret header required")
    try:
        return await actions.poll_connect(
            ctx,
            connect_session_id=connect_session_id,
            poll_secret=poll_secret,
        )
    except ValueError as exc:
        detail: str = str(exc)
        if detail == "Invalid poll credentials":
            raise HTTPException(status_code=401, detail=detail) from exc
        raise HTTPException(status_code=404, detail=detail) from exc


@router.post("/list-sources", response_model=ListSourcesResult)
async def api_list_sources(ctx: Ctx, user_id: EffectiveUser) -> ListSourcesResult:
    return await actions.list_sources(ctx, user_id)


@router.post("/cancel-sync")
async def api_cancel_sync(
    ctx: Ctx,
    user_id: EffectiveUser,
    body: CancelSyncRequest,
) -> CancelSyncResult:
    return await actions.cancel_sync(ctx, user_id, source_id=body.source_id)


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


@router.post("/list-contact-enrichment-status", response_model=ListContactEnrichmentStatusResult)
async def api_list_contact_enrichment_status(
    ctx: Ctx,
    user_id: EffectiveUser,
) -> ListContactEnrichmentStatusResult:
    return await actions.list_contact_enrichment_status(ctx, user_id)


@router.post("/get-user-profile", response_model=UserProfileResult)
async def api_get_user_profile(ctx: Ctx, user_id: EffectiveUser) -> UserProfileResult:
    return await actions.get_user_profile(ctx, user_id)


@router.post("/update-user-profile", response_model=UserProfileResult)
async def api_update_user_profile(
    ctx: Ctx,
    user_id: EffectiveUser,
    body: UpdateUserProfileRequest,
) -> UserProfileResult:
    return await actions.update_user_profile(ctx, user_id, body)


@router.post("/save-user-experience", response_model=UserProfileResult)
async def api_save_user_experience(
    ctx: Ctx,
    user_id: EffectiveUser,
    body: SaveUserExperienceRequest,
) -> UserProfileResult:
    try:
        return await actions.save_user_experience(
            ctx,
            user_id,
            experience_id=body.id,
            company=body.company,
            role=body.role,
            is_current=body.is_current,
            started_at=body.started_at,
            ended_at=body.ended_at,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/delete-user-experience", response_model=UserProfileResult)
async def api_delete_user_experience(
    ctx: Ctx,
    user_id: EffectiveUser,
    body: DeleteUserExperienceRequest,
) -> UserProfileResult:
    try:
        return await actions.delete_user_experience(
            ctx,
            user_id,
            experience_id=body.id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/delete-user-account", response_model=DeleteUserAccountResult)
async def api_delete_user_account(
    ctx: Ctx,
    user_id: EffectiveUser,
) -> DeleteUserAccountResult:
    return await actions.delete_user_account(ctx, user_id)


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


@router.post("/get-target-companies", response_model=TargetCompaniesResult)
async def api_get_target_companies(
    ctx: Ctx,
    user_id: EffectiveUser,
) -> TargetCompaniesResult:
    return await actions.get_target_companies(ctx, user_id)


@router.post("/get-second-degree-target-companies", response_model=SecondDegreeTargetCompaniesResult)
async def api_get_second_degree_target_companies(
    ctx: Ctx,
    user_id: EffectiveUser,
) -> SecondDegreeTargetCompaniesResult:
    return await actions.get_second_degree_target_companies(ctx, user_id)


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
async def api_list_people(
    ctx: Ctx,
    user_id: EffectiveUser,
    body: ListPeopleRequest | None = None,
) -> ListPeopleResult:
    request: ListPeopleRequest = body or ListPeopleRequest()
    return await actions.list_people(
        ctx,
        user_id,
        network_only=request.network_only,
        include_shared=request.include_shared,
    )


@router.post("/list-strong-ties", response_model=ListStrongTiesResult)
async def api_list_strong_ties(ctx: Ctx, user_id: EffectiveUser) -> ListStrongTiesResult:
    return await actions.list_strong_ties(ctx, user_id)


@router.post("/count-strong-ties", response_model=StrongTieCountResult)
async def api_count_strong_ties(ctx: Ctx, user_id: EffectiveUser) -> StrongTieCountResult:
    return await actions.count_strong_ties(ctx, user_id)


@router.post("/list-strong-tie-companies", response_model=StrongTieCompaniesResult)
async def api_list_strong_tie_companies(
    ctx: Ctx,
    user_id: EffectiveUser,
) -> StrongTieCompaniesResult:
    return await actions.list_strong_tie_companies(ctx, user_id)


@router.post("/enrich-strong-ties", response_model=EnrichStrongTiesResult)
async def api_enrich_strong_ties(ctx: Ctx, user_id: EffectiveUser) -> EnrichStrongTiesResult:
    return await actions.enrich_strong_ties(ctx, user_id)


@router.post("/get-scrapingdog-enrichment-status", response_model=ScrapingDogEnrichmentStatusResult)
async def api_get_scrapingdog_enrichment_status(
    ctx: Ctx,
    user_id: EffectiveUser,
) -> ScrapingDogEnrichmentStatusResult:
    return await actions.get_scrapingdog_enrichment_status(ctx, user_id)


@router.post("/get-network-status", response_model=NetworkStatusResult)
async def api_get_network_status(ctx: Ctx, user_id: EffectiveUser) -> NetworkStatusResult:
    return await actions.get_network_status(ctx, user_id)


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


@router.post("/update-person", response_model=PersonDetailResult)
async def api_update_person(
    ctx: Ctx,
    user_id: EffectiveUser,
    body: UpdatePersonRequest,
) -> PersonDetailResult:
    try:
        return await actions.update_person(ctx, user_id, body=body)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("/enrich-person", response_model=EnrichPersonResult)
async def api_enrich_person(
    ctx: Ctx,
    user_id: EffectiveUser,
    body: EnrichPersonRequest,
) -> EnrichPersonResult:
    try:
        return await actions.enrich_person(ctx, user_id, person_id=body.person_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/list-orgs", response_model=ListOrgsResult)
async def api_list_orgs(
    ctx: Ctx,
    user_id: EffectiveUser,
    body: ListOrgsRequest | None = None,
) -> ListOrgsResult:
    request: ListOrgsRequest = body or ListOrgsRequest()
    return await actions.list_orgs(ctx, user_id, include_shared=request.include_shared)


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


@router.post("/update-org", response_model=OrgDetailResult)
async def api_update_org(
    ctx: Ctx,
    user_id: EffectiveUser,
    body: UpdateOrgRequest,
) -> OrgDetailResult:
    try:
        return await actions.update_org(ctx, user_id, body=body)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("/enrich-orgs", response_model=EnrichOrgsResult)
async def api_enrich_orgs(ctx: Ctx, user_id: EffectiveUser) -> EnrichOrgsResult:
    return await actions.enrich_orgs(ctx, user_id)


@router.post("/get-org-enrichment-status", response_model=OrgEnrichmentStatusResult)
async def api_get_org_enrichment_status(
    ctx: Ctx,
    user_id: EffectiveUser,
) -> OrgEnrichmentStatusResult:
    return await actions.get_org_enrichment_status(ctx, user_id)


@router.post("/cancel-org-enrichment", response_model=CancelOrgEnrichmentResult)
async def api_cancel_org_enrichment(
    ctx: Ctx,
    user_id: EffectiveUser,
) -> CancelOrgEnrichmentResult:
    return await actions.cancel_org_enrichment(ctx, user_id)


@router.post("/list-org-lists", response_model=ListOrgListsResult)
async def api_list_org_lists(ctx: Ctx, user_id: EffectiveUser) -> ListOrgListsResult:
    return await actions.list_org_lists(ctx, user_id)


@router.post("/create-org-list", response_model=CreateOrgListResult)
async def api_create_org_list(
    ctx: Ctx,
    user_id: EffectiveUser,
    body: CreateOrgListRequest,
) -> CreateOrgListResult:
    try:
        return await actions.create_org_list(ctx, user_id, body=body)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/rename-org-list", response_model=RenameOrgListResult)
async def api_rename_org_list(
    ctx: Ctx,
    user_id: EffectiveUser,
    body: RenameOrgListRequest,
) -> RenameOrgListResult:
    try:
        return await actions.rename_org_list(ctx, user_id, body=body)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("/delete-org-list", response_model=DeleteOrgListResult)
async def api_delete_org_list(
    ctx: Ctx,
    user_id: EffectiveUser,
    body: DeleteOrgListRequest,
) -> DeleteOrgListResult:
    try:
        return await actions.delete_org_list(ctx, user_id, body=body)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("/add-orgs-to-list", response_model=ModifyOrgListMembershipResult)
async def api_add_orgs_to_list(
    ctx: Ctx,
    user_id: EffectiveUser,
    body: ModifyOrgListMembershipRequest,
) -> ModifyOrgListMembershipResult:
    try:
        return await actions.add_orgs_to_list(ctx, user_id, body=body)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("/remove-orgs-from-list", response_model=ModifyOrgListMembershipResult)
async def api_remove_orgs_from_list(
    ctx: Ctx,
    user_id: EffectiveUser,
    body: ModifyOrgListMembershipRequest,
) -> ModifyOrgListMembershipResult:
    try:
        return await actions.remove_orgs_from_list(ctx, user_id, body=body)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("/get-job-monitor-config", response_model=JobMonitorConfigResult)
async def api_get_job_monitor_config(
    ctx: Ctx,
    user_id: EffectiveUser,
) -> JobMonitorConfigResult:
    return await actions.get_job_monitor_config(ctx, user_id)


@router.post("/set-job-monitor-config", response_model=JobMonitorConfigResult)
async def api_set_job_monitor_config(
    ctx: Ctx,
    user_id: EffectiveUser,
    body: SetJobMonitorConfigRequest,
) -> JobMonitorConfigResult:
    try:
        return await actions.set_job_monitor_config(ctx, user_id, body=body)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/get-job-scan-status", response_model=JobScanStatusResult)
async def api_get_job_scan_status(
    ctx: Ctx,
    user_id: EffectiveUser,
) -> JobScanStatusResult:
    return await actions.get_job_scan_status(ctx, user_id)


@router.post(
    "/start-single-org-job-discovery",
    response_model=StartSingleOrgDiscoveryResult,
)
async def api_start_single_org_job_discovery(
    ctx: Ctx,
    user_id: EffectiveUser,
    body: StartSingleOrgDiscoveryRequest,
) -> StartSingleOrgDiscoveryResult:
    return await actions.start_single_org_job_discovery(ctx, user_id, org_id=body.org_id)


def _format_sse_event(event: JobEvent | GraphEvent) -> str:
    return f"data: {json.dumps(event)}\n\n"


@router.get("/events/jobs")
async def api_job_events(
    request: Request,
    ctx: Ctx,
    user_id: EffectiveUser,
) -> StreamingResponse:
    async def event_generator():
        queue = job_event_bus.register(user_id)
        try:
            async with ctx.session_factory() as db:
                from contactsafe_server.services.job_discovery_service import JobDiscoveryService
                from contactsafe_server.services.job_relevance_service import (
                    get_scoring_progress_async,
                )

                discovery_service = JobDiscoveryService(db, ctx.settings)
                scan_status = await discovery_service.get_scan_status(user_id)
                if scan_status.scanning_active:
                    yield _format_sse_event(
                        {
                            "type": "scan_progress",
                            "scanning_active": True,
                            "current_org_name": None,
                        },
                    )

                scoring_progress: tuple[int, int] | None = await get_scoring_progress_async(
                    user_id,
                )
                if scoring_progress is not None:
                    scored, total = scoring_progress
                    yield _format_sse_event(
                        {
                            "type": "scoring_progress",
                            "scored": scored,
                            "total": total,
                        },
                    )

            while True:
                if await request.is_disconnected():
                    break
                try:
                    event: JobEvent | None = await asyncio.wait_for(queue.get(), timeout=15.0)
                except TimeoutError:
                    yield ": keepalive\n\n"
                    continue
                if event is None:
                    break
                yield _format_sse_event(event)
        finally:
            job_event_bus.unregister(user_id, queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/events/graph")
async def api_graph_events(
    request: Request,
    ctx: Ctx,
    user_id: EffectiveUser,
) -> StreamingResponse:
    async def event_generator():
        queue = graph_event_bus.register(user_id)
        try:
            async with ctx.session_factory() as db:
                from contactsafe_core.enums import SyncState
                from contactsafe_server.db.models import Source
                from contactsafe_server.graph_event_publishers import source_sync_event_for
                from contactsafe_server.services.org_enrichment_service import OrgEnrichmentService

                sources_result = await db.execute(
                    select(Source).where(
                        Source.user_id == user_id,
                        Source.sync_state.in_(
                            [
                                SyncState.SYNCING.value,
                                SyncState.PENDING.value,
                                SyncState.PARTIAL.value,
                            ],
                        ),
                    ),
                )
                for source in sources_result.scalars().all():
                    yield _format_sse_event(source_sync_event_for(source))

                org_service = OrgEnrichmentService(db, ctx.settings)
                enrichment_status = await org_service.get_status(user_id)
                if enrichment_status.state == "running":
                    yield _format_sse_event(
                        {
                            "type": "org_enrichment_progress",
                            "orgs_enriched": enrichment_status.orgs_enriched,
                            "orgs_total": enrichment_status.orgs_total,
                            "progress_message": enrichment_status.progress_message,
                            "state": "running",
                        },
                    )

            while True:
                if await request.is_disconnected():
                    break
                try:
                    event: GraphEvent | None = await asyncio.wait_for(
                        queue.get(),
                        timeout=15.0,
                    )
                except TimeoutError:
                    yield ": keepalive\n\n"
                    continue
                if event is None:
                    break
                yield _format_sse_event(event)
        finally:
            graph_event_bus.unregister(user_id, queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


class _ListOrgJobsBody(BaseModel):
    relevant_only: bool = False


@router.post("/list-org-jobs", response_model=ListOrgJobsResult)
async def api_list_org_jobs(
    ctx: Ctx,
    user_id: EffectiveUser,
    body: _ListOrgJobsBody = _ListOrgJobsBody(),
) -> ListOrgJobsResult:
    return await actions.list_org_jobs(ctx, user_id, relevant_only=body.relevant_only)


@router.post("/list-flat-jobs", response_model=FlatJobListResult)
async def api_list_flat_jobs(
    ctx: Ctx,
    user_id: EffectiveUser,
) -> FlatJobListResult:
    return await actions.list_flat_jobs(ctx, user_id)


class _GetJobDetailBody(BaseModel):
    job_id: UUID


@router.post("/get-job-detail", response_model=JobDetailResult)
async def api_get_job_detail(
    ctx: Ctx,
    user_id: EffectiveUser,
    body: _GetJobDetailBody,
) -> JobDetailResult:
    return await actions.get_job_detail(ctx, user_id, job_id=body.job_id)


@router.post("/get-job-preferences", response_model=JobPreferencesResult)
async def api_get_job_preferences(ctx: Ctx, user_id: EffectiveUser) -> JobPreferencesResult:
    return await actions.get_job_preferences(ctx, user_id)


@router.post("/set-job-preferences", response_model=JobPreferencesResult)
async def api_set_job_preferences(
    ctx: Ctx,
    user_id: EffectiveUser,
    body: SetJobPreferencesRequest,
) -> JobPreferencesResult:
    return await actions.set_job_preferences(
        ctx, user_id, body.text,
        location_pref=body.location_pref,
        location_city=body.location_city,
        commute_max_minutes=body.commute_max_minutes,
        commute_note=body.commute_note,
    )


@router.post("/set-job-target-scope", response_model=JobPreferencesResult)
async def api_set_job_target_scope(
    ctx: Ctx,
    user_id: EffectiveUser,
    body: SetJobTargetScopeRequest,
) -> JobPreferencesResult:
    return await actions.set_job_target_scope(ctx, user_id, body.target_scope)


@router.post("/get-notification-preferences", response_model=NotificationPreferencesResult)
async def api_get_notification_preferences(
    ctx: Ctx,
    user_id: EffectiveUser,
) -> NotificationPreferencesResult:
    return await actions.get_notification_preferences(ctx, user_id)


@router.post("/set-notification-preferences", response_model=NotificationPreferencesResult)
async def api_set_notification_preferences(
    ctx: Ctx,
    user_id: EffectiveUser,
    body: SetNotificationPreferencesRequest,
) -> NotificationPreferencesResult:
    return await actions.set_notification_preferences(
        ctx,
        user_id,
        body.job_digest_frequency,
    )


@router.get("/unsubscribe", response_class=HTMLResponse)
@router.post("/unsubscribe", response_class=HTMLResponse)
async def api_unsubscribe(
    request: Request,
    ctx: Ctx,
    token: str = Query(...),
) -> HTMLResponse:
    jwt_service: JWTService = ctx.jwt_service
    try:
        user_id: UUID = jwt_service.decode_unsubscribe_token(token)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid or expired unsubscribe link")

    async with ctx.session_factory() as db:
        service = JobDigestService(db, ctx.settings, jwt_service=jwt_service)
        updated: bool = await service.unsubscribe_user(user_id)
    if not updated:
        raise HTTPException(status_code=404, detail="User not found")

    from pathlib import Path

    from fastapi.templating import Jinja2Templates

    templates_dir: Path = (
        Path(__file__).resolve().parents[1] / "templates" / "email"
    )
    templates: Jinja2Templates = Jinja2Templates(directory=str(templates_dir))
    return templates.TemplateResponse(
        request,
        "unsubscribed.html",
        {
            "profile_url": f"{ctx.settings.effective_web_base_url}/profile",
        },
    )


@router.post("/webhooks/theirstack")
async def api_theirstack_webhook(request: Request, ctx: Ctx) -> dict[str, bool]:
    payload: bytes = await request.body()
    signature: str | None = request.headers.get("X-TheirStack-Signature-256")
    try:
        body: dict[str, Any] = json.loads(payload.decode("utf-8"))
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    from contactsafe_server.services.theirstack_webhook import handle_theirstack_webhook

    async with ctx.session_factory() as db:
        accepted: bool = await handle_theirstack_webhook(
            db,
            ctx.settings,
            payload,
            signature,
            body,
        )
    if not accepted:
        raise HTTPException(status_code=403, detail="Invalid webhook signature")
    return {"ok": True}


@router.post("/dedup-persons", response_model=DedupPersonsResult)
async def api_dedup_persons(ctx: Ctx, user_id: EffectiveUser) -> DedupPersonsResult:
    try:
        return await actions.dedup_persons(ctx, user_id)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=str(exc))
