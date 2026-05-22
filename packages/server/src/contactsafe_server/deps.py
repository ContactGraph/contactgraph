from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from contactsafe_server.config import Settings, get_settings
from contactsafe_server.db.connection import get_session_factory
from contactsafe_server.oauth.google import GoogleOAuthClient
from contactsafe_server.services.crypto import TokenEncryptor
from contactsafe_server.services.oauth_service import OAuthService


@dataclass(frozen=True, slots=True)
class AppContext:
    settings: Settings
    session_factory: async_sessionmaker[AsyncSession]
    encryptor: TokenEncryptor


def build_app_context() -> AppContext:
    settings: Settings = get_settings()
    return AppContext(
        settings=settings,
        session_factory=get_session_factory(settings),
        encryptor=TokenEncryptor(settings.token_encryption_key),
    )


def build_oauth_service(db: AsyncSession, ctx: AppContext) -> OAuthService:
    google: GoogleOAuthClient = GoogleOAuthClient(ctx.settings)
    return OAuthService(
        db=db,
        settings=ctx.settings,
        encryptor=ctx.encryptor,
        google=google,
    )
