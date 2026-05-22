import uuid
from collections.abc import AsyncGenerator
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from contactsafe_core.enums import SessionStatus
from contactsafe_server.config import Settings, get_settings
from contactsafe_server.db.connection import get_session_factory
from contactsafe_server.db.models import ConnectSession, User
from contactsafe_server.oauth.google import GoogleOAuthClient
from contactsafe_server.services.crypto import TokenEncryptor
from contactsafe_server.services.import_scheduler import schedule_source_sync
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


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    factory = get_session_factory()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


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
        return templates.TemplateResponse(
            request=request,
            name="error.html",
            context={"message": str(exc)},
            status_code=500,
        )

    schedule_source_sync(source.id)

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
