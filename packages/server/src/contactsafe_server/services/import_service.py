import logging
import uuid
from datetime import UTC, datetime

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from contactsafe_core.enums import OAuthProvider, SourceConnectionStatus, SourceType, SyncState
from contactsafe_server.config import Settings
from contactsafe_server.db.models import OAuthCredential, Person, PersonEdge, Source, User
from contactsafe_server.oauth.google import GoogleTokens
from contactsafe_server.services.crypto import TokenEncryptor
from contactsafe_server.services.email_parse import (
    ContactAccumulator,
    company_query_from_question,
    name_query_from_question,
    org_name_from_email,
    parse_address_header,
    parse_internal_date_ms,
    person_matches_name,
)
from contactsafe_server.services.gmail_client import GmailClient, GmailMessageMeta

logger = logging.getLogger(__name__)


class ImportService:
    def __init__(
        self,
        db: AsyncSession,
        settings: Settings,
        encryptor: TokenEncryptor,
        gmail: GmailClient,
    ) -> None:
        self._db: AsyncSession = db
        self._settings: Settings = settings
        self._encryptor: TokenEncryptor = encryptor
        self._gmail: GmailClient = gmail

    async def run_sync(self, source_id: uuid.UUID) -> None:
        source: Source | None = await self._db.get(Source, source_id)
        if source is None:
            return
        if source.source_type != SourceType.GOOGLE_MAIL.value:
            raise ValueError(f"Sync not supported for source type {source.source_type}")

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
            access_token, refreshed = await self._gmail.get_valid_access_token(
                access_token, refresh_token, cred.token_expires_at
            )
            if refreshed is not None:
                await self._persist_tokens(cred, refreshed)
                access_token = refreshed.access_token

            contacts: dict[str, ContactAccumulator] = await self._scan_gmail(
                access_token=access_token,
                user_email=user.email,
            )
            source.contacts_found = len(contacts)
            source.contacts_pending = max(
                0, len(contacts) - self._settings.import_initial_contact_target
            )
            await self._db.flush()

            await self._db.execute(delete(PersonEdge).where(PersonEdge.user_id == user_id))
            await self._db.execute(delete(Person).where(Person.user_id == user_id))
            await self._db.flush()

            sorted_contacts: list[ContactAccumulator] = sorted(
                contacts.values(),
                key=lambda c: (
                    c.last_seen_at or datetime.min.replace(tzinfo=UTC),
                    c.message_count,
                ),
                reverse=True,
            )

            resolved: int = 0
            for accumulator in sorted_contacts:
                await self._upsert_person(user_id, user.email, accumulator)
                resolved += 1
                source.contacts_resolved = resolved
                source.contacts_pending = max(0, source.contacts_found - resolved)
                if resolved == self._settings.import_initial_contact_target:
                    source.sync_state = SyncState.PARTIAL.value
                    await self._db.flush()

            for accumulator in sorted_contacts[self._settings.import_initial_contact_target :]:
                await self._upsert_person(user_id, user.email, accumulator)
                resolved += 1
                source.contacts_resolved = resolved
                source.contacts_pending = max(0, source.contacts_found - resolved)

            source.sync_state = SyncState.COMPLETE.value
            source.sync_completed_at = datetime.now(tz=UTC)
            source.contacts_pending = 0
            source.connection_status = SourceConnectionStatus.CONNECTED.value
            await self._db.flush()
        except Exception as exc:
            logger.exception("Sync failed for source %s", source_id)
            source.sync_state = SyncState.FAILED.value
            source.sync_error = str(exc)[:500]
            await self._db.flush()
            raise

    async def run_import(self, user_id: uuid.UUID) -> None:
        """Deprecated: use run_sync with the user's google_mail source_id."""
        result = await self._db.execute(
            select(Source).where(
                Source.user_id == user_id,
                Source.source_type == SourceType.GOOGLE_MAIL.value,
            )
        )
        source: Source | None = result.scalar_one_or_none()
        if source is None:
            return
        await self.run_sync(source.id)

    async def _scan_gmail(
        self,
        *,
        access_token: str,
        user_email: str,
    ) -> dict[str, ContactAccumulator]:
        contacts: dict[str, ContactAccumulator] = {}
        page_token: str | None = None
        fetched: int = 0
        max_messages: int = self._settings.import_max_messages

        while fetched < max_messages:
            batch_size: int = min(100, max_messages - fetched)
            refs, page_token = await self._gmail.list_message_refs(
                access_token,
                max_results=batch_size,
                page_token=page_token,
                query=self._settings.import_gmail_query,
            )
            if not refs:
                break

            for ref in refs:
                meta: GmailMessageMeta = await self._gmail.get_message_metadata(
                    access_token, ref.id
                )
                seen_at: datetime | None = parse_internal_date_ms(
                    meta.internal_date_ms or ref.internal_date_ms
                )
                self._accumulate_header(
                    contacts,
                    header=meta.from_header,
                    user_email=user_email,
                    seen_at=seen_at,
                    from_user=False,
                )
                self._accumulate_header(
                    contacts,
                    header=meta.to_header,
                    user_email=user_email,
                    seen_at=seen_at,
                    from_user=True,
                )
                self._accumulate_header(
                    contacts,
                    header=meta.cc_header,
                    user_email=user_email,
                    seen_at=seen_at,
                    from_user=True,
                )
            fetched += len(refs)
            if page_token is None:
                break

        return contacts

    def _accumulate_header(
        self,
        contacts: dict[str, ContactAccumulator],
        *,
        header: str | None,
        user_email: str,
        seen_at: datetime | None,
        from_user: bool,
    ) -> None:
        if not header:
            return
        for display_name, email in parse_address_header(header):
            if email == user_email:
                continue
            existing: ContactAccumulator | None = contacts.get(email)
            if existing is None:
                contacts[email] = ContactAccumulator(
                    email=email,
                    display_name=display_name,
                    last_seen_at=seen_at,
                )
                existing = contacts[email]
            existing.observe(display_name=display_name, seen_at=seen_at, from_user=from_user)

    async def _upsert_person(
        self,
        user_id: uuid.UUID,
        user_email: str,
        accumulator: ContactAccumulator,
    ) -> None:
        org_name: str | None = org_name_from_email(accumulator.email)
        person = Person(
            user_id=user_id,
            canonical_name=accumulator.display_name,
            email_addresses=[accumulator.email],
            current_org_name=org_name,
            last_seen_in_email=accumulator.last_seen_at,
            confidence_score=0.85,
        )
        self._db.add(person)
        await self._db.flush()

        tie_strength: float = min(
            1.0,
            float(accumulator.message_count) / 20.0,
        )
        edge = PersonEdge(
            user_id=user_id,
            person_id=person.id,
            relationship_types=["contact"],
            email_count=accumulator.message_count,
            outbound_count=accumulator.outbound_count,
            inbound_count=accumulator.inbound_count,
            thread_count=accumulator.message_count,
            last_email_at=accumulator.last_seen_at,
            last_genuine_interaction_at=accumulator.last_seen_at
            if accumulator.outbound_count > 0 and accumulator.inbound_count > 0
            else None,
            first_contact_date=accumulator.last_seen_at,
            tie_strength_score=tie_strength,
            notes=f"Imported from Gmail metadata for {user_email}",
        )
        self._db.add(edge)

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
                OAuthCredential.is_valid.is_(True),
            )
        )
        return result.scalar_one_or_none()

    async def _persist_tokens(self, cred: OAuthCredential, tokens: GoogleTokens) -> None:
        cred.access_token_encrypted = self._encryptor.encrypt(tokens.access_token)
        cred.token_expires_at = tokens.expires_at
        cred.scopes = tokens.scopes
        await self._db.flush()


