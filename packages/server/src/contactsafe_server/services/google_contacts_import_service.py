import logging
import uuid
from datetime import UTC, datetime

import httpx
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from contactsafe_core.enums import OAuthProvider, SourceConnectionStatus, SourceType, SyncState
from contactsafe_server.config import Settings
from contactsafe_server.db.models import (
    OAuthCredential,
    Person,
    Source,
    User,
    UserPersonObservation,
)
from contactsafe_server.oauth.google import GoogleTokens
from contactsafe_server.services.claim_writer import record_employment, record_relationship
from contactsafe_server.services.crypto import TokenEncryptor
from contactsafe_server.services.entity_resolution import EntityResolver
from contactsafe_server.services.org_search import is_automation_or_generic_domain
from contactsafe_server.services.people_api_client import (
    GoogleContact,
    PeopleApiClient,
)
from contactsafe_server.services.user_person_service import ensure_user_person

logger: logging.Logger = logging.getLogger(__name__)


class GoogleContactsImportService:
    def __init__(
        self,
        db: AsyncSession,
        settings: Settings,
        encryptor: TokenEncryptor,
        people_client: PeopleApiClient,
    ) -> None:
        self._db: AsyncSession = db
        self._settings: Settings = settings
        self._encryptor: TokenEncryptor = encryptor
        self._people: PeopleApiClient = people_client

    async def run_sync(self, source_id: uuid.UUID) -> None:
        source: Source | None = await self._db.get(Source, source_id)
        if source is None:
            return
        if source.source_type != SourceType.GOOGLE_CONTACTS.value:
            raise ValueError(f"Expected google_contacts source, got {source.source_type}")

        user: User | None = await self._db.get(User, source.user_id)
        if user is None:
            return

        user_id: uuid.UUID = source.user_id
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
                raise ValueError("No valid Google OAuth credentials for source")

            access_token: str = self._encryptor.decrypt(cred.access_token_encrypted)
            refresh_token: str = self._encryptor.decrypt(cred.refresh_token_encrypted)
            access_token, refreshed = await self._people.get_valid_access_token(
                access_token, refresh_token, cred.token_expires_at,
            )
            if refreshed is not None:
                await self._persist_tokens(cred, refreshed)
                access_token = refreshed.access_token

            resolver: EntityResolver = EntityResolver(self._db)

            await self._fetch_and_ingest(
                access_token=access_token,
                user_id=user_id,
                source=source,
                resolver=resolver,
            )

            source.sync_state = SyncState.COMPLETE.value
            source.sync_completed_at = datetime.now(tz=UTC)
            source.contacts_pending = 0
            source.connection_status = SourceConnectionStatus.CONNECTED.value
            await self._db.flush()
        except Exception as exc:
            logger.exception("Google Contacts sync failed for source %s", source_id)
            source.sync_state = SyncState.FAILED.value
            source.sync_error = str(exc)[:500]
            await self._db.flush()
            raise

    async def _fetch_and_ingest(
        self,
        *,
        access_token: str,
        user_id: uuid.UUID,
        source: Source,
        resolver: EntityResolver,
    ) -> None:
        page_token: str | None = None
        stored_sync_token: str | None = source.sync_token
        use_sync_token: str | None = stored_sync_token
        total_fetched: int = 0
        total_resolved: int = 0
        max_results: int = self._settings.import_contacts_max_results
        page_size: int = self._settings.import_contacts_page_size
        final_sync_token: str | None = None
        user: User | None = await self._db.get(User, user_id)
        user_person: Person | None = None
        if user is not None:
            user_person = await ensure_user_person(self._db, user)

        while total_fetched < max_results:
            try:
                page = await self._people.list_connections(
                    access_token,
                    page_size=min(page_size, max_results - total_fetched),
                    page_token=page_token,
                    sync_token=use_sync_token if page_token is None else None,
                    request_sync_token=True,
                )
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code == 410 and use_sync_token is not None:
                    logger.info(
                        "Sync token expired for source %s, falling back to full sync",
                        source.id,
                    )
                    use_sync_token = None
                    source.sync_token = None
                    await self._db.flush()
                    continue
                raise

            for contact in page.contacts:
                if contact.is_deleted:
                    continue
                if not contact.emails and not contact.phone_numbers:
                    continue

                total_fetched += 1
                source.contacts_found = total_fetched

                await self._upsert_contact(
                    contact=contact,
                    user_id=user_id,
                    source_id=source.id,
                    resolver=resolver,
                    user_person=user_person,
                )
                total_resolved += 1
                source.contacts_resolved = total_resolved
                source.contacts_pending = max(0, total_fetched - total_resolved)

            if page.next_sync_token is not None:
                final_sync_token = page.next_sync_token

            if (
                source.sync_state == SyncState.SYNCING.value
                and total_resolved >= self._settings.import_partial_contact_target
            ):
                source.sync_state = SyncState.PARTIAL.value

            await self._db.flush()
            await self._db.commit()
            await self._db.refresh(source)

            logger.info(
                "Contacts sync progress source=%s fetched=%s resolved=%s",
                source.id, total_fetched, total_resolved,
            )

            page_token = page.next_page_token
            if page_token is None:
                break

        if final_sync_token is not None:
            source.sync_token = final_sync_token
            await self._db.flush()

    async def _upsert_contact(
        self,
        *,
        contact: GoogleContact,
        user_id: uuid.UUID,
        source_id: uuid.UUID,
        resolver: EntityResolver,
        user_person: Person | None = None,
    ) -> None:
        display_name: str = contact.display_name or (
            contact.emails[0] if contact.emails else contact.phone_numbers[0]
        )

        phone: str | None = contact.phone_numbers[0] if contact.phone_numbers else None
        person: Person = await resolver.resolve_person(
            emails=contact.emails,
            display_name=display_name,
            phone=phone,
        )

        if contact.display_name and (
            not person.canonical_name
            or person.canonical_name == (person.primary_email or "")
        ):
            person.canonical_name = contact.display_name

        if contact.phone_numbers:
            existing_phones: set[str] = set(person.phone_numbers or [])
            new_phones: list[str] = list(existing_phones)
            for phone_num in contact.phone_numbers:
                if phone_num not in existing_phones:
                    new_phones.append(phone_num)
                    try:
                        await resolver.add_person_alias(
                            person_id=person.id,
                            kind="phone",
                            value=phone_num,
                        )
                    except Exception:
                        logger.debug(
                            "Phone alias %s already mapped, skipping", phone_num,
                        )
            if len(new_phones) > len(person.phone_numbers or []):
                person.phone_numbers = new_phones

        for extra_phone in contact.phone_numbers[1:]:
            try:
                await resolver.add_person_alias(
                    person_id=person.id,
                    kind="phone",
                    value=extra_phone,
                )
            except Exception:
                pass

        stmt = pg_insert(UserPersonObservation).values(
            user_id=user_id,
            person_id=person.id,
            first_observed_at=datetime.now(tz=UTC),
            last_observed_at=datetime.now(tz=UTC),
            email_count=0,
            outbound_count=0,
            inbound_count=0,
            thread_count=0,
            tie_strength_score=0.3,
            is_human=True,
            is_broadcast=False,
            is_automated=False,
            relationship_types=["google_contact"],
            notes="Imported from Google Contacts",
            source_id=source_id,
        )
        stmt = stmt.on_conflict_do_update(
            constraint="pk_user_person_obs",
            set_={
                "last_observed_at": stmt.excluded.last_observed_at,
                "relationship_types": stmt.excluded.relationship_types,
                "updated_at": stmt.excluded.updated_at,
            },
        )
        await self._db.execute(stmt)

        if user_person is not None and user_person.id != person.id:
            await record_relationship(
                self._db,
                person_a_id=user_person.id,
                person_b_id=person.id,
                kind="google_contact",
                contributor_user_id=user_id,
                contributor_source_kind="google_contacts",
            )

        if contact.org_name and contact.emails:
            domain: str = contact.emails[0].rsplit("@", 1)[-1].lower()
            if not is_automation_or_generic_domain(domain):
                org = await resolver.resolve_org(domain=domain, name=contact.org_name)
                await record_employment(
                    self._db,
                    person_id=person.id,
                    org_id=org.id,
                    role_title=contact.org_title,
                    contributor_user_id=user_id,
                    contributor_source_kind="google_contacts",
                    contributor_source_id=source_id,
                    confidence=0.8,
                )

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

    async def _persist_tokens(self, cred: OAuthCredential, tokens: GoogleTokens) -> None:
        cred.access_token_encrypted = self._encryptor.encrypt(tokens.access_token)
        cred.token_expires_at = tokens.expires_at
        cred.scopes = tokens.scopes
        await self._db.flush()
