import logging
import uuid
from datetime import UTC, datetime

from sqlalchemy import exists, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from contactsafe_core.enums import (
    OAuthProvider,
    SessionStatus,
    SourceConnectionStatus,
    SourceType,
    SyncState,
)
from contactsafe_core.schemas import (
    ListSourcesResult,
    SourceStatusResult,
    SourceSummary,
    SyncSourceResult,
)
from contactsafe_server.db.models import ConnectSession, OAuthCredential, Source, User

logger: logging.Logger = logging.getLogger(__name__)

_SYNCABLE_SOURCE_TYPES: frozenset[SourceType] = frozenset({
    SourceType.GOOGLE_MAIL,
    SourceType.GOOGLE_CALENDAR,
    SourceType.PHONE_CONTACTS_UPLOAD,
    SourceType.LINKEDIN_CONNECTIONS_UPLOAD,
    SourceType.LINKEDIN_PROFILE_UPLOAD,
})

_OAUTH_SOURCE_TYPES: frozenset[SourceType] = frozenset({
    SourceType.GOOGLE_MAIL,
    SourceType.GOOGLE_CALENDAR,
})

from contactsafe_server.services.crypto import TokenEncryptor
from contactsafe_server.services.upload_payload_crypto import build_upload_payload
from contactsafe_server.services.import_scheduler import (
    is_source_sync_running,
    release_sync_lock,
    schedule_source_sync,
)


