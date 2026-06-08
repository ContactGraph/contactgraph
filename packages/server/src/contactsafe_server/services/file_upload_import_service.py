import logging
import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from contactsafe_core.enums import SourceConnectionStatus, SourceType, SyncState
from contactsafe_server.config import Settings
from contactsafe_server.db.models import Person, Source, User, UserPersonObservation
from contactsafe_server.services.claim_writer import (
    record_employment,
    record_person_attribute,
    record_relationship,
)
from contactsafe_server.services.entity_resolution import EntityResolver, build_last_name_index
from contactsafe_server.services.phone_normalization import normalize_phone
from contactsafe_server.services.linkedin_connections_parser import (
    ParsedLinkedInConnection,
    parse_linkedin_connections_csv,
)
from contactsafe_server.services.linkedin_profile_parser import (
    ParsedLinkedInProfile,
    parse_linkedin_profile_pdf,
)
from contactsafe_server.services.person_profile_recompute import PersonProfileRecompute
from contactsafe_server.services.phone_contacts_parser import (
    ParsedPhoneContact,
    parse_phone_contacts_upload,
)
from contactsafe_server.services.crypto import TokenEncryptor
from contactsafe_server.services.upload_payload_crypto import read_upload_payload
from contactsafe_server.services.user_person_service import ensure_user_person

logger: logging.Logger = logging.getLogger(__name__)

_LINKEDIN_UPLOAD_RELATIONSHIP_TYPES: list[str] = ["linkedin_connections_upload"]
_PHONE_UPLOAD_RELATIONSHIP_TYPES: list[str] = ["phone_contacts_upload"]
_LINKEDIN_IMPORT_COMMIT_BATCH: int = 100


def _merged_relationship_types_on_conflict() -> text:
    return text(
        "(SELECT COALESCE(array_agg(DISTINCT rel), ARRAY[]::text[]) "
        "FROM unnest("
        "COALESCE(user_person_observations.relationship_types, ARRAY[]::text[]) "
        "|| excluded.relationship_types"
        ") AS rel)"
    )


