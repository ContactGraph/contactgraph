import logging
import uuid
from collections.abc import Iterable
from datetime import UTC, datetime
from itertools import combinations

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from contactsafe_core.enums import OAuthProvider, SourceConnectionStatus, SourceType, SyncState
from contactsafe_server.config import Settings
from contactsafe_server.db.models import (
    OAuthCredential,
    Person,
    PersonEdge,
    PersonPersonEdge,
    Source,
    User,
)
from contactsafe_server.oauth.google import GoogleTokens
from contactsafe_server.services.crypto import TokenEncryptor
from contactsafe_server.services.email_parse import (
    ContactAccumulator,
    org_name_from_email,
    parse_address_header,
    parse_internal_date_ms,
)
from contactsafe_server.services.ingest_enrichment_service import (
    IngestEnrichmentService,
    edge_flags_from_accumulator,
)
from contactsafe_server.services.interaction_excerpt_service import InteractionExcerptService
from contactsafe_server.services.org_service import OrgService
from contactsafe_server.services.gmail_client import GmailClient, GmailMessageMeta
from contactsafe_server.services.pitch_detection import (
    is_pitch_outreach_snippet,
    message_from_user,
)

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

            contacts, person_pair_counts = await self._scan_gmail(
                access_token=access_token,
                user_email=user.email,
            )
            source.contacts_found = len(contacts)
            source.contacts_pending = max(
                0, len(contacts) - self._settings.import_initial_contact_target
            )
            await self._db.flush()

            await self._db.execute(delete(PersonEdge).where(PersonEdge.user_id == user_id))
            await self._db.execute(
                delete(PersonPersonEdge).where(PersonPersonEdge.user_id == user_id)
            )
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

            await self._upsert_person_person_edges(
                user_id=user_id,
                person_pair_counts=person_pair_counts,
            )

            enricher = IngestEnrichmentService(self._db, self._settings)
            await enricher.enrich_after_import(
                user_id=user_id,
                contact_by_email=contacts,
            )
            await self._link_orgs_for_user(user_id)
            excerpt_service = InteractionExcerptService(self._db, self._settings)
            await excerpt_service.seed_excerpts_for_user(user_id)

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
    ) -> tuple[
        dict[str, ContactAccumulator],
        dict[tuple[str, str], tuple[int, datetime | None]],
    ]:
        contacts: dict[str, ContactAccumulator] = {}
        pair_stats: dict[tuple[str, str], tuple[int, datetime | None]] = {}
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
                if (
                    meta.snippet
                    and message_from_user(meta.from_header, user_email)
                    and is_pitch_outreach_snippet(meta.snippet)
                ):
                    self._tag_pitch_recipients(
                        contacts,
                        header=meta.to_header,
                        user_email=user_email,
                        seen_at=seen_at,
                    )
                    self._tag_pitch_recipients(
                        contacts,
                        header=meta.cc_header,
                        user_email=user_email,
                        seen_at=seen_at,
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
                participants = self._collect_participants(
                    user_email=user_email,
                    headers=(meta.from_header, meta.to_header, meta.cc_header),
                )
                self._accumulate_pair_stats(
                    pair_stats=pair_stats,
                    participants=participants,
                    seen_at=seen_at,
                )
            fetched += len(refs)
            if page_token is None:
                break

        logger.info(
            "Gmail scan complete: fetched=%s contacts=%s person_pairs=%s",
            fetched,
            len(contacts),
            len(pair_stats),
        )
        return contacts, pair_stats

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

    def _accumulate_pair_stats(
        self,
        *,
        pair_stats: dict[tuple[str, str], tuple[int, datetime | None]],
        participants: list[str],
        seen_at: datetime | None,
    ) -> None:
        for pair in combinations(participants, 2):
            left, right = tuple(sorted(pair))
            count, last_seen = pair_stats.get((left, right), (0, None))
            max_seen = (
                seen_at
                if last_seen is None or (seen_at and seen_at > last_seen)
                else last_seen
            )
            pair_stats[(left, right)] = (count + 1, max_seen)

    def _collect_participants(
        self, *, user_email: str, headers: Iterable[str | None]
    ) -> list[str]:
        participants: set[str] = set()
        for header in headers:
            if not header:
                continue
            for _, email in parse_address_header(header):
                if email != user_email:
                    participants.add(email)
        return sorted(participants)

    def _tag_pitch_recipients(
        self,
        contacts: dict[str, ContactAccumulator],
        *,
        header: str | None,
        user_email: str,
        seen_at: datetime | None,
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
            existing.pitch_outbound_count += 1

    async def _upsert_person(
        self,
        user_id: uuid.UUID,
        user_email: str,
        accumulator: ContactAccumulator,
    ) -> None:
        org_name: str | None = org_name_from_email(accumulator.email)
        org_service = OrgService(self._db)
        org = await org_service.resolve_org(
            user_id=user_id,
            email=accumulator.email,
            org_name_hint=org_name,
        )
        person = Person(
            user_id=user_id,
            canonical_name=accumulator.display_name,
            email_addresses=[accumulator.email],
            current_org_name=org.canonical_name if org else org_name,
            current_org_id=org.id if org else None,
            last_seen_in_email=accumulator.last_seen_at,
            confidence_score=0.85,
        )
        self._db.add(person)
        await self._db.flush()

        is_broadcast, is_human = edge_flags_from_accumulator(accumulator)
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
            if is_human
            else None,
            first_contact_date=accumulator.last_seen_at,
            tie_strength_score=tie_strength,
            is_broadcast=is_broadcast,
            is_human=is_human,
            notes=f"Imported from Gmail metadata for {user_email}",
        )
        self._db.add(edge)

    async def _link_orgs_for_user(self, user_id: uuid.UUID) -> None:
        result = await self._db.execute(select(Person).where(Person.user_id == user_id))
        for person in result.scalars().all():
            if person.current_org_id is not None or not person.email_addresses:
                continue
            org_name: str | None = person.current_org_name or org_name_from_email(
                person.email_addresses[0]
            )
            org_service = OrgService(self._db)
            org = await org_service.resolve_org(
                user_id=user_id,
                email=person.email_addresses[0],
                org_name_hint=org_name,
            )
            if org is not None:
                person.current_org_id = org.id
                if not person.current_org_name:
                    person.current_org_name = org.canonical_name
        await self._db.flush()

    async def _upsert_person_person_edges(
        self,
        *,
        user_id: uuid.UUID,
        person_pair_counts: dict[tuple[str, str], tuple[int, datetime | None]],
    ) -> None:
        if not person_pair_counts:
            return
        result = await self._db.execute(select(Person).where(Person.user_id == user_id))
        by_email: dict[str, uuid.UUID] = {}
        for person in result.scalars().all():
            for email in person.email_addresses:
                by_email[email] = person.id

        for (left_email, right_email), (count, last_seen) in person_pair_counts.items():
            left_id = by_email.get(left_email)
            right_id = by_email.get(right_email)
            if left_id is None or right_id is None:
                continue
            edge = PersonPersonEdge(
                user_id=user_id,
                left_person_id=left_id,
                right_person_id=right_id,
                co_occurrence_count=count,
                last_seen_at=last_seen,
            )
            self._db.add(edge)
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
                OAuthCredential.is_valid.is_(True),
            )
        )
        return result.scalar_one_or_none()

    async def _persist_tokens(self, cred: OAuthCredential, tokens: GoogleTokens) -> None:
        cred.access_token_encrypted = self._encryptor.encrypt(tokens.access_token)
        cred.token_expires_at = tokens.expires_at
        cred.scopes = tokens.scopes
        await self._db.flush()
