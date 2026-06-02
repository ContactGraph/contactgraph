from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from contactsafe_server.config import Settings, get_settings
from contactsafe_server.db.connection import get_session_factory
from contactsafe_server.oauth.google import GoogleOAuthClient
from contactsafe_server.services.crypto import TokenEncryptor
from contactsafe_server.services.jwt_service import JWTService
from contactsafe_server.services.enrichment_service import EnrichmentService
from contactsafe_server.services.oauth_service import OAuthService
from contactsafe_server.services.oauth_server_service import OAuthServerService
from contactsafe_server.services.source_service import SourceService


@dataclass(frozen=True, slots=True)
class AppContext:
    settings: Settings
    session_factory: async_sessionmaker[AsyncSession]
    encryptor: TokenEncryptor
    jwt_service: JWTService


def build_jwt_service(settings: Settings | None = None) -> JWTService:
    cfg: Settings = settings or get_settings()
    return JWTService(cfg)


def build_app_context() -> AppContext:
    settings: Settings = get_settings()
    return AppContext(
        settings=settings,
        session_factory=get_session_factory(settings),
        encryptor=TokenEncryptor(settings.token_encryption_key),
        jwt_service=build_jwt_service(settings),
    )


def build_oauth_service(db: AsyncSession, ctx: AppContext) -> OAuthService:
    google: GoogleOAuthClient = GoogleOAuthClient(ctx.settings)
    return OAuthService(
        db=db,
        settings=ctx.settings,
        encryptor=ctx.encryptor,
        google=google,
    )


def build_oauth_server_service(db: AsyncSession, ctx: AppContext) -> OAuthServerService:
    return OAuthServerService(
        db=db,
        settings=ctx.settings,
        jwt_service=ctx.jwt_service,
    )


def build_source_service(db: AsyncSession) -> SourceService:
    return SourceService(db)


def build_enrichment_service(db: AsyncSession) -> EnrichmentService:
    return EnrichmentService(db)
