import logging
import uuid
from collections.abc import Iterable
from datetime import UTC, datetime
from itertools import combinations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert as pg_insert

from contactsafe_core.enums import IdentityKind, OAuthProvider, SourceConnectionStatus, SourceType, SyncState
from contactsafe_server.config import Settings
from contactsafe_server.db.models import (
    OAuthCredential,
    Person,
    Source,
    User,
    UserIdentity,
    UserPersonObservation,
    UserRelationshipObservation,
)
from contactsafe_server.oauth.google import GoogleTokens
from contactsafe_server.services.claim_writer import record_employment, record_relationship
from contactsafe_server.services.org_search import is_automation_or_generic_domain
from contactsafe_server.services.crypto import TokenEncryptor
from contactsafe_server.services.email_parse import (
    ContactAccumulator,
    email_local_part,
    email_lookup_variants,
    is_likely_self_contact,
    normalize_email,
    parse_address_header,
    parse_internal_date_ms,
    sanitize_display_name,
)
from contactsafe_server.services.contact_classifier import (
    classify_contact,
    compute_tie_strength,
)
from contactsafe_server.services.entity_resolution import EntityResolver
from contactsafe_server.services.gmail_client import (
    GmailClient,
    GmailMessageListPage,
    GmailMessageMeta,
    GmailMessageRef,
)
from contactsafe_server.services.people_api_client import GoogleContact, PeopleApiClient
from contactsafe_server.services.pitch_detection import (
    is_pitch_outreach_snippet,
    message_from_user,
)
from contactsafe_server.services.user_org_observation_service import rebuild_user_org_observations

logger: logging.Logger = logging.getLogger(__name__)


