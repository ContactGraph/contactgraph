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
from contactsafe_server.services.crypto import TokenEncryptor
from contactsafe_server.services.email_parse import (
    ContactAccumulator,
    email_local_part,
    email_lookup_variants,
    is_likely_self_contact,
    org_name_from_email,
    parse_address_header,
    parse_internal_date_ms,
    sanitize_display_name,
)
from contactsafe_server.services.contact_classifier import (
    classify_contact,
    compute_tie_strength,
)
from contactsafe_server.services.entity_resolution import EntityResolver
from contactsafe_server.services.ingest_enrichment_service import IngestEnrichmentService
from contactsafe_server.services.interaction_excerpt_service import InteractionExcerptService
from contactsafe_server.services.org_search import is_automation_or_generic_domain
from contactsafe_server.services.gmail_client import (
    GmailClient,
    GmailMessageMeta,
    GmailMessageRef,
)
from contactsafe_server.services.pitch_detection import (
    is_pitch_outreach_snippet,
    message_from_user,
)

logger: logging.Logger = logging.getLogger(__name__)


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

            resolver = EntityResolver(self._db)

            source_email: str = source.external_account_id or user.email
            contacts, person_pair_counts, upserted_emails = await self._scan_and_ingest_gmail(
                access_token=access_token,
                user_email=source_email,
                user_id=user_id,
                source=source,
                resolver=resolver,
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
                person_pair_counts=person_pair_counts,
                resolver=resolver,
            )

            await self._rebuild_user_org_observations(user_id)

            enricher = IngestEnrichmentService(self._db, self._settings)
            await enricher.enrich_after_import(
                user_id=user_id,
                contact_by_email=contacts,
            )
            await self._rebuild_user_org_observations(user_id)

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

    async def _scan_and_ingest_gmail(
        self,
        *,
        access_token: str,
        user_email: str,
        user_id: uuid.UUID,
        source: Source,
        resolver: EntityResolver,
    ) -> tuple[
        dict[str, ContactAccumulator],
        dict[tuple[str, str], tuple[int, datetime | None]],
        set[str],
    ]:
        contacts: dict[str, ContactAccumulator] = {}
        pair_stats: dict[tuple[str, str], tuple[int, datetime | None]] = {}
        upserted_emails: set[str] = set()
        user_emails, user_local_parts = await self._load_user_identity(
            user_email=user_email,
            source=source,
        )
        page_token: str | None = None
        messages_scanned: int = 0
        messages_since_commit: int = 0
        max_messages: int = self._settings.import_max_messages
        commit_interval: int = max(1, self._settings.import_progress_commit_messages)

        while messages_scanned < max_messages:
            batch_size: int = min(100, max_messages - messages_scanned)
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
            "Gmail scan complete: fetched=%s contacts=%s person_pairs=%s resolved=%s",
            messages_scanned,
            len(contacts),
            len(pair_stats),
            len(upserted_emails),
        )
        return contacts, pair_stats, upserted_emails

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

        stmt = pg_insert(UserPersonObservation).values(
            user_id=user_id,
            person_id=person.id,
            first_observed_at=accumulator.last_seen_at,
            last_observed_at=accumulator.last_seen_at,
            last_genuine_interaction_at=accumulator.last_seen_at if classification.is_human else None,
            email_count=accumulator.message_count,
            outbound_count=accumulator.outbound_count,
            inbound_count=accumulator.inbound_count,
            thread_count=accumulator.message_count,
            tie_strength_score=tie_strength,
            is_broadcast=classification.is_broadcast,
            is_human=classification.is_human,
            is_automated=classification.is_automated,
            relationship_types=["contact"],
            notes=f"Imported from Gmail metadata for {user_email}",
            source_id=source_id,
        )
        stmt = stmt.on_conflict_do_update(
            constraint="pk_user_person_obs",
            set_={
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
                "notes": stmt.excluded.notes,
                "source_id": stmt.excluded.source_id,
                "updated_at": stmt.excluded.updated_at,
            },
        )
        await self._db.execute(stmt)

        if not classification.is_automated:
            domain: str = accumulator.email.rsplit("@", 1)[1].lower()
            if not is_automation_or_generic_domain(domain):
                org_name_hint: str | None = org_name_from_email(accumulator.email)
                org = await resolver.resolve_org(domain=domain, name=org_name_hint)
                await record_employment(
                    self._db,
                    person_id=person.id,
                    org_id=org.id,
                    contributor_user_id=user_id,
                    contributor_source_kind="gmail_domain",
                    contributor_source_id=source_id,
                    confidence=0.5,
                )

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

    async def _rebuild_user_org_observations(self, user_id: uuid.UUID) -> None:
        from contactsafe_server.db.models import (
            EmploymentClaim,
            Org,
            UserOrgObservation,
            UserPersonObservation,
        )

        result = await self._db.execute(
            select(
                EmploymentClaim.org_id,
                EmploymentClaim.person_id,
                UserPersonObservation.email_count,
                UserPersonObservation.last_observed_at,
                UserPersonObservation.tie_strength_score,
            )
            .join(
                UserPersonObservation,
                (UserPersonObservation.person_id == EmploymentClaim.person_id)
                & (UserPersonObservation.user_id == user_id),
            )
            .where(EmploymentClaim.is_current.is_(True))
        )
        rows = result.all()

        by_org: dict[uuid.UUID, dict[str, object]] = {}
        for org_id, person_id, email_count, last_at, tie in rows:
            bucket = by_org.setdefault(org_id, {
                "person_ids": set(),
                "email_count": 0,
                "tie": 0.0,
                "last_at": None,
            })
            pid_set: set[uuid.UUID] = bucket["person_ids"]  # type: ignore[assignment]
            pid_set.add(person_id)
            bucket["email_count"] = int(bucket["email_count"]) + email_count  # type: ignore[arg-type]
            bucket["tie"] = max(float(bucket["tie"]), tie)  # type: ignore[arg-type]
            prev: datetime | None = bucket["last_at"]  # type: ignore[assignment]
            if last_at is not None and (prev is None or last_at > prev):
                bucket["last_at"] = last_at

        for org_id, bucket in by_org.items():
            pid_set = bucket["person_ids"]  # type: ignore[assignment]
            stmt = pg_insert(UserOrgObservation).values(
                user_id=user_id,
                org_id=org_id,
                associated_person_ids=sorted(pid_set),
                total_email_count=int(bucket["email_count"]),  # type: ignore[arg-type]
                last_interaction_at=bucket["last_at"],  # type: ignore[arg-type]
                tie_strength_score=float(bucket["tie"]),  # type: ignore[arg-type]
                relationship_types=["contact"],
            )
            stmt = stmt.on_conflict_do_update(
                constraint="pk_user_org_obs",
                set_={
                    "associated_person_ids": stmt.excluded.associated_person_ids,
                    "total_email_count": stmt.excluded.total_email_count,
                    "last_interaction_at": stmt.excluded.last_interaction_at,
                    "tie_strength_score": stmt.excluded.tie_strength_score,
                    "updated_at": stmt.excluded.updated_at,
                },
            )
            await self._db.execute(stmt)
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
