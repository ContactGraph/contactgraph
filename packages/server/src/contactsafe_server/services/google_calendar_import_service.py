import logging
import uuid
from datetime import UTC, datetime

import httpx
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from contactsafe_core.enums import OAuthProvider, SourceConnectionStatus, SourceType, SyncState
from contactsafe_server.db.models import OAuthCredential, Source
from contactsafe_server.oauth.google import GoogleTokens
from contactsafe_server.services.calendar_api_client import CalendarApiClient
from contactsafe_server.services.crypto import TokenEncryptor
from contactsafe_server.services.entity_resolution import EntityResolver

logger: logging.Logger = logging.getLogger(__name__)


class GoogleCalendarImportService:
    def __init__(
        self,
        db: AsyncSession,
        encryptor: TokenEncryptor,
        calendar_client: CalendarApiClient,
    ) -> None:
        self._db: AsyncSession = db
        self._encryptor: TokenEncryptor = encryptor
        self._calendar: CalendarApiClient = calendar_client

    async def run_sync(self, source_id: uuid.UUID) -> None:
        source: Source | None = await self._db.get(Source, source_id)
        if source is None:
            return
        if source.source_type != SourceType.GOOGLE_CALENDAR.value:
            raise ValueError(f"Expected google_calendar source, got {source.source_type}")

        source.sync_state = SyncState.SYNCING.value
        source.sync_started_at = datetime.now(tz=UTC)
        source.sync_error = None
        source.contacts_found = 0
        source.contacts_resolved = 0
        source.contacts_pending = 0
        await self._db.flush()

        try:
            cred: OAuthCredential | None = await self._get_credential_for_source(source)
            if cred is None:
                raise ValueError("No valid Google OAuth credentials for calendar source")
            access: str = self._encryptor.decrypt(cred.access_token_encrypted)
            refresh: str = self._encryptor.decrypt(cred.refresh_token_encrypted)
            access, refreshed = await self._calendar.get_valid_access_token(
                access, refresh, cred.token_expires_at
            )
            if refreshed is not None:
                await self._persist_tokens(cred, refreshed)
                access = refreshed.access_token

            await self._fetch_and_ingest(access_token=access, source=source)
            source.sync_state = SyncState.COMPLETE.value
            source.sync_completed_at = datetime.now(tz=UTC)
            source.connection_status = SourceConnectionStatus.CONNECTED.value
            source.contacts_pending = 0
            await self._db.flush()
        except Exception as exc:
            logger.exception("Google Calendar sync failed for source %s", source_id)
            source.sync_state = SyncState.FAILED.value
            source.sync_error = str(exc)[:500]
            await self._db.flush()
            raise

    async def _fetch_and_ingest(self, *, access_token: str, source: Source) -> None:
        from contactsafe_server.db.models import UserPersonObservation

        try:
            page = await self._calendar.list_recent_participants(
                access_token,
                sync_token=source.sync_token,
                max_results=250,
            )
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 410 and source.sync_token is not None:
                logger.info("Calendar sync token expired for source %s, resetting", source.id)
                source.sync_token = None
                await self._db.flush()
                page = await self._calendar.list_recent_participants(
                    access_token, sync_token=None, max_results=250
                )
            else:
                raise

        resolver = EntityResolver(self._db)
        seen: set[str] = set()
        for participant in page.participants:
            if participant.email in seen:
                continue
            seen.add(participant.email)
            person = await resolver.resolve_person(
                emails=[participant.email],
                display_name=participant.display_name or participant.email,
            )
            now = datetime.now(tz=UTC)
            stmt = pg_insert(UserPersonObservation).values(
                user_id=source.user_id,
                person_id=person.id,
                first_observed_at=now,
                last_observed_at=now,
                email_count=0,
                outbound_count=0,
                inbound_count=0,
                thread_count=0,
                tie_strength_score=0.2,
                is_human=True,
                is_broadcast=False,
                is_automated=False,
                relationship_types=["google_calendar"],
                notes="Observed via Google Calendar events",
                source_id=source.id,
            ).on_conflict_do_update(
                constraint="pk_user_person_obs",
                set_={
                    "last_observed_at": now,
                    "relationship_types": ["google_calendar"],
                },
            )
            await self._db.execute(stmt)
            source.contacts_found += 1
            source.contacts_resolved += 1

        source.contacts_pending = 0
        if page.next_sync_token:
            source.sync_token = page.next_sync_token
        await self._db.flush()

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
        return result.scalar_one_or_none()

    async def _persist_tokens(self, cred: OAuthCredential, tokens: GoogleTokens) -> None:
        cred.access_token_encrypted = self._encryptor.encrypt(tokens.access_token)
        cred.refresh_token_encrypted = self._encryptor.encrypt(tokens.refresh_token)
        cred.token_expires_at = tokens.expires_at
        cred.scopes = tokens.scopes
        await self._db.flush()
