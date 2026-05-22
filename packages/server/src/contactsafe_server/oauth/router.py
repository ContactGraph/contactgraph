import uuid
from collections.abc import AsyncGenerator
from pathlib import Path

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from contactsafe_core.enums import SessionStatus
from contactsafe_server.config import Settings, get_settings
from contactsafe_server.db.connection import get_session_factory
from contactsafe_server.db.models import ConnectSession, User
from contactsafe_server.deps import build_jwt_service
from contactsafe_server.oauth.google import GoogleOAuthClient
from contactsafe_server.services.crypto import TokenEncryptor
from contactsafe_server.services.import_scheduler import schedule_source_sync
from contactsafe_server.services.oauth_server_service import (
    OAuthServerService,
    parse_scopes_param,
)
from contactsafe_server.services.oauth_service import OAuthService

router: APIRouter = APIRouter(prefix="/oauth", tags=["oauth"])
_templates_dir: Path = Path(__file__).parent / "templates"
templates: Jinja2Templates = Jinja2Templates(directory=str(_templates_dir))


def _build_oauth_service(
    db: AsyncSession,
    settings: Settings,
) -> OAuthService:
    encryptor: TokenEncryptor = TokenEncryptor(settings.token_encryption_key)
    google: GoogleOAuthClient = GoogleOAuthClient(settings)
    return OAuthService(db=db, settings=settings, encryptor=encryptor, google=google)


def _build_oauth_server_service(
    db: AsyncSession,
    settings: Settings,
) -> OAuthServerService:
    return OAuthServerService(
        db=db,
        settings=settings,
        jwt_service=build_jwt_service(settings),
    )


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    factory = get_session_factory()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


