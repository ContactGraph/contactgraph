import secrets
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from contactsafe_core.enums import OAuthProvider, SessionStatus, SourceType, SyncState
from contactsafe_core.schemas import ConnectSourceResult
from contactsafe_server.config import Settings
from contactsafe_server.db.models import ConnectSession, OAuthCredential, Source, User
from contactsafe_server.oauth.google import GoogleOAuthClient, GoogleTokens, GoogleUserInfo
from contactsafe_server.services.crypto import TokenEncryptor
from contactsafe_server.services.source_service import SourceService


class OAuthService:
    def __init__(
        self,
        db: AsyncSession,
        settings: Settings,
        encryptor: TokenEncryptor,
        google: GoogleOAuthClient,
    ) -> None:
        self._db: AsyncSession = db
        self._settings: Settings = settings
        self._encryptor: TokenEncryptor = encryptor
        self._google: GoogleOAuthClient = google
        self._sources: SourceService = SourceService(db)

    _GOOGLE_SOURCE_TYPES: frozenset[SourceType] = frozenset({
        SourceType.GOOGLE_MAIL,
        SourceType.GOOGLE_CONTACTS,
    })

    async def create_connect_session(
        self,
        user_token: str | None = None,
        source_type: SourceType = SourceType.GOOGLE_MAIL,
    ) -> ConnectSourceResult:
        """Start OAuth flow or return existing connection for a known user."""
        if source_type not in self._GOOGLE_SOURCE_TYPES:
            raise ValueError(f"connect_source not implemented for {source_type.value}")

        if user_token:
            existing: ConnectSourceResult | None = await self._check_existing_by_email(
                user_token
            )
            if existing is not None:
                return existing

        state: str = secrets.token_urlsafe(32)
        session: ConnectSession = ConnectSession(
            state=state,
            status=SessionStatus.PENDING.value,
            requested_scopes=list(self._settings.google_scopes),
        )
        self._db.add(session)
        await self._db.flush()

        oauth_url: str = self._settings.oauth_start_url_template.format(
            session_id=session.id
        )
        return ConnectSourceResult(
            connect_session_id=session.id,
            oauth_url=oauth_url,
            status=SessionStatus.PENDING,
            message="Open the OAuth URL in a browser to connect Gmail, Calendar, and Contacts.",
            already_connected=False,
        )

    async def get_session_by_id(self, session_id: uuid.UUID) -> ConnectSession | None:
        return await self._get_session(session_id)

    async def get_session_by_state(self, state: str) -> ConnectSession | None:
        result = await self._db.execute(
            select(ConnectSession).where(ConnectSession.state == state)
        )
        return result.scalar_one_or_none()

    def build_google_authorization_url(self, session: ConnectSession) -> str:
        return self._google.build_authorization_url(state=session.state)

    async def complete_oauth(self, session: ConnectSession, code: str) -> tuple[User, Source]:
        tokens: GoogleTokens = await self._google.exchange_code(code)
        userinfo: GoogleUserInfo = await self._google.fetch_userinfo(tokens.access_token)
        email: str = str(userinfo.get("email", "")).strip().lower()
        if not email:
            raise ValueError("Google account did not return an email address")

        user: User = await self._upsert_user(email, userinfo)
        cred: OAuthCredential = await self._upsert_credentials(user.id, tokens)
        source: Source = await self._sources.ensure_google_mail_source(user.id, email)
        await self._sources.link_credential_to_source(cred, source)

        await self._sources.ensure_google_contacts_source(user.id, email)

        session.user_id = user.id
        session.status = SessionStatus.CONNECTED.value
        session.completed_at = datetime.now(tz=UTC)
        await self._db.flush()
        return user, source

    async def mark_session_failed(self, session: ConnectSession) -> None:
        session.status = SessionStatus.FAILED.value
        session.completed_at = datetime.now(tz=UTC)
        await self._db.flush()

    async def _check_existing_by_email(self, email: str) -> ConnectSourceResult | None:
        normalized: str = email.strip().lower()
        result = await self._db.execute(select(User).where(User.email == normalized))
        user: User | None = result.scalar_one_or_none()
        if user is None:
            return None

        cred: OAuthCredential | None = await self._get_valid_credential(user.id)
        if cred is None:
            return None

        source: Source = await self._sources.ensure_google_mail_source(user.id, normalized)
        await self._sources.link_credential_to_source(cred, source)
        await self._sources.ensure_google_contacts_source(user.id, normalized)

        session: ConnectSession = ConnectSession(
            state=secrets.token_urlsafe(32),
            status=SessionStatus.CONNECTED.value,
            user_id=user.id,
            requested_scopes=list(cred.scopes),
            completed_at=datetime.now(tz=UTC),
        )
        self._db.add(session)
        await self._db.flush()

        if source.sync_state in {SyncState.PENDING.value, SyncState.FAILED.value} or (
            source.sync_error
        ):
            await self._sources.request_sync(source.id)

        return ConnectSourceResult(
            connect_session_id=session.id,
            oauth_url="",
            status=SessionStatus.CONNECTED,
            message="Gmail and Calendar are already connected for this account.",
            already_connected=True,
            email=user.email,
            scopes=list(cred.scopes),
            source_id=source.id,
        )

    async def _upsert_user(self, email: str, userinfo: GoogleUserInfo) -> User:
        result = await self._db.execute(select(User).where(User.email == email))
        existing: User | None = result.scalar_one_or_none()
        if existing is not None:
            existing.google_profile_name = userinfo.get("name")
            existing.google_profile_picture = userinfo.get("picture")
            return existing

        user = User(
            email=email,
            google_profile_name=userinfo.get("name"),
            google_profile_picture=userinfo.get("picture"),
        )
        self._db.add(user)
        await self._db.flush()
        return user

    async def _upsert_credentials(
        self, user_id: uuid.UUID, tokens: GoogleTokens
    ) -> OAuthCredential:
        result = await self._db.execute(
            select(OAuthCredential).where(
                OAuthCredential.user_id == user_id,
                OAuthCredential.provider == OAuthProvider.GOOGLE.value,
            )
        )
        existing: OAuthCredential | None = result.scalar_one_or_none()
        access_encrypted: bytes = self._encryptor.encrypt(tokens.access_token)
        refresh_encrypted: bytes = self._encryptor.encrypt(tokens.refresh_token)

        if existing is not None:
            existing.access_token_encrypted = access_encrypted
            existing.refresh_token_encrypted = refresh_encrypted
            existing.token_expires_at = tokens.expires_at
            existing.scopes = tokens.scopes
            existing.is_valid = True
            return existing

        cred = OAuthCredential(
            user_id=user_id,
            provider=OAuthProvider.GOOGLE.value,
            access_token_encrypted=access_encrypted,
            refresh_token_encrypted=refresh_encrypted,
            token_expires_at=tokens.expires_at,
            scopes=tokens.scopes,
            is_valid=True,
        )
        self._db.add(cred)
        await self._db.flush()
        return cred

    async def _get_valid_credential(self, user_id: uuid.UUID) -> OAuthCredential | None:
        result = await self._db.execute(
            select(OAuthCredential).where(
                OAuthCredential.user_id == user_id,
                OAuthCredential.provider == OAuthProvider.GOOGLE.value,
                OAuthCredential.is_valid.is_(True),
            )
        )
        return result.scalar_one_or_none()

    async def _get_session(self, session_id: uuid.UUID) -> ConnectSession | None:
        return await self._db.get(ConnectSession, session_id)