class FileUploadImportService:
    def __init__(
        self,
        db: AsyncSession,
        settings: Settings | None = None,
        *,
        encryptor: TokenEncryptor | None = None,
    ) -> None:
        self._db: AsyncSession = db
        self._settings: Settings = settings or Settings()
        self._encryptor: TokenEncryptor = encryptor or TokenEncryptor(
            self._settings.token_encryption_key
        )

    async def _commit_progress(self, source: Source) -> None:
        await self._db.commit()
        await self._db.refresh(source)

    async def run_sync(self, source_id: uuid.UUID) -> None:
        source: Source | None = await self._db.get(Source, source_id)
        if source is None:
            return

        if source.source_type not in {
            SourceType.PHONE_CONTACTS_UPLOAD.value,
            SourceType.LINKEDIN_CONNECTIONS_UPLOAD.value,
            SourceType.LINKEDIN_PROFILE_UPLOAD.value,
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
            filename, content = read_upload_payload(
                source.upload_payload,
                self._encryptor,
            )
            if not content.strip():
                raise ValueError("Upload payload is empty")

            if source.source_type == SourceType.PHONE_CONTACTS_UPLOAD.value:
                await self._ingest_phone_contacts(source, content, filename)
            elif source.source_type == SourceType.LINKEDIN_PROFILE_UPLOAD.value:
                await self._ingest_linkedin_profile(source, content)
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
        source.contacts_pending = len(contacts)
        await self._db.flush()
        await self._commit_progress(source)

        resolver = EntityResolver(self._db)
        user_id: uuid.UUID = source.user_id
        source_id: uuid.UUID = source.id
        user: User | None = await self._db.get(User, user_id)
        user_person: Person | None = None
        if user is not None:
            user_person = await ensure_user_person(self._db, user)

        for contact in contacts:
            if not contact.display_name:
                continue

            display_name: str = contact.display_name
            normalized_phones: list[str] = [
                normalize_phone(p) for p in contact.phone_numbers
            ]
            primary_phone: str | None = normalized_phones[0] if normalized_phones else None
            person: Person = await resolver.resolve_person(
                emails=list(contact.emails),
                display_name=display_name,
                phone=primary_phone,
                linkedin_url=contact.linkedin_url,
            )

            if contact.display_name and (
                not person.canonical_name
                or person.canonical_name == (person.primary_email or "")
            ):
                person.canonical_name = contact.display_name

            if normalized_phones:
                existing_phones: set[str] = set(person.phone_numbers or [])
                new_phones: list[str] = list(existing_phones)
                for phone_num in normalized_phones:
                    if phone_num not in existing_phones:
                        new_phones.append(phone_num)
                        existing_phones.add(phone_num)
                        try:
                            await resolver.add_person_alias(
                                person_id=person.id,
                                kind="phone",
                                value=phone_num,
                            )
                        except Exception:
                            logger.debug(
                                "Phone alias %s already mapped, skipping",
                                phone_num,
                            )
                if len(new_phones) > len(person.phone_numbers or []):
                    person.phone_numbers = new_phones

            for extra_email in contact.emails[1:]:
                try:
                    await resolver.add_person_alias(
                        person_id=person.id,
                        kind="email",
                        value=extra_email,
                    )
                except Exception:
                    pass

            if contact.linkedin_url:
                try:
                    await resolver.add_person_alias(
                        person_id=person.id,
                        kind="linkedin_url",
                        value=contact.linkedin_url,
                    )
                except Exception:
                    pass

            now = datetime.now(tz=UTC)
            phone_tie_strength: float = 0.5
            insert_stmt = pg_insert(UserPersonObservation).values(
                user_id=user_id,
                person_id=person.id,
                first_observed_at=now,
                last_observed_at=now,
                email_count=0,
                outbound_count=0,
                inbound_count=0,
                thread_count=0,
                tie_strength_score=phone_tie_strength,
                is_human=True,
                is_broadcast=False,
                is_automated=False,
                relationship_types=_PHONE_UPLOAD_RELATIONSHIP_TYPES,
                notes="Imported from phone contacts upload",
                source_id=source_id,
            )
            stmt = insert_stmt.on_conflict_do_update(
                constraint="pk_user_person_obs",
                set_={
                    "last_observed_at": now,
                    "relationship_types": _merged_relationship_types_on_conflict(),
                    "tie_strength_score": func.least(
                        1.0,
                        UserPersonObservation.tie_strength_score
                        + insert_stmt.excluded.tie_strength_score,
                    ),
                    "updated_at": now,
                },
            )
            await self._db.execute(stmt)

            if user_person is not None and user_person.id != person.id:
                await record_relationship(
                    self._db,
                    person_a_id=user_person.id,
                    person_b_id=person.id,
                    kind="phone_contact",
                    contributor_user_id=user_id,
                    contributor_source_kind="phone_contacts_upload",
                )

            source.contacts_found += 1
            source.contacts_resolved += 1

        await self._db.flush()

    async def _ingest_linkedin_connections(
        self,
        source: Source,
        content: str,
    ) -> None:
        connections: list[ParsedLinkedInConnection] = parse_linkedin_connections_csv(content)
        logger.info("Parsed %d LinkedIn connections for source %s", len(connections), source.id)
        source.contacts_pending = len(connections)
        await self._db.flush()
        await self._commit_progress(source)

        resolver = EntityResolver(self._db)
        logger.info("Preloading entity resolution caches...")
        await resolver.preload_caches()
        logger.info("Caches loaded: %d persons, %d person aliases, %d orgs, %d org aliases",
                     len(resolver._person_cache), len(resolver._person_alias_cache or {}),
                     len(resolver._org_cache), len(resolver._org_alias_cache or {}))
        commit_interval: int = _LINKEDIN_IMPORT_COMMIT_BATCH
        processed_since_commit: int = 0
        merge_relationship_types = _merged_relationship_types_on_conflict()

        from contactsafe_server.services.entity_resolution import _extract_last_name

        all_persons: list[Person] = list(resolver._person_cache.values())
        name_index: dict[str, list[Person]] = build_last_name_index(all_persons)
        seen_person_ids: set[uuid.UUID] = {p.id for p in all_persons}
        touched_person_ids: list[uuid.UUID] = []

        for connection in connections:
            if not connection.linkedin_url:
                continue

            person = await resolver.resolve_linkedin_connection(
                linkedin_url=connection.linkedin_url,
                first_name=connection.first_name,
                last_name=connection.last_name,
                email=connection.email,
                name_index=name_index,
            )

            touched_person_ids.append(person.id)
            if person.id not in seen_person_ids:
                seen_person_ids.add(person.id)
                last_key: str = _extract_last_name(person.canonical_name).lower()
                if last_key:
                    name_index.setdefault(last_key, []).append(person)

            observed_at: datetime = (
                datetime.combine(connection.connected_on, datetime.min.time(), tzinfo=UTC)
                if connection.connected_on is not None
                else datetime.now(tz=UTC)
            )
            stmt = pg_insert(UserPersonObservation).values(
                user_id=source.user_id,
                person_id=person.id,
                first_observed_at=observed_at,
                last_observed_at=observed_at,
                email_count=0,
                outbound_count=0,
                inbound_count=0,
                thread_count=0,
                tie_strength_score=0.3,
                is_human=True,
                is_broadcast=False,
                is_automated=False,
                relationship_types=_LINKEDIN_UPLOAD_RELATIONSHIP_TYPES,
                notes="Imported from LinkedIn connections export",
                source_id=source.id,
            ).on_conflict_do_update(
                constraint="pk_user_person_obs",
                set_={
                    "last_observed_at": observed_at,
                    "relationship_types": merge_relationship_types,
                },
            )
            await self._db.execute(stmt)

            if connection.company:
                org = await resolver.resolve_org(domain=None, name=connection.company)
                await record_employment(
                    self._db,
                    person_id=person.id,
                    org_id=org.id,
                    role_title=connection.position,
                    contributor_user_id=source.user_id,
                    contributor_source_kind="linkedin_connections_upload",
                    contributor_source_id=source.id,
                    confidence=0.8,
                )

            source.contacts_found += 1
            source.contacts_resolved += 1

            processed_since_commit += 1
            if processed_since_commit >= commit_interval:
                await self._db.flush()
                await self._commit_progress(source)
                logger.info("LinkedIn import progress: %d/%d", source.contacts_resolved, len(connections))
                processed_since_commit = 0

        if processed_since_commit > 0:
            await self._db.flush()

        unique_touched: list[uuid.UUID] = list(dict.fromkeys(touched_person_ids))
        logger.info("LinkedIn import loop done (%d contacts, %d unique persons). Starting recompute...",
                     source.contacts_resolved, len(unique_touched))
        recompute = PersonProfileRecompute(self._db, self._settings)
        await recompute.recompute_persons(unique_touched)
        logger.info("Recompute finished for source %s", source.id)

    async def _ingest_linkedin_profile(
        self,
        source: Source,
        content_base64: str,
    ) -> None:
        profile: ParsedLinkedInProfile = await parse_linkedin_profile_pdf(
            content_base64, self._settings,
        )
        user: User | None = await self._db.get(User, source.user_id)
        if user is None:
            raise ValueError("User not found for source")

        person: Person = await ensure_user_person(self._db, user)
        resolver = EntityResolver(self._db)
        user_id: uuid.UUID = source.user_id
        source_id: uuid.UUID = source.id

        if profile.name and not user.display_name:
            user.display_name = profile.name
        if profile.location and not user.location:
            user.location = profile.location

        for exp in profile.experiences:
            org = await resolver.resolve_org(domain=None, name=exp.company)
            await record_employment(
                self._db,
                person_id=person.id,
                org_id=org.id,
                role_title=exp.title,
                is_current=exp.is_current,
                started_at=exp.start_date,
                ended_at=exp.end_date,
                contributor_user_id=user_id,
                contributor_source_kind="linkedin_profile_upload",
                contributor_source_id=source_id,
                confidence=0.9,
            )
            source.contacts_found += 1
            source.contacts_resolved += 1

        for edu in profile.education:
            await record_person_attribute(
                self._db,
                person_id=person.id,
                kind="education",
                value=edu.school,
                contributor_user_id=user_id,
                contributor_source_kind="linkedin_profile_upload",
                contributor_source_id=source_id,
                confidence=0.9,
                evidence={
                    "degree": edu.degree,
                    "field_of_study": edu.field_of_study,
                    "start_year": edu.start_year,
                    "end_year": edu.end_year,
                },
            )

        if profile.headline:
            await record_person_attribute(
                self._db,
                person_id=person.id,
                kind="headline",
                value=profile.headline,
                contributor_user_id=user_id,
                contributor_source_kind="linkedin_profile_upload",
                contributor_source_id=source_id,
                confidence=0.9,
            )

        if profile.about:
            await record_person_attribute(
                self._db,
                person_id=person.id,
                kind="bio_summary",
                value=profile.about[:500],
                contributor_user_id=user_id,
                contributor_source_kind="linkedin_profile_upload",
                contributor_source_id=source_id,
                confidence=0.9,
            )

        recompute = PersonProfileRecompute(self._db)
        await recompute.recompute_persons([person.id])
        await self._db.flush()
