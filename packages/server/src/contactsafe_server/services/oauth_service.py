import secrets
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from contactsafe_core.enums import IdentityKind, OAuthProvider, SessionStatus, SourceType, SyncState
from contactsafe_core.schemas import ConnectSourceResult
from contactsafe_server.config import Settings
from contactsafe_server.db.models import ConnectSession, OAuthCredential, Source, User, UserIdentity
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
        SourceType.GOOGLE_CONTACTS,  # deprecated alias; treated as google_mail
        SourceType.GOOGLE_CALENDAR,
    })

    async def create_connect_session(
        self,
        user_token: str | None = None,
        source_type: SourceType = SourceType.GOOGLE_MAIL,
        *,
        authenticated_user_id: uuid.UUID | None = None,
    ) -> ConnectSourceResult:
        """Start OAuth flow or return existing connection for a known user.

        When ``authenticated_user_id`` is provided the new Google account will
        be linked to the existing user on callback (add-another-account flow).
        """
        if source_type not in self._GOOGLE_SOURCE_TYPES:
            raise ValueError(f"connect_source not implemented for {source_type.value}")

        if source_type == SourceType.GOOGLE_CONTACTS:
            source_type = SourceType.GOOGLE_MAIL

        if user_token:
            existing: ConnectSourceResult | None = await self._check_existing_by_email(
                user_token,
                source_type=source_type,
            )
            if existing is not None:
                return existing

        state: str = secrets.token_urlsafe(32)
        session: ConnectSession = ConnectSession(
            state=state,
            status=SessionStatus.PENDING.value,
            requested_scopes=list(self._settings.google_scopes),
            user_id=authenticated_user_id,
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

        user: User = await self._resolve_or_create_user(email, userinfo, session)
        cred: OAuthCredential = await self._upsert_credentials(user.id, email, tokens)
        mail_source: Source = await self._sources.ensure_google_mail_source(user.id, email)
        await self._sources.link_credential_to_source(cred, mail_source)
        await self._sources.ensure_google_calendar_source(user.id, email)

        session.user_id = user.id
        session.status = SessionStatus.CONNECTED.value
        session.completed_at = datetime.now(tz=UTC)
        await self._db.flush()
        return user, mail_source

    async def mark_session_failed(self, session: ConnectSession) -> None:
        session.status = SessionStatus.FAILED.value
        session.completed_at = datetime.now(tz=UTC)
        await self._db.flush()

    async def _check_existing_by_email(
        self,
        email: str,
        *,
        source_type: SourceType = SourceType.GOOGLE_MAIL,
    ) -> ConnectSourceResult | None:
        normalized: str = email.strip().lower()
        user: User | None = await self._find_user_by_email(normalized)
        if user is None:
            return None

        cred: OAuthCredential | None = await self._get_valid_credential(
            user.id, external_account_id=normalized,
        )
        if cred is None:
            return None

        mail_source: Source = await self._sources.ensure_google_mail_source(user.id, normalized)
        await self._sources.link_credential_to_source(cred, mail_source)
        calendar_source: Source = await self._sources.ensure_google_calendar_source(
            user.id, normalized
        )

        target_source: Source = (
            calendar_source if source_type == SourceType.GOOGLE_CALENDAR else mail_source
        )

        session: ConnectSession = ConnectSession(
            state=secrets.token_urlsafe(32),
            status=SessionStatus.CONNECTED.value,
            user_id=user.id,
            requested_scopes=list(cred.scopes),
            completed_at=datetime.now(tz=UTC),
        )
        self._db.add(session)
        await self._db.flush()

        if target_source.sync_state in {SyncState.PENDING.value, SyncState.FAILED.value} or (
            target_source.sync_error
        ):
            await self._sources.request_sync(target_source.id)

        label: str = (
            "Google Calendar"
            if source_type == SourceType.GOOGLE_CALENDAR
            else "Gmail"
        )
        return ConnectSourceResult(
            connect_session_id=session.id,
            oauth_url="",
            status=SessionStatus.CONNECTED,
            message=f"{label} is already connected for this account.",
            already_connected=True,
            email=user.email,
            scopes=list(cred.scopes),
            source_id=target_source.id,
        )

    async def _find_user_by_email(self, email: str) -> User | None:
        """Look up a user via the user_identities table."""
        result = await self._db.execute(
            select(User).join(UserIdentity).where(
                UserIdentity.kind == IdentityKind.EMAIL.value,
                UserIdentity.value == email,
            )
        )
        return result.scalar_one_or_none()

    async def _resolve_or_create_user(
        self,
        email: str,
        userinfo: GoogleUserInfo,
        session: ConnectSession,
    ) -> User:
        """Resolve an existing user via identity lookup, or create a new one.

        Three cases:
        1. Email already in user_identities -> return that user (reconnect / known link).
        2. Email unknown + session has user_id -> link email to existing user (add account).
        3. Email unknown + no session user_id -> create new user + identity (signup).
        """
        existing_user: User | None = await self._find_user_by_email(email)
        if existing_user is not None:
            existing_user.google_profile_name = userinfo.get("name")
            existing_user.google_profile_picture = userinfo.get("picture")
            return existing_user

        if session.user_id is not None:
            user = await self._db.get(User, session.user_id)
            if user is None:
                raise ValueError("Session references a non-existent user")
            identity = UserIdentity(
                user_id=user.id,
                kind=IdentityKind.EMAIL.value,
                value=email,
                is_primary=False,
                verified_at=datetime.now(tz=UTC),
            )
            self._db.add(identity)
            await self._db.flush()
            return user

        user = User(
            email=email,
            google_profile_name=userinfo.get("name"),
            google_profile_picture=userinfo.get("picture"),
        )
        self._db.add(user)
        await self._db.flush()
        identity = UserIdentity(
            user_id=user.id,
            kind=IdentityKind.EMAIL.value,
            value=email,
            is_primary=True,
            verified_at=datetime.now(tz=UTC),
        )
        self._db.add(identity)
        await self._db.flush()
        return user

    async def _upsert_credentials(
        self, user_id: uuid.UUID, external_account_id: str, tokens: GoogleTokens,
    ) -> OAuthCredential:
        result = await self._db.execute(
            select(OAuthCredential).where(
                OAuthCredential.user_id == user_id,
                OAuthCredential.provider == OAuthProvider.GOOGLE.value,
                OAuthCredential.external_account_id == external_account_id,
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
            external_account_id=external_account_id,
            access_token_encrypted=access_encrypted,
            refresh_token_encrypted=refresh_encrypted,
            token_expires_at=tokens.expires_at,
            scopes=tokens.scopes,
            is_valid=True,
        )
        self._db.add(cred)
        await self._db.flush()
        return cred

    async def _get_valid_credential(
        self,
        user_id: uuid.UUID,
        *,
        external_account_id: str | None = None,
    ) -> OAuthCredential | None:
        """Find a valid Google credential, optionally scoped to a specific account."""
        query = select(OAuthCredential).where(
            OAuthCredential.user_id == user_id,
            OAuthCredential.provider == OAuthProvider.GOOGLE.value,
            OAuthCredential.is_valid.is_(True),
        )
        if external_account_id is not None:
            query = query.where(
                OAuthCredential.external_account_id == external_account_id,
            )
        result = await self._db.execute(query.limit(1))
        return result.scalar_one_or_none()

    async def _get_session(self, session_id: uuid.UUID) -> ConnectSession | None:
        return await self._db.get(ConnectSession, session_id)
