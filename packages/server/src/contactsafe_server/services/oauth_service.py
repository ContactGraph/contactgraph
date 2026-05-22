import secrets
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from contactsafe_core.enums import ImportState, OAuthProvider, SessionStatus
from contactsafe_core.schemas import ConnectGmailResult, ImportStatus
from contactsafe_server.config import Settings
from contactsafe_server.db.models import ConnectSession, OAuthCredential, User
from contactsafe_server.oauth.google import GoogleOAuthClient, GoogleTokens, GoogleUserInfo
from contactsafe_server.services.crypto import TokenEncryptor


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

    async def create_connect_session(self, user_token: str | None = None) -> ConnectGmailResult:
        """Start OAuth flow or return existing connection for a known user."""
        if user_token:
            existing: ConnectGmailResult | None = await self._check_existing_by_email(user_token)
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

        oauth_url: str = self._settings.oauth_start_url_template.format(session_id=session.id)
        return ConnectGmailResult(
            session_id=session.id,
            oauth_url=oauth_url,
            status=SessionStatus.PENDING,
            message="Open the OAuth URL in a browser to connect Gmail and Calendar.",
            already_connected=False,
        )

    async def get_import_status(self, session_id: uuid.UUID) -> ImportStatus:
        session: ConnectSession | None = await self._get_session(session_id)
        if session is None:
            raise ValueError(f"Unknown session_id: {session_id}")

        status: SessionStatus = SessionStatus(session.status)
        email: str | None = None
        scopes: list[str] = list(session.requested_scopes)

        if session.user_id is not None:
            user: User | None = await self._db.get(User, session.user_id)
            if user is not None:
                email = user.email
            cred: OAuthCredential | None = await self._get_valid_credential(session.user_id)
            if cred is not None:
                scopes = list(cred.scopes)

        import_state: ImportState = ImportState.PENDING
        contacts_found: int = 0
        contacts_resolved: int = 0
        contacts_pending: int = 0
        message: str = self._status_message(status, ImportState.PENDING)

        if session.user_id is not None:
            user_row: User | None = await self._db.get(User, session.user_id)
            if user_row is not None:
                import_state = ImportState(user_row.import_state)
                contacts_found = user_row.contacts_found
                contacts_resolved = user_row.contacts_resolved
                contacts_pending = user_row.contacts_pending
                message = self._import_message(status, user_row)

        return ImportStatus(
            session_id=session.id,
            status=status,
            import_state=import_state,
            email=email,
            scopes=scopes,
            contacts_found=contacts_found,
            contacts_resolved=contacts_resolved,
            contacts_pending=contacts_pending,
            message=message,
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

    async def complete_oauth(self, session: ConnectSession, code: str) -> User:
        tokens: GoogleTokens = await self._google.exchange_code(code)
        userinfo: GoogleUserInfo = await self._google.fetch_userinfo(tokens.access_token)
        email: str = str(userinfo.get("email", "")).strip().lower()
        if not email:
            raise ValueError("Google account did not return an email address")

        user: User = await self._upsert_user(email, userinfo)
        await self._upsert_credentials(user.id, tokens)

        session.user_id = user.id
        session.status = SessionStatus.CONNECTED.value
        session.completed_at = datetime.now(tz=UTC)
        await self._db.flush()
        return user

    async def mark_session_failed(self, session: ConnectSession) -> None:
        session.status = SessionStatus.FAILED.value
        session.completed_at = datetime.now(tz=UTC)
        await self._db.flush()

    async def _check_existing_by_email(self, email: str) -> ConnectGmailResult | None:
        normalized: str = email.strip().lower()
        result = await self._db.execute(select(User).where(User.email == normalized))
        user: User | None = result.scalar_one_or_none()
        if user is None:
            return None

        cred: OAuthCredential | None = await self._get_valid_credential(user.id)
        if cred is None:
            return None

        session: ConnectSession = ConnectSession(
            state=secrets.token_urlsafe(32),
            status=SessionStatus.CONNECTED.value,
            user_id=user.id,
            requested_scopes=list(cred.scopes),
            completed_at=datetime.now(tz=UTC),
        )
        self._db.add(session)
        await self._db.flush()

        return ConnectGmailResult(
            session_id=session.id,
            oauth_url="",
            status=SessionStatus.CONNECTED,
            message="Gmail and Calendar are already connected for this account.",
            already_connected=True,
            email=user.email,
            scopes=list(cred.scopes),
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

    async def _upsert_credentials(self, user_id: uuid.UUID, tokens: GoogleTokens) -> None:
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
            return

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

    @staticmethod
    def _status_message(status: SessionStatus, import_state: ImportState) -> str:
        if status == SessionStatus.PENDING:
            return "Waiting for Google OAuth. Open the connect URL and authorize access."
        if status == SessionStatus.FAILED:
            return "OAuth failed. Call connect_gmail again to retry."
        if status == SessionStatus.CONNECTED:
            return f"Google account connected. Import status: {import_state.value}."
        return "Unknown status."

    @staticmethod
    def _import_message(status: SessionStatus, user: User) -> str:
        if status != SessionStatus.CONNECTED:
            return OAuthService._status_message(status, ImportState(user.import_state))
        if user.import_error:
            return f"Import failed: {user.import_error}"
        match ImportState(user.import_state):
            case ImportState.IMPORTING:
                return (
                    f"Importing contacts from Gmail ({user.contacts_resolved}/"
                    f"{user.contacts_found} resolved)..."
                )
            case ImportState.PARTIAL:
                return (
                    f"Partial graph ready ({user.contacts_resolved} contacts). "
                    "Import continuing in background."
                )
            case ImportState.COMPLETE:
                return f"Import complete. {user.contacts_resolved} contacts in your graph."
            case _:
                return "Google connected. Gmail import starting..."