class SourceService:
    def __init__(self, db: AsyncSession) -> None:
        self._db: AsyncSession = db

    async def ensure_google_contacts_source(self, user_id: uuid.UUID, email: str) -> Source:
        normalized: str = email.strip().lower()
        result = await self._db.execute(
            select(Source).where(
                Source.user_id == user_id,
                Source.source_type == SourceType.GOOGLE_CONTACTS.value,
                Source.external_account_id == normalized,
            )
        )
        existing: Source | None = result.scalar_one_or_none()
        if existing is not None:
            existing.connection_status = SourceConnectionStatus.CONNECTED.value
            existing.label = f"{normalized} (contacts)"
            await self._db.flush()
            return existing

        source = Source(
            user_id=user_id,
            source_type=SourceType.GOOGLE_CONTACTS.value,
            label=f"{normalized} (contacts)",
            external_account_id=normalized,
            connection_status=SourceConnectionStatus.CONNECTED.value,
            sync_state=SyncState.PENDING.value,
        )
        self._db.add(source)
        await self._db.flush()
        return source

    async def ensure_google_mail_source(self, user_id: uuid.UUID, email: str) -> Source:
        normalized: str = email.strip().lower()
        result = await self._db.execute(
            select(Source).where(
                Source.user_id == user_id,
                Source.source_type == SourceType.GOOGLE_MAIL.value,
                Source.external_account_id == normalized,
            )
        )
        existing: Source | None = result.scalar_one_or_none()
        if existing is not None:
            existing.connection_status = SourceConnectionStatus.CONNECTED.value
            existing.label = normalized
            await self._db.flush()
            return existing

        source = Source(
            user_id=user_id,
            source_type=SourceType.GOOGLE_MAIL.value,
            label=normalized,
            external_account_id=normalized,
            connection_status=SourceConnectionStatus.CONNECTED.value,
            sync_state=SyncState.PENDING.value,
        )
        self._db.add(source)
        await self._db.flush()
        return source

    async def ensure_google_calendar_source(self, user_id: uuid.UUID, email: str) -> Source:
        normalized: str = email.strip().lower()
        result = await self._db.execute(
            select(Source).where(
                Source.user_id == user_id,
                Source.source_type == SourceType.GOOGLE_CALENDAR.value,
                Source.external_account_id == normalized,
            )
        )
        existing: Source | None = result.scalar_one_or_none()
        if existing is not None:
            existing.connection_status = SourceConnectionStatus.CONNECTED.value
            existing.label = f"{normalized} (calendar)"
            await self._db.flush()
            return existing

        source = Source(
            user_id=user_id,
            source_type=SourceType.GOOGLE_CALENDAR.value,
            label=f"{normalized} (calendar)",
            external_account_id=normalized,
            connection_status=SourceConnectionStatus.CONNECTED.value,
            sync_state=SyncState.PENDING.value,
        )
        self._db.add(source)
        await self._db.flush()
        return source

    async def ensure_phone_contacts_source(self, user_id: uuid.UUID, email: str) -> Source:
        normalized: str = email.strip().lower()
        result = await self._db.execute(
            select(Source).where(
                Source.user_id == user_id,
                Source.source_type == SourceType.PHONE_CONTACTS_UPLOAD.value,
                Source.external_account_id == normalized,
            )
        )
        existing: Source | None = result.scalar_one_or_none()
        if existing is not None:
            existing.connection_status = SourceConnectionStatus.CONNECTED.value
            existing.label = "Phone contacts"
            await self._db.flush()
            return existing

        source = Source(
            user_id=user_id,
            source_type=SourceType.PHONE_CONTACTS_UPLOAD.value,
            label="Phone contacts",
            external_account_id=normalized,
            connection_status=SourceConnectionStatus.CONNECTED.value,
            sync_state=SyncState.PENDING.value,
        )
        self._db.add(source)
        await self._db.flush()
        return source

    async def ensure_upload_source(
        self,
        user_id: uuid.UUID,
        *,
        source_type: SourceType,
        filename: str,
        content: str,
        encryptor: TokenEncryptor | None = None,
    ) -> Source:
        if source_type not in {
            SourceType.PHONE_CONTACTS_UPLOAD,
            SourceType.LINKEDIN_CONNECTIONS_UPLOAD,
            SourceType.LINKEDIN_PROFILE_UPLOAD,
        }:
            raise ValueError(f"Upload not supported for {source_type.value}")

        external_id: str = f"upload:{filename.strip().lower()}"
        result = await self._db.execute(
            select(Source).where(
                Source.user_id == user_id,
                Source.source_type == source_type.value,
                Source.external_account_id == external_id,
            )
        )
        existing: Source | None = result.scalar_one_or_none()
        upload_labels: dict[SourceType, str] = {
            SourceType.PHONE_CONTACTS_UPLOAD: "Phone contacts",
            SourceType.LINKEDIN_CONNECTIONS_UPLOAD: "LinkedIn connections",
            SourceType.LINKEDIN_PROFILE_UPLOAD: "LinkedIn profile",
        }
        label: str = upload_labels[source_type]
        if encryptor is None:
            raise ValueError("encryptor is required for upload sources")
        payload: dict[str, object] = build_upload_payload(
            filename=filename,
            content=content,
            encryptor=encryptor,
        )

        if existing is not None:
            existing.upload_payload = payload
            existing.connection_status = SourceConnectionStatus.CONNECTED.value
            existing.sync_state = SyncState.PENDING.value
            existing.sync_error = None
            existing.contacts_found = 0
            existing.contacts_resolved = 0
            existing.contacts_pending = 0
            await self._db.flush()
            return existing

        source = Source(
            user_id=user_id,
            source_type=source_type.value,
            label=label,
            external_account_id=external_id,
            connection_status=SourceConnectionStatus.CONNECTED.value,
            sync_state=SyncState.PENDING.value,
            upload_payload=payload,
        )
        self._db.add(source)
        await self._db.flush()
        return source

    async def link_credential_to_source(
        self,
        credential: OAuthCredential,
        source: Source,
    ) -> None:
        credential.source_id = source.id
        await self._db.flush()

    async def list_sources_for_user(self, user_id: uuid.UUID) -> ListSourcesResult:
        result = await self._db.execute(
            select(Source)
            .where(Source.user_id == user_id)
            .order_by(Source.created_at)
        )
        sources: list[Source] = list(result.scalars().all())
        for source in sources:
            await self._recover_orphaned_sync(source)
        visible_sources: list[Source] = [
            source
            for source in sources
            if source.source_type != SourceType.GOOGLE_CONTACTS.value
        ]
        if visible_sources:
            await self._db.flush()
        if not visible_sources:
            return ListSourcesResult(
                sources=[],
                message="No data sources connected yet. Call connect_source first.",
            )
        return ListSourcesResult(
            sources=[self._to_summary(s) for s in visible_sources],
            message=f"Found {len(visible_sources)} source(s).",
        )

    async def require_source_owned_by(
        self,
        source_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> Source:
        source: Source | None = await self._db.get(Source, source_id)
        if source is None or source.user_id != user_id:
            raise ValueError(f"Unknown source_id: {source_id}")
        return source

    async def get_source_status(
        self,
        source_id: uuid.UUID,
        *,
        connect_session_id: uuid.UUID | None = None,
    ) -> SourceStatusResult:
        source: Source | None = await self._db.get(Source, source_id)
        if source is None:
            raise ValueError(f"Unknown source_id: {source_id}")

        session_status: SessionStatus = SessionStatus.PENDING
        if connect_session_id is not None:
            session: ConnectSession | None = await self._db.get(
                ConnectSession, connect_session_id
            )
            if session is not None:
                session_status = SessionStatus(session.status)

        user: User | None = await self._db.get(User, source.user_id)
        email: str | None = user.email if user is not None else None
        scopes: list[str] = []
        cred: OAuthCredential | None = await self._get_credential_for_source(source)
        if cred is not None:
            scopes = list(cred.scopes)

        sync_state: SyncState = SyncState(source.sync_state)
        return SourceStatusResult(
            source_id=source.id,
            connect_session_id=connect_session_id,
            status=session_status,
            connection_status=SourceConnectionStatus(source.connection_status),
            sync_state=sync_state,
            email=email,
            scopes=scopes,
            contacts_found=source.contacts_found,
            contacts_resolved=source.contacts_resolved,
            contacts_pending=source.contacts_pending,
            message=self._sync_message(source),
        )

    async def get_source_status_for_connect_session(
        self,
        connect_session_id: uuid.UUID,
    ) -> SourceStatusResult:
        session: ConnectSession | None = await self._db.get(ConnectSession, connect_session_id)
        if session is None:
            raise ValueError(f"Unknown connect_session_id: {connect_session_id}")

        session_status: SessionStatus = SessionStatus(session.status)
        if session.user_id is None:
            return SourceStatusResult(
                source_id=connect_session_id,
                connect_session_id=connect_session_id,
                status=session_status,
                connection_status=SourceConnectionStatus.PENDING_OAUTH,
                sync_state=SyncState.PENDING,
                message=self._oauth_session_message(session_status),
            )

        source: Source | None = await self._get_default_google_mail_source(session.user_id)
        if source is None:
            user: User | None = await self._db.get(User, session.user_id)
            return SourceStatusResult(
                source_id=connect_session_id,
                connect_session_id=connect_session_id,
                status=session_status,
                connection_status=SourceConnectionStatus.PENDING_OAUTH,
                sync_state=SyncState.PENDING,
                email=user.email if user is not None else None,
                message="OAuth connected but no mail source record yet. Call sync_source.",
            )

        result = await self.get_source_status(
            source.id,
            connect_session_id=connect_session_id,
        )
        result.status = session_status
        if session_status != SessionStatus.CONNECTED:
            result.message = self._oauth_session_message(session_status)
        return result

    async def get_source_status_for_user(self, user_id: uuid.UUID) -> SourceStatusResult:
        source: Source | None = await self._get_default_google_mail_source(user_id)
        if source is None:
            user: User | None = await self._db.get(User, user_id)
            return SourceStatusResult(
                source_id=user_id,
                status=SessionStatus.CONNECTED,
                connection_status=SourceConnectionStatus.PENDING_OAUTH,
                sync_state=SyncState.PENDING,
                email=user.email if user is not None else None,
                message="OAuth connected but no mail source record yet. Call sync_source.",
            )
        result = await self.get_source_status(source.id)
        result.status = SessionStatus.CONNECTED
        return result

    async def request_sync_for_user(self, user_id: uuid.UUID) -> SyncSourceResult:
        result = await self._db.execute(
            select(Source)
            .where(
                Source.user_id == user_id,
                Source.source_type == SourceType.GOOGLE_MAIL.value,
            )
            .order_by(Source.created_at)
        )
        sources: list[Source] = list(result.scalars().all())
        if not sources:
            raise ValueError("No google_mail source for this user")
        last_result: SyncSourceResult | None = None
        for source in sources:
            last_result = await self.request_sync(source.id)
        assert last_result is not None
        return last_result

    async def resolve_source_id(
        self,
        *,
        source_id: uuid.UUID | None = None,
        connect_session_id: uuid.UUID | None = None,
        user_id: uuid.UUID | None = None,
    ) -> uuid.UUID:
        if source_id is not None:
            source: Source | None = await self._db.get(Source, source_id)
            if source is None:
                raise ValueError(f"Unknown source_id: {source_id}")
            return source_id

        if user_id is not None:
            source = await self._get_default_google_mail_source(user_id)
            if source is None:
                raise ValueError("No google_mail source for this user")
            return source.id

        if connect_session_id is None:
            raise ValueError("Provide source_id, user_id, or connect_session_id")

        session: ConnectSession | None = await self._db.get(ConnectSession, connect_session_id)
        if session is None:
            raise ValueError(f"Unknown connect_session_id: {connect_session_id}")
        if session.user_id is None:
            raise ValueError("Connect session has no linked user yet")

        source = await self._get_default_google_mail_source(session.user_id)
        if source is None:
            raise ValueError("No google_mail source for this user")
        return source.id

    async def resolve_user_id(
        self,
        *,
        source_id: uuid.UUID | None = None,
        connect_session_id: uuid.UUID | None = None,
        user_id: uuid.UUID | None = None,
    ) -> uuid.UUID:
        if user_id is not None:
            return user_id
        resolved_source_id: uuid.UUID = await self.resolve_source_id(
            source_id=source_id,
            connect_session_id=connect_session_id,
        )
        source: Source | None = await self._db.get(Source, resolved_source_id)
        if source is None:
            raise ValueError(f"Unknown source_id: {resolved_source_id}")
        return source.user_id

    async def request_sync(self, source_id: uuid.UUID) -> SyncSourceResult:
        source: Source | None = await self._db.get(Source, source_id)
        if source is None:
            raise ValueError(f"Unknown source_id: {source_id}")

        source = await self._resolve_gmail_sync_source(source)

        try:
            parsed_type: SourceType = SourceType(source.source_type)
        except ValueError:
            return SyncSourceResult(
                source_id=source.id,
                scheduled=False,
                sync_state=SyncState(source.sync_state),
                message=f"Sync not implemented for source type {source.source_type}.",
            )

        if parsed_type not in _SYNCABLE_SOURCE_TYPES:
            return SyncSourceResult(
                source_id=source.id,
                scheduled=False,
                sync_state=SyncState(source.sync_state),
                message=f"Sync not implemented for source type {source.source_type}.",
            )

        if source.connection_status != SourceConnectionStatus.CONNECTED.value:
            return SyncSourceResult(
                source_id=source.id,
                scheduled=False,
                sync_state=SyncState(source.sync_state),
                message="Source is not connected. Call connect_source first.",
            )

        if parsed_type in _OAUTH_SOURCE_TYPES:
            cred: OAuthCredential | None = await self._get_credential_for_source(source)
            if cred is None:
                return SyncSourceResult(
                    source_id=source.id,
                    scheduled=False,
                    sync_state=SyncState(source.sync_state),
                    message=(
                        "No valid credentials for this source. "
                        "Call connect_source with your email as user_token to reconnect."
                    ),
                )
        elif source.upload_payload is None:
            return SyncSourceResult(
                source_id=source.id,
                scheduled=False,
                sync_state=SyncState(source.sync_state),
                message="Upload a file before syncing this source.",
            )

        user: User | None = await self._db.get(User, source.user_id)
        email: str | None = user.email if user is not None else None
        user_id: uuid.UUID = source.user_id

        await self._recover_orphaned_sync(source)

        if self._sync_in_progress(source, user_id):
            logger.info("request_sync blocked: sync in progress for source %s / user %s", source.id, user_id)
            await self._db.refresh(source)
            return SyncSourceResult(
                source_id=source.id,
                scheduled=False,
                sync_state=SyncState(source.sync_state),
                email=email,
                message="Sync is already running for this source. Poll get_source_status.",
            )

        if not schedule_source_sync(source.id, user_id):
            logger.info("request_sync blocked: schedule_source_sync returned False for source %s", source.id)
            return SyncSourceResult(
                source_id=source.id,
                scheduled=False,
                sync_state=SyncState(source.sync_state),
                email=email,
                message="Sync is already running for this source. Poll get_source_status.",
            )

        claimed: bool = await self._try_claim_sync(source)
        if not claimed:
            logger.info("request_sync blocked: _try_claim_sync failed for source %s (sync_state=%s)", source.id, source.sync_state)
            release_sync_lock(source.id, user_id)
            await self._db.refresh(source)
            return SyncSourceResult(
                source_id=source.id,
                scheduled=False,
                sync_state=SyncState(source.sync_state),
                email=email,
                message="Sync is already running for this source. Poll get_source_status.",
            )

        return SyncSourceResult(
            source_id=source.id,
            scheduled=True,
            sync_state=SyncState.SYNCING,
            email=email,
            message=(
                "Sync started in the background. "
                "Poll get_source_status until sync_state is partial or complete."
            ),
        )

    async def request_sync_for_connect_session(
        self,
        connect_session_id: uuid.UUID,
    ) -> SyncSourceResult:
        session: ConnectSession | None = await self._db.get(ConnectSession, connect_session_id)
        if session is None:
            raise ValueError(f"Unknown connect_session_id: {connect_session_id}")

        if SessionStatus(session.status) != SessionStatus.CONNECTED:
            return SyncSourceResult(
                source_id=connect_session_id,
                scheduled=False,
                sync_state=SyncState.PENDING,
                message="Source is not connected for this session. Call connect_source first.",
            )

        if session.user_id is None:
            return SyncSourceResult(
                source_id=connect_session_id,
                scheduled=False,
                sync_state=SyncState.PENDING,
                message="Session has no linked user. Complete OAuth before syncing.",
            )

        source_id: uuid.UUID = await self.resolve_source_id(
            connect_session_id=connect_session_id
        )
        return await self.request_sync(source_id)

    async def user_has_queryable_graph(self, user_id: uuid.UUID) -> bool:
        result = await self._db.execute(
            select(Source).where(
                Source.user_id == user_id,
                Source.source_type.in_([
                    SourceType.GOOGLE_MAIL.value,
                    SourceType.GOOGLE_CALENDAR.value,
                    SourceType.PHONE_CONTACTS_UPLOAD.value,
                    SourceType.LINKEDIN_CONNECTIONS_UPLOAD.value,
                ]),
                Source.sync_state.in_(
                    [SyncState.PARTIAL.value, SyncState.COMPLETE.value]
                ),
            )
        )
        return result.first() is not None

    async def _get_default_google_mail_source(self, user_id: uuid.UUID) -> Source | None:
        result = await self._db.execute(
            select(Source)
            .where(
                Source.user_id == user_id,
                Source.source_type == SourceType.GOOGLE_MAIL.value,
            )
            .order_by(Source.created_at)
            .limit(1)
        )
        return result.scalar_one_or_none()

    @staticmethod
    def _sync_in_progress(source: Source, user_id: uuid.UUID) -> bool:
        del user_id
        return is_source_sync_running(source.id)

    async def _recover_orphaned_sync(self, source: Source) -> None:
        """Mark sync failed when DB says syncing but no background task is running."""
        if source.sync_state != SyncState.SYNCING.value:
            return
        if is_source_sync_running(source.id):
            return
        source.sync_state = SyncState.FAILED.value
        source.sync_error = (
            source.sync_error or "Sync was interrupted before it finished. Try again."
        )[:500]
        logger.warning(
            "Recovered orphaned sync for source %s (started_at=%s)",
            source.id,
            source.sync_started_at,
        )

    async def _resolve_gmail_sync_source(self, source: Source) -> Source:
        """Map legacy google_contacts rows to the paired google_mail source."""
        if source.source_type != SourceType.GOOGLE_CONTACTS.value:
            return source
        result = await self._db.execute(
            select(Source).where(
                Source.user_id == source.user_id,
                Source.source_type == SourceType.GOOGLE_MAIL.value,
                Source.external_account_id == source.external_account_id,
            )
        )
        mail_source: Source | None = result.scalar_one_or_none()
        if mail_source is not None:
            return mail_source
        return source

    async def _try_claim_sync(self, source: Source) -> bool:
        """Atomically mark this source syncing."""
        result = await self._db.execute(
            update(Source)
            .where(
                Source.id == source.id,
                Source.sync_state != SyncState.SYNCING.value,
            )
            .values(
                sync_state=SyncState.SYNCING.value,
                sync_started_at=datetime.now(tz=UTC),
                sync_error=None,
            )
            .returning(Source.id)
        )
        claimed_id: uuid.UUID | None = result.scalar_one_or_none()
        if claimed_id is None:
            return False
        await self._db.refresh(source)
        return True

    async def _get_credential_for_source(self, source: Source) -> OAuthCredential | None:
        result = await self._db.execute(
            select(OAuthCredential).where(
                OAuthCredential.source_id == source.id,
                OAuthCredential.is_valid.is_(True),
            )
        )
        cred: OAuthCredential | None = result.scalar_one_or_none()
        if cred is not None:
            return cred
        result = await self._db.execute(
            select(OAuthCredential).where(
                OAuthCredential.user_id == source.user_id,
                OAuthCredential.provider == OAuthProvider.GOOGLE.value,
                OAuthCredential.external_account_id == source.external_account_id,
                OAuthCredential.is_valid.is_(True),
            )
        )
        cred = result.scalar_one_or_none()
        if cred is not None:
            return cred
        result = await self._db.execute(
            select(OAuthCredential)
            .where(
                OAuthCredential.user_id == source.user_id,
                OAuthCredential.provider == OAuthProvider.GOOGLE.value,
                OAuthCredential.is_valid.is_(True),
            )
            .limit(1)
        )
        return result.scalar_one_or_none()

    @staticmethod
    def _to_summary(source: Source) -> SourceSummary:
        return SourceSummary(
            source_id=source.id,
            source_type=SourceType(source.source_type),
            label=source.label,
            external_account_id=source.external_account_id,
            connection_status=SourceConnectionStatus(source.connection_status),
            sync_state=SyncState(source.sync_state),
            contacts_found=source.contacts_found,
            contacts_resolved=source.contacts_resolved,
            contacts_pending=source.contacts_pending,
            sync_error=source.sync_error,
        )

    @staticmethod
    def _oauth_session_message(status: SessionStatus) -> str:
        if status == SessionStatus.PENDING:
            return "Waiting for Google OAuth. Open the connect URL and authorize access."
        if status == SessionStatus.FAILED:
            return "OAuth failed. Call connect_source again to retry."
        if status == SessionStatus.CONNECTED:
            return "Google account connected."
        return "Unknown status."

    @staticmethod
    def _sync_message(source: Source) -> str:
        sync_state: SyncState = SyncState(source.sync_state)
        try:
            source_type: SourceType = SourceType(source.source_type)
        except ValueError:
            source_type = SourceType.GOOGLE_MAIL
        label_map: dict[SourceType, str] = {
            SourceType.GOOGLE_MAIL: "Gmail",
            SourceType.GOOGLE_CALENDAR: "Google Calendar",
            SourceType.PHONE_CONTACTS_UPLOAD: "Phone contacts",
            SourceType.LINKEDIN_CONNECTIONS_UPLOAD: "LinkedIn connections",
            SourceType.LINKEDIN_PROFILE_UPLOAD: "LinkedIn profile",
            SourceType.GOOGLE_CONTACTS: "Gmail",
        }
        label: str = label_map.get(source_type, source.label)
        if source.sync_error:
            return f"Sync failed: {source.sync_error}"
        match sync_state:
            case SyncState.SYNCING:
                if source.contacts_resolved > 0:
                    return (
                        f"Syncing {label} ({source.contacts_resolved}/"
                        f"{source.contacts_found} contacts in your graph so far)..."
                    )
                if source.contacts_found > 0:
                    return (
                        f"Scanning {label} ({source.contacts_found} contacts found so far)..."
                    )
                return f"Scanning {label}..."
            case SyncState.PARTIAL:
                return (
                    f"Partial graph ready ({source.contacts_resolved} contacts). "
                    "Sync continuing in background."
                )
            case SyncState.COMPLETE:
                return f"Sync complete. {source.contacts_resolved} contacts in your graph."
            case SyncState.FAILED:
                return f"Sync failed: {source.sync_error or 'unknown error'}"
            case _:
                return "Connected. Call sync_source to start ingestion."