class QueryService:
    def __init__(self, db: AsyncSession) -> None:
        self._db: AsyncSession = db

    async def query_by_user(
        self,
        *,
        user_id: uuid.UUID,
        question: str,
        limit: int = 25,
    ) -> list[Person]:
        company: str | None = company_query_from_question(question)
        name_hint: str | None = name_query_from_question(question)
        needs_filter: bool = company is not None or name_hint is not None
        fetch_limit: int = 500 if needs_filter else limit
        stmt = (
            select(Person)
            .options(selectinload(Person.edge))
            .where(Person.user_id == user_id)
            .order_by(Person.last_seen_in_email.desc().nullslast())
            .limit(fetch_limit)
        )
        result = await self._db.execute(stmt)
        people: list[Person] = list(result.scalars().all())

        if not needs_filter:
            return people[:limit]

        filtered: list[Person] = []
        company_lower: str | None = company.lower() if company else None
        for person in people:
            if name_hint is not None and not person_matches_name(
                person.canonical_name,
                list(person.email_addresses),
                name_hint,
            ):
                continue
            if company_lower is not None:
                org_match: bool = bool(
                    person.current_org_name
                    and company_lower in person.current_org_name.lower()
                )
                name_match: bool = company_lower in person.canonical_name.lower()
                email_match: bool = any(
                    company_lower in email.split("@", 1)[-1]
                    for email in person.email_addresses
                )
                if not (org_match or name_match or email_match):
                    continue
            filtered.append(person)

        filtered.sort(
            key=lambda p: (
                p.edge.tie_strength_score if p.edge else 0.0,
                p.last_seen_in_email.timestamp() if p.last_seen_in_email else 0.0,
            ),
            reverse=True,
        )
        return filtered[:limit]
