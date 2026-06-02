import logging
import uuid
from datetime import UTC, datetime

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from contactsafe_core.enums import SourceConnectionStatus, SourceType, SyncState
from contactsafe_server.db.models import Source, UserPersonObservation
from contactsafe_server.services.entity_resolution import EntityResolver
from contactsafe_server.services.linkedin_connections_parser import (
    ParsedLinkedInConnection,
    parse_linkedin_connections_csv,
)
from contactsafe_server.services.phone_contacts_parser import (
    ParsedPhoneContact,
    parse_phone_contacts_upload,
)

logger: logging.Logger = logging.getLogger(__name__)


class FileUploadImportService:
    def __init__(self, db: AsyncSession) -> None:
        self._db: AsyncSession = db

    async def run_sync(self, source_id: uuid.UUID) -> None:
        source: Source | None = await self._db.get(Source, source_id)
        if source is None:
            return

        if source.source_type not in {
            SourceType.PHONE_CONTACTS_UPLOAD.value,
            SourceType.LINKEDIN_CONNECTIONS_UPLOAD.value,
        }:
            raise ValueError(f"Unsupported upload source type {source.source_type}")

        source.sync_state = SyncState.SYNCING.value
        source.sync_started_at = datetime.now(tz=UTC)
        source.sync_error = None
        source.contacts_found = 0
        source.contacts_resolved = 0
        source.contacts_pending = 0
        await self._db.flush()

        try:
            payload: dict[str, object] | None = source.upload_payload
            if payload is None:
                raise ValueError("No upload payload stored for this source")

            content: str = str(payload.get("content", ""))
            filename: str = str(payload.get("filename", "upload.csv"))
            if not content.strip():
                raise ValueError("Upload payload is empty")

            if source.source_type == SourceType.PHONE_CONTACTS_UPLOAD.value:
                await self._ingest_phone_contacts(source, content, filename)
            else:
                await self._ingest_linkedin_connections(source, content)

            source.upload_payload = None
            source.sync_state = SyncState.COMPLETE.value
            source.sync_completed_at = datetime.now(tz=UTC)
            source.connection_status = SourceConnectionStatus.CONNECTED.value
            source.contacts_pending = 0
            await self._db.flush()
        except Exception as exc:
            logger.exception("Upload import failed for source %s", source_id)
            source.sync_state = SyncState.FAILED.value
            source.sync_error = str(exc)[:500]
            await self._db.flush()
            raise

    async def _ingest_phone_contacts(
        self,
        source: Source,
        content: str,
        filename: str,
    ) -> None:
        contacts: list[ParsedPhoneContact] = parse_phone_contacts_upload(content, filename)
        resolver = EntityResolver(self._db)
        for contact in contacts:
            emails: list[str] = [contact.email] if contact.email else []
            person = await resolver.resolve_person(
                emails=emails or None,
                display_name=contact.display_name,
            )
            if contact.phone:
                try:
                    await resolver.add_person_alias(
                        person_id=person.id,
                        kind="phone",
                        value=contact.phone,
                    )
                except Exception:
                    logger.debug("Phone alias already mapped for %s", contact.phone)

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
                tie_strength_score=0.25,
                is_human=True,
                is_broadcast=False,
                is_automated=False,
                relationship_types=["phone_contacts_upload"],
                notes="Imported from phone contacts upload",
                source_id=source.id,
            ).on_conflict_do_update(
                constraint="pk_user_person_obs",
                set_={
                    "last_observed_at": now,
                    "relationship_types": ["phone_contacts_upload"],
                },
            )
            await self._db.execute(stmt)
            source.contacts_found += 1
            source.contacts_resolved += 1
        await self._db.flush()

    async def _ingest_linkedin_connections(
        self,
        source: Source,
        content: str,
    ) -> None:
        connections: list[ParsedLinkedInConnection] = parse_linkedin_connections_csv(content)
        resolver = EntityResolver(self._db)
        for connection in connections:
            emails: list[str] = [connection.email] if connection.email else []
            person = await resolver.resolve_person(
                emails=emails or None,
                display_name=connection.display_name,
            )
            if connection.linkedin_url:
                try:
                    await resolver.add_person_alias(
                        person_id=person.id,
                        kind="linkedin_url",
                        value=connection.linkedin_url,
                    )
                except Exception:
                    logger.debug(
                        "LinkedIn alias already mapped for %s",
                        connection.linkedin_url,
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
                tie_strength_score=0.3,
                is_human=True,
                is_broadcast=False,
                is_automated=False,
                relationship_types=["linkedin_connections_upload"],
                notes="Imported from LinkedIn connections export",
                source_id=source.id,
            ).on_conflict_do_update(
                constraint="pk_user_person_obs",
                set_={
                    "last_observed_at": now,
                    "relationship_types": ["linkedin_connections_upload"],
                },
            )
            await self._db.execute(stmt)
            source.contacts_found += 1
            source.contacts_resolved += 1
        await self._db.flush()