@router.get("/authorize")
async def oauth_authorize_pkce(
    redirect_uri: str = Query(...),
    code_challenge: str = Query(...),
    state: str = Query(...),
    code_challenge_method: str = Query(default="S256"),
    scope: str = Query(default="contactsafe:read contactsafe:write"),
    client_id: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> RedirectResponse:
    _ = client_id
    oauth_server: OAuthServerService = _build_oauth_server_service(db, settings)
    try:
        session: ConnectSession = await oauth_server.create_oauth_authorize_session(
            redirect_uri=redirect_uri,
            code_challenge=code_challenge,
            code_challenge_method=code_challenge_method,
            client_state=state,
            scopes=parse_scopes_param(scope),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    oauth_service: OAuthService = _build_oauth_service(db, settings)
    auth_url: str = oauth_service.build_google_authorization_url(session)
    return RedirectResponse(url=auth_url, status_code=302)


@router.post("/token")
async def oauth_token(
    grant_type: str = Form(...),
    code: str | None = Form(default=None),
    redirect_uri: str | None = Form(default=None),
    code_verifier: str | None = Form(default=None),
    refresh_token: str | None = Form(default=None),
    db: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> JSONResponse:
    oauth_server: OAuthServerService = _build_oauth_server_service(db, settings)
    try:
        if grant_type == "authorization_code":
            if not code or not redirect_uri or not code_verifier:
                raise HTTPException(
                    status_code=400,
                    detail="code, redirect_uri, and code_verifier are required",
                )
            token_response = await oauth_server.exchange_authorization_code(
                code=code,
                redirect_uri=redirect_uri,
                code_verifier=code_verifier,
            )
        elif grant_type == "refresh_token":
            if not refresh_token:
                raise HTTPException(status_code=400, detail="refresh_token is required")
            token_response = await oauth_server.exchange_refresh_token(refresh_token)
        else:
            raise HTTPException(status_code=400, detail=f"Unsupported grant_type: {grant_type}")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    body: dict[str, object] = {
        "access_token": token_response.access_token,
        "token_type": token_response.token_type,
        "expires_in": token_response.expires_in,
        "scope": token_response.scope,
    }
    if token_response.refresh_token is not None:
        body["refresh_token"] = token_response.refresh_token
    return JSONResponse(body)


@router.get("/start/{session_id}", response_class=HTMLResponse)
async def oauth_start_page(
    request: Request,
    session_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> HTMLResponse:
    service: OAuthService = _build_oauth_service(db, settings)
    connect_session: ConnectSession | None = await service.get_session_by_id(session_id)
    if connect_session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    if connect_session.status == SessionStatus.CONNECTED.value:
        return templates.TemplateResponse(
            request=request,
            name="connected.html",
            context={"session_id": str(session_id)},
        )

    return templates.TemplateResponse(
        request=request,
        name="start.html",
        context={
            "session_id": str(session_id),
            "authorize_url": f"/oauth/authorize/{session_id}",
        },
    )


@router.get("/authorize/{session_id}")
async def oauth_authorize_redirect(
    session_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> RedirectResponse:
    service: OAuthService = _build_oauth_service(db, settings)
    connect_session: ConnectSession | None = await service.get_session_by_id(session_id)
    if connect_session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    if connect_session.status == SessionStatus.CONNECTED.value:
        return RedirectResponse(url=f"/oauth/complete/{session_id}", status_code=302)

    auth_url: str = service.build_google_authorization_url(connect_session)
    return RedirectResponse(url=auth_url, status_code=302)


@router.get("/callback")
async def oauth_callback(
    request: Request,
    code: str | None = Query(default=None),
    state: str | None = Query(default=None),
    error: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> HTMLResponse:
    if error:
        return templates.TemplateResponse(
            request=request,
            name="error.html",
            context={"message": f"Google OAuth error: {error}"},
            status_code=400,
        )

    if not code or not state:
        raise HTTPException(status_code=400, detail="Missing code or state")

    service: OAuthService = _build_oauth_service(db, settings)
    connect_session: ConnectSession | None = await service.get_session_by_state(state)
    if connect_session is None:
        raise HTTPException(status_code=400, detail="Invalid OAuth state")

    try:
        user, source = await service.complete_oauth(connect_session, code)
    except Exception as exc:
        await service.mark_session_failed(connect_session)
        if connect_session.oauth_redirect_uri:
            oauth_server: OAuthServerService = _build_oauth_server_service(db, settings)
            error_url: str = oauth_server.build_client_redirect_url(
                connect_session,
                error="server_error",
            )
            return RedirectResponse(url=error_url, status_code=302)
        return templates.TemplateResponse(
            request=request,
            name="error.html",
            context={"message": str(exc)},
            status_code=500,
        )

    schedule_source_sync(source.id)

    if connect_session.oauth_redirect_uri:
        oauth_server = _build_oauth_server_service(db, settings)
        scopes: list[str] = (
            list(connect_session.requested_scopes)
            if connect_session.requested_scopes
            else parse_scopes_param("")
        )
        auth_code: str = await oauth_server.create_authorization_code(
            connect_session,
            user.id,
            scopes,
        )
        redirect_url: str = oauth_server.build_client_redirect_url(
            connect_session,
            code=auth_code,
        )
        return RedirectResponse(url=redirect_url, status_code=302)

    return templates.TemplateResponse(
        request=request,
        name="complete.html",
        context={
            "email": user.email,
            "session_id": str(connect_session.id),
        },
    )


@router.get("/complete/{session_id}", response_class=HTMLResponse)
async def oauth_complete_page(
    request: Request,
    session_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> HTMLResponse:
    service: OAuthService = _build_oauth_service(db, settings)
    connect_session: ConnectSession | None = await service.get_session_by_id(session_id)
    if connect_session is None or connect_session.user_id is None:
        raise HTTPException(status_code=404, detail="Session not found or not connected")

    user: User | None = await db.get(User, connect_session.user_id)
    email: str = user.email if user else ""

    return templates.TemplateResponse(
        request=request,
        name="complete.html",
        context={"email": email, "session_id": str(session_id)},
    )