class ImportService:
    SENT_MAIL_QUERY: str = "in:sent"

    def __init__(
        self,
        db: AsyncSession,
        settings: Settings,
        encryptor: TokenEncryptor,
        gmail: GmailClient,
        people_client: PeopleApiClient | None = None,
    ) -> None:
        self._db: AsyncSession = db
        self._settings: Settings = settings
        self._encryptor: TokenEncryptor = encryptor
        self._gmail: GmailClient = gmail
        self._people: PeopleApiClient | None = people_client

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

            resolver = EntityResolver(self._db)

            source_email: str = source.external_account_id or user.email
            user_emails, user_local_parts = await self._load_user_identity(
                user_email=source_email,
                source=source,
            )
            contacts: dict[str, ContactAccumulator] = {}
            pair_stats: dict[tuple[str, str], tuple[int, datetime | None]] = {}
            upserted_emails: set[str] = set()

            await self._phase1_google_contacts_seed(
                access_token=access_token,
                user_id=user_id,
                user_email=source_email,
                source=source,
                resolver=resolver,
                user_emails=user_emails,
                user_local_parts=user_local_parts,
                contacts=contacts,
                upserted_emails=upserted_emails,
            )

            await self._phase2_sent_mail_scan(
                access_token=access_token,
                user_email=source_email,
                user_id=user_id,
                source=source,
                resolver=resolver,
                user_emails=user_emails,
                user_local_parts=user_local_parts,
                contacts=contacts,
                pair_stats=pair_stats,
                upserted_emails=upserted_emails,
            )

            await self._phase3_contact_timelines(
                access_token=access_token,
                user_id=user_id,
                user_email=source_email,
                source=source,
                resolver=resolver,
                contacts=contacts,
                upserted_emails=upserted_emails,
            )

            sorted_contacts: list[ContactAccumulator] = sorted(
                contacts.values(),
                key=lambda c: (
                    c.last_seen_at or datetime.min.replace(tzinfo=UTC),
                    c.message_count,
                ),
                reverse=True,
            )

            for accumulator in sorted_contacts:
                if accumulator.email in upserted_emails:
                    continue
                await self._upsert_person(
                    user_id,
                    source_email,
                    accumulator,
                    source_id=source.id,
                    resolver=resolver,
                )
                upserted_emails.add(accumulator.email)
                source.contacts_resolved = len(upserted_emails)
                source.contacts_pending = max(0, source.contacts_found - source.contacts_resolved)
                await self._db.flush()

            await self._commit_progress(source)

            await self._upsert_person_pair_observations(
                user_id=user_id,
                source_id=source.id,
                person_pair_counts=pair_stats,
                resolver=resolver,
            )

            await rebuild_user_org_observations(self._db, user_id)

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
            select(Source)
            .where(
                Source.user_id == user_id,
                Source.source_type == SourceType.GOOGLE_MAIL.value,
            )
            .order_by(Source.created_at)
        )
        sources: list[Source] = list(result.scalars().all())
        for source in sources:
            await self.run_sync(source.id)

    async def _commit_progress(self, source: Source) -> None:
        await self._db.commit()
        await self._db.refresh(source)

    async def _phase1_google_contacts_seed(
        self,
        *,
        access_token: str,
        user_id: uuid.UUID,
        user_email: str,
        source: Source,
        resolver: EntityResolver,
        user_emails: set[str],
        user_local_parts: set[str],
        contacts: dict[str, ContactAccumulator],
        upserted_emails: set[str],
    ) -> None:
        if self._people is None:
            logger.warning(
                "PeopleApiClient not configured; skipping Phase 1 Google Contacts seed",
            )
            return

        page_token: str | None = None
        contacts_fetched: int = 0
        max_results: int = self._settings.import_contacts_max_results
        page_size: int = self._settings.import_contacts_page_size

        while contacts_fetched < max_results:
            page = await self._people.list_connections(
                access_token,
                page_size=min(page_size, max_results - contacts_fetched),
                page_token=page_token,
                request_sync_token=False,
            )

            for contact in page.contacts:
                if contact.is_deleted or not contact.emails:
                    continue
                contacts_fetched += 1

                for raw_email in contact.emails:
                    email: str | None = normalize_email(raw_email)
                    if email is None:
                        continue
                    if is_likely_self_contact(
                        email,
                        user_emails=user_emails,
                        user_local_parts=user_local_parts,
                    ):
                        continue

                    display_name: str = sanitize_display_name(
                        contact.display_name or email,
                        email,
                    )
                    existing: ContactAccumulator | None = contacts.get(email)
                    if existing is None:
                        contacts[email] = ContactAccumulator(
                            email=email,
                            display_name=display_name,
                            from_google_contacts=True,
                        )
                    else:
                        existing.from_google_contacts = True
                        if display_name and (
                            not existing.display_name or existing.display_name == email
                        ):
                            existing.display_name = display_name

                    await self._upsert_google_contact_details(
                        contact=contact,
                        email=email,
                        display_name=display_name,
                        user_id=user_id,
                        source_id=source.id,
                        resolver=resolver,
                    )
                    await self._upsert_person(
                        user_id,
                        user_email,
                        contacts[email],
                        source_id=source.id,
                        resolver=resolver,
                    )
                    upserted_emails.add(email)

            source.contacts_found = len(contacts)
            source.contacts_resolved = len(upserted_emails)
            source.contacts_pending = max(0, source.contacts_found - source.contacts_resolved)
            if (
                source.sync_state == SyncState.SYNCING.value
                and source.contacts_resolved >= self._settings.import_partial_contact_target
            ):
                source.sync_state = SyncState.PARTIAL.value
            await self._db.flush()
            await self._commit_progress(source)

            page_token = page.next_page_token
            if page_token is None:
                break

        logger.info(
            "Phase 1 Google Contacts seed complete: contacts=%s resolved=%s",
            len(contacts),
            len(upserted_emails),
        )

    async def _phase2_sent_mail_scan(
        self,
        *,
        access_token: str,
        user_email: str,
        user_id: uuid.UUID,
        source: Source,
        resolver: EntityResolver,
        user_emails: set[str],
        user_local_parts: set[str],
        contacts: dict[str, ContactAccumulator],
        pair_stats: dict[tuple[str, str], tuple[int, datetime | None]],
        upserted_emails: set[str],
    ) -> None:
        page_token: str | None = None
        messages_scanned: int = 0
        messages_since_commit: int = 0
        max_messages: int = self._settings.import_sent_max_messages
        commit_interval: int = max(1, self._settings.import_progress_commit_messages)

        while messages_scanned < max_messages:
            batch_size: int = min(100, max_messages - messages_scanned)
            page: GmailMessageListPage = await self._gmail.list_message_refs(
                access_token,
                max_results=batch_size,
                page_token=page_token,
                query=self.SENT_MAIL_QUERY,
            )
            if not page.refs:
                break

            for ref in page.refs:
                meta: GmailMessageMeta = await self._gmail.get_message_metadata(
                    access_token, ref.id
                )
                self._accumulate_message(
                    contacts=contacts,
                    pair_stats=pair_stats,
                    meta=meta,
                    ref=ref,
                    user_email=user_email,
                    user_emails=user_emails,
                    user_local_parts=user_local_parts,
                )
                messages_scanned += 1
                messages_since_commit += 1
                if messages_since_commit >= commit_interval:
                    await self._flush_ingest_progress(
                        contacts=contacts,
                        upserted_emails=upserted_emails,
                        user_id=user_id,
                        user_email=user_email,
                        source=source,
                        messages_scanned=messages_scanned,
                        resolver=resolver,
                    )
                    messages_since_commit = 0

            page_token = page.next_page_token
            if page_token is None:
                break

        if messages_since_commit > 0:
            await self._flush_ingest_progress(
                contacts=contacts,
                upserted_emails=upserted_emails,
                user_id=user_id,
                user_email=user_email,
                source=source,
                messages_scanned=messages_scanned,
                resolver=resolver,
            )

        logger.info(
            "Phase 2 sent mail scan complete: fetched=%s contacts=%s person_pairs=%s resolved=%s",
            messages_scanned,
            len(contacts),
            len(pair_stats),
            len(upserted_emails),
        )

    async def _phase3_contact_timelines(
        self,
        *,
        access_token: str,
        user_id: uuid.UUID,
        user_email: str,
        source: Source,
        resolver: EntityResolver,
        contacts: dict[str, ContactAccumulator],
        upserted_emails: set[str],
    ) -> None:
        sorted_contacts: list[ContactAccumulator] = sorted(
            contacts.values(),
            key=lambda c: (
                c.last_seen_at or datetime.min.replace(tzinfo=UTC),
                c.message_count,
            ),
            reverse=True,
        )
        timeline_contacts: list[ContactAccumulator] = sorted_contacts[
            : self._settings.import_timeline_max_contacts
        ]
        commit_interval: int = max(1, self._settings.import_progress_commit_messages)
        timelines_fetched: int = 0

        for accumulator in timeline_contacts:
            timeline = await self._gmail.get_contact_timeline(
                access_token,
                accumulator.email,
                max_pages=self._settings.import_timeline_max_pages,
            )
            accumulator.apply_timeline(
                earliest_date=timeline.earliest_date,
                latest_date=timeline.latest_date,
                estimated_count=timeline.estimated_count,
            )
            await self._upsert_person(
                user_id,
                user_email,
                accumulator,
                source_id=source.id,
                resolver=resolver,
            )
            upserted_emails.add(accumulator.email)
            timelines_fetched += 1

            if timelines_fetched % commit_interval == 0:
                source.contacts_found = len(contacts)
                source.contacts_resolved = len(upserted_emails)
                source.contacts_pending = max(
                    0, source.contacts_found - source.contacts_resolved
                )
                await self._db.flush()
                await self._commit_progress(source)

        source.contacts_found = len(contacts)
        source.contacts_resolved = len(upserted_emails)
        source.contacts_pending = max(0, source.contacts_found - source.contacts_resolved)
        await self._db.flush()
        await self._commit_progress(source)

        logger.info(
            "Phase 3 contact timelines complete: timelines=%s contacts=%s",
            timelines_fetched,
            len(contacts),
        )

    async def _upsert_google_contact_details(
        self,
        *,
        contact: GoogleContact,
        email: str,
        display_name: str,
        user_id: uuid.UUID,
        source_id: uuid.UUID,
        resolver: EntityResolver,
    ) -> None:
        phone: str | None = contact.phone_numbers[0] if contact.phone_numbers else None
        person: Person = await resolver.resolve_person(
            emails=[email],
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

        if contact.org_name and not person.current_org_name:
            domain: str | None = None
            if "@" in email:
                email_domain: str = email.rsplit("@", 1)[1].lower()
                if not is_automation_or_generic_domain(email_domain):
                    domain = email_domain
            org = await resolver.resolve_org(domain=domain, name=contact.org_name)
            await record_employment(
                self._db,
                person_id=person.id,
                org_id=org.id,
                role_title=contact.org_title,
                contributor_user_id=user_id,
                contributor_source_kind="google_contacts",
                contributor_source_id=source_id,
                confidence=0.5,
            )

    async def _flush_ingest_progress(
        self,
        *,
        contacts: dict[str, ContactAccumulator],
        upserted_emails: set[str],
        user_id: uuid.UUID,
        user_email: str,
        source: Source,
        messages_scanned: int,
        resolver: EntityResolver,
    ) -> None:
        source.contacts_found = len(contacts)
        source.contacts_pending = max(0, source.contacts_found - len(upserted_emails))

        sorted_contacts: list[ContactAccumulator] = sorted(
            contacts.values(),
            key=lambda c: (
                c.last_seen_at or datetime.min.replace(tzinfo=UTC),
                c.message_count,
            ),
            reverse=True,
        )

        refresh_limit: int = max(
            self._settings.import_partial_contact_target,
            self._settings.import_initial_contact_target,
        )
        refresh_emails: set[str] = {
            acc.email for acc in sorted_contacts[:refresh_limit]
        }

        for accumulator in sorted_contacts:
            if (
                accumulator.email not in upserted_emails
                or accumulator.email in refresh_emails
            ):
                await self._upsert_person(
                    user_id,
                    user_email,
                    accumulator,
                    source_id=source.id,
                    resolver=resolver,
                )
                upserted_emails.add(accumulator.email)

        source.contacts_resolved = len(upserted_emails)
        source.contacts_pending = max(0, source.contacts_found - source.contacts_resolved)

        if (
            source.sync_state == SyncState.SYNCING.value
            and source.contacts_resolved >= self._settings.import_partial_contact_target
        ):
            source.sync_state = SyncState.PARTIAL.value

        await self._db.flush()
        await self._commit_progress(source)
        logger.info(
            "Sync progress for source %s: messages=%s contacts_found=%s resolved=%s state=%s",
            source.id,
            messages_scanned,
            source.contacts_found,
            source.contacts_resolved,
            source.sync_state,
        )

    def _accumulate_message(
        self,
        *,
        contacts: dict[str, ContactAccumulator],
        pair_stats: dict[tuple[str, str], tuple[int, datetime | None]],
        meta: GmailMessageMeta,
        ref: GmailMessageRef,
        user_email: str,
        user_emails: set[str] | None = None,
        user_local_parts: set[str] | None = None,
    ) -> None:
        owned_emails: set[str] = user_emails or {user_email.strip().lower()}
        owned_locals: set[str] = user_local_parts or {email_local_part(user_email)}
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
                user_emails=owned_emails,
                user_local_parts=owned_locals,
                seen_at=seen_at,
            )
            self._tag_pitch_recipients(
                contacts,
                header=meta.cc_header,
                user_emails=owned_emails,
                user_local_parts=owned_locals,
                seen_at=seen_at,
            )
        self._accumulate_header(
            contacts,
            header=meta.from_header,
            user_emails=owned_emails,
            user_local_parts=owned_locals,
            seen_at=seen_at,
            from_user=False,
            snippet=meta.snippet,
            has_list_unsubscribe=meta.has_list_unsubscribe,
        )
        self._accumulate_header(
            contacts,
            header=meta.to_header,
            user_emails=owned_emails,
            user_local_parts=owned_locals,
            seen_at=seen_at,
            from_user=True,
        )
        self._accumulate_header(
            contacts,
            header=meta.cc_header,
            user_emails=owned_emails,
            user_local_parts=owned_locals,
            seen_at=seen_at,
            from_user=True,
        )
        participants = self._collect_participants(
            user_emails=owned_emails,
            user_local_parts=owned_locals,
            headers=(meta.from_header, meta.to_header, meta.cc_header),
        )
        self._accumulate_pair_stats(
            pair_stats=pair_stats,
            participants=participants,
            seen_at=seen_at,
        )

    def _accumulate_header(
        self,
        contacts: dict[str, ContactAccumulator],
        *,
        header: str | None,
        user_emails: set[str],
        user_local_parts: set[str],
        seen_at: datetime | None,
        from_user: bool,
        snippet: str | None = None,
        has_list_unsubscribe: bool = False,
    ) -> None:
        if not header:
            return
        for display_name, email in parse_address_header(header):
            if is_likely_self_contact(
                email,
                user_emails=user_emails,
                user_local_parts=user_local_parts,
            ):
                continue
            cleaned_name: str = sanitize_display_name(display_name, email)
            existing: ContactAccumulator | None = contacts.get(email)
            if existing is None:
                contacts[email] = ContactAccumulator(
                    email=email,
                    display_name=cleaned_name,
                    last_seen_at=seen_at,
                )
                existing = contacts[email]
            existing.observe(
                display_name=cleaned_name,
                seen_at=seen_at,
                from_user=from_user,
                snippet=snippet if not from_user else None,
                has_list_unsubscribe=has_list_unsubscribe if not from_user else False,
            )

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
        self,
        *,
        user_emails: set[str],
        user_local_parts: set[str],
        headers: Iterable[str | None],
    ) -> list[str]:
        participants: set[str] = set()
        for header in headers:
            if not header:
                continue
            for _, email in parse_address_header(header):
                if not is_likely_self_contact(
                    email,
                    user_emails=user_emails,
                    user_local_parts=user_local_parts,
                ):
                    participants.add(email)
        return sorted(participants)

    def _tag_pitch_recipients(
        self,
        contacts: dict[str, ContactAccumulator],
        *,
        header: str | None,
        user_emails: set[str],
        user_local_parts: set[str],
        seen_at: datetime | None,
    ) -> None:
        if not header:
            return
        for display_name, email in parse_address_header(header):
            if is_likely_self_contact(
                email,
                user_emails=user_emails,
                user_local_parts=user_local_parts,
            ):
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
        *,
        source_id: uuid.UUID,
        resolver: EntityResolver,
    ) -> None:
        classification = classify_contact(accumulator)
        display_name: str = sanitize_display_name(
            accumulator.display_name, accumulator.email
        )

        person: Person = await resolver.resolve_person(
            emails=[accumulator.email],
            display_name=display_name,
        )

        if display_name and (
            not person.canonical_name
            or person.canonical_name == accumulator.email
            or (
                accumulator.last_seen_at is not None
                and person.updated_at is not None
                and accumulator.last_seen_at > person.updated_at
            )
        ):
            person.canonical_name = display_name

        tie_strength: float = compute_tie_strength(accumulator, classification)
        if accumulator.from_google_contacts and accumulator.message_count == 0:
            tie_strength = max(tie_strength, 0.3)

        relationship_types: list[str] = (
            ["contact", "google_contact"]
            if accumulator.from_google_contacts
            else ["contact"]
        )
        first_observed: datetime | None = (
            accumulator.first_seen_at or accumulator.last_seen_at
        )

        import_snippets: list[str] | None = (
            list(accumulator.inbound_snippets)
            if accumulator.inbound_snippets
            else None
        )

        stmt = pg_insert(UserPersonObservation).values(
            user_id=user_id,
            person_id=person.id,
            first_observed_at=first_observed,
            last_observed_at=accumulator.last_seen_at,
            last_genuine_interaction_at=accumulator.last_seen_at if classification.is_human else None,
            email_count=accumulator.message_count,
            outbound_count=accumulator.outbound_count,
            inbound_count=accumulator.inbound_count,
            thread_count=accumulator.message_count,
            tie_strength_score=tie_strength,
            is_broadcast=classification.is_broadcast,
            is_human=classification.is_human or accumulator.from_google_contacts,
            is_automated=classification.is_automated,
            relationship_types=relationship_types,
            notes=f"Imported from Gmail metadata for {user_email}",
            import_snippets=import_snippets,
            source_id=source_id,
        )
        stmt = stmt.on_conflict_do_update(
            constraint="pk_user_person_obs",
            set_={
                "first_observed_at": stmt.excluded.first_observed_at,
                "last_observed_at": stmt.excluded.last_observed_at,
                "last_genuine_interaction_at": stmt.excluded.last_genuine_interaction_at,
                "email_count": stmt.excluded.email_count,
                "outbound_count": stmt.excluded.outbound_count,
                "inbound_count": stmt.excluded.inbound_count,
                "thread_count": stmt.excluded.thread_count,
                "tie_strength_score": stmt.excluded.tie_strength_score,
                "is_broadcast": stmt.excluded.is_broadcast,
                "is_human": stmt.excluded.is_human,
                "is_automated": stmt.excluded.is_automated,
                "relationship_types": stmt.excluded.relationship_types,
                "notes": stmt.excluded.notes,
                "import_snippets": stmt.excluded.import_snippets,
                "source_id": stmt.excluded.source_id,
                "updated_at": stmt.excluded.updated_at,
            },
        )
        await self._db.execute(stmt)

    async def _upsert_person_pair_observations(
        self,
        *,
        user_id: uuid.UUID,
        source_id: uuid.UUID,
        person_pair_counts: dict[tuple[str, str], tuple[int, datetime | None]],
        resolver: EntityResolver,
    ) -> None:
        if not person_pair_counts:
            return

        from contactsafe_server.db.models import PersonAlias
        result = await self._db.execute(
            select(PersonAlias.value, PersonAlias.person_id).where(PersonAlias.kind == "email")
        )
        by_email: dict[str, uuid.UUID] = {row[0]: row[1] for row in result.all()}

        for (left_email, right_email), (count, last_seen) in person_pair_counts.items():
            left_id: uuid.UUID | None = by_email.get(left_email)
            right_id: uuid.UUID | None = by_email.get(right_email)
            if left_id is None or right_id is None:
                continue
            if left_id == right_id:
                continue

            a_id: uuid.UUID = min(left_id, right_id)
            b_id: uuid.UUID = max(left_id, right_id)

            stmt = pg_insert(UserRelationshipObservation).values(
                user_id=user_id,
                person_a_id=a_id,
                person_b_id=b_id,
                co_thread_count=count,
                last_seen_together_at=last_seen,
                source_id=source_id,
            )
            stmt = stmt.on_conflict_do_update(
                constraint="pk_user_rel_obs",
                set_={
                    "co_thread_count": stmt.excluded.co_thread_count,
                    "last_seen_together_at": stmt.excluded.last_seen_together_at,
                    "updated_at": stmt.excluded.updated_at,
                },
            )
            await self._db.execute(stmt)

            await record_relationship(
                self._db,
                person_a_id=a_id,
                person_b_id=b_id,
                kind="co_thread",
                observed_count=count,
                contributor_user_id=user_id,
                contributor_source_kind="gmail",
                last_seen_together_at=last_seen,
            )

        await self._db.flush()

    async def _load_user_identity(
        self,
        *,
        user_email: str,
        source: Source,
    ) -> tuple[set[str], set[str]]:
        emails: set[str] = {user_email.strip().lower()}
        if source.external_account_id:
            emails.add(source.external_account_id.strip().lower())
        result = await self._db.execute(
            select(UserIdentity.value).where(
                UserIdentity.user_id == source.user_id,
                UserIdentity.kind == IdentityKind.EMAIL.value,
            )
        )
        for row_value in result.scalars().all():
            emails.add(str(row_value).strip().lower())
        local_parts: set[str] = {email_local_part(email) for email in emails}
        return emails, local_parts

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
