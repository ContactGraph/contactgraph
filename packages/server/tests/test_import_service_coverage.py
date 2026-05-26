"""Tests targeting uncovered lines in import_service.py.

Covers: run_sync, run_import, _load_user_identity, _upsert_person,
_get_credential_for_source, _persist_tokens, _accumulate_message,
_accumulate_header, _tag_pitch_recipients, _rebuild_user_org_observations,
_upsert_person_pair_observations, and error handling paths.
"""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from contactsafe_core.enums import (
    IdentityKind,
    OAuthProvider,
    SourceConnectionStatus,
    SourceType,
    SyncState,
)
from contactsafe_server.config import Settings
from contactsafe_server.services.email_parse import ContactAccumulator
from contactsafe_server.services.gmail_client import GmailMessageMeta, GmailMessageRef
from contactsafe_server.services.import_service import ImportService

pytestmark = pytest.mark.anyio


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_db() -> MagicMock:
    db: MagicMock = MagicMock()
    db.get = AsyncMock()
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    db.execute = AsyncMock()
    return db


def _make_source(
    *,
    user_id: uuid.UUID | None = None,
    source_type: str = SourceType.GOOGLE_MAIL.value,
) -> MagicMock:
    source: MagicMock = MagicMock()
    source.id = uuid.uuid4()
    source.user_id = user_id or uuid.uuid4()
    source.source_type = source_type
    source.external_account_id = "user@example.com"
    source.sync_state = SyncState.PENDING.value
    source.sync_started_at = None
    source.sync_error = None
    source.contacts_found = 0
    source.contacts_resolved = 0
    source.contacts_pending = 0
    source.sync_completed_at = None
    source.connection_status = SourceConnectionStatus.PENDING_OAUTH.value
    return source


def _make_user(user_id: uuid.UUID | None = None) -> MagicMock:
    user: MagicMock = MagicMock()
    user.id = user_id or uuid.uuid4()
    user.email = "user@example.com"
    return user


def _make_cred() -> MagicMock:
    cred: MagicMock = MagicMock()
    cred.access_token_encrypted = b"enc_access"
    cred.refresh_token_encrypted = b"enc_refresh"
    cred.token_expires_at = datetime(2099, 1, 1, tzinfo=UTC)
    cred.scopes = ["https://www.googleapis.com/auth/gmail.readonly"]
    cred.is_valid = True
    return cred


def _make_service(
    db: MagicMock | None = None,
    settings: Settings | None = None,
    gmail: MagicMock | None = None,
    encryptor: MagicMock | None = None,
) -> ImportService:
    return ImportService(
        db=db or _make_db(),
        settings=settings or Settings(),
        encryptor=encryptor or MagicMock(decrypt=MagicMock(return_value="decrypted_token")),
        gmail=gmail or MagicMock(),
    )


# ---------------------------------------------------------------------------
# run_sync – success path
# ---------------------------------------------------------------------------

class TestRunSync:
    async def test_returns_early_when_source_not_found(self) -> None:
        db: MagicMock = _make_db()
        db.get = AsyncMock(return_value=None)
        svc: ImportService = _make_service(db=db)

        await svc.run_sync(uuid.uuid4())

        db.flush.assert_not_awaited()

    async def test_raises_for_unsupported_source_type(self) -> None:
        source: MagicMock = _make_source(source_type=SourceType.GOOGLE_CALENDAR.value)
        db: MagicMock = _make_db()
        db.get = AsyncMock(side_effect=[source])
        svc: ImportService = _make_service(db=db)

        with pytest.raises(ValueError, match="Sync not supported"):
            await svc.run_sync(source.id)

    async def test_returns_early_when_user_not_found(self) -> None:
        source: MagicMock = _make_source()
        db: MagicMock = _make_db()
        db.get = AsyncMock(side_effect=[source, None])
        svc: ImportService = _make_service(db=db)

        await svc.run_sync(source.id)

        assert source.sync_state == SyncState.PENDING.value

    @patch("contactsafe_server.services.import_service.InteractionExcerptService")
    @patch("contactsafe_server.services.import_service.IngestEnrichmentService")
    @patch("contactsafe_server.services.import_service.EntityResolver")
    async def test_success_flow_sets_complete(
        self,
        mock_resolver_cls: MagicMock,
        mock_enricher_cls: MagicMock,
        mock_excerpt_cls: MagicMock,
    ) -> None:
        user_id: uuid.UUID = uuid.uuid4()
        source: MagicMock = _make_source(user_id=user_id)
        user: MagicMock = _make_user(user_id)

        db: MagicMock = _make_db()
        db.get = AsyncMock(side_effect=[source, user])

        gmail: MagicMock = MagicMock()
        gmail.get_valid_access_token = AsyncMock(return_value=("token", None))

        encryptor: MagicMock = MagicMock(decrypt=MagicMock(return_value="tok"))

        svc: ImportService = _make_service(db=db, gmail=gmail, encryptor=encryptor)
        svc._get_credential_for_source = AsyncMock(return_value=_make_cred())  # type: ignore[method-assign]
        svc._scan_and_ingest_gmail = AsyncMock(return_value=({}, {}, set()))  # type: ignore[method-assign]
        svc._upsert_person_pair_observations = AsyncMock()  # type: ignore[method-assign]
        svc._rebuild_user_org_observations = AsyncMock()  # type: ignore[method-assign]
        svc._commit_progress = AsyncMock()  # type: ignore[method-assign]

        mock_enricher_cls.return_value.enrich_after_import = AsyncMock()
        mock_excerpt_cls.return_value.seed_excerpts_for_user = AsyncMock()

        await svc.run_sync(source.id)

        assert source.sync_state == SyncState.COMPLETE.value
        assert source.connection_status == SourceConnectionStatus.CONNECTED.value
        assert source.contacts_pending == 0
        svc._scan_and_ingest_gmail.assert_awaited_once()

    @patch("contactsafe_server.services.import_service.InteractionExcerptService")
    @patch("contactsafe_server.services.import_service.IngestEnrichmentService")
    @patch("contactsafe_server.services.import_service.EntityResolver")
    async def test_success_flow_upserts_remaining_contacts(
        self,
        mock_resolver_cls: MagicMock,
        mock_enricher_cls: MagicMock,
        mock_excerpt_cls: MagicMock,
    ) -> None:
        """Contacts returned by _scan_and_ingest_gmail but not yet in upserted_emails get upserted."""
        user_id: uuid.UUID = uuid.uuid4()
        source: MagicMock = _make_source(user_id=user_id)
        user: MagicMock = _make_user(user_id)

        db: MagicMock = _make_db()
        db.get = AsyncMock(side_effect=[source, user])

        acc: ContactAccumulator = ContactAccumulator(
            email="new@example.com",
            display_name="New Person",
            last_seen_at=datetime(2025, 6, 1, tzinfo=UTC),
        )
        acc.message_count = 3

        gmail: MagicMock = MagicMock()
        gmail.get_valid_access_token = AsyncMock(return_value=("token", None))

        svc: ImportService = _make_service(db=db, gmail=gmail)
        svc._get_credential_for_source = AsyncMock(return_value=_make_cred())  # type: ignore[method-assign]
        svc._scan_and_ingest_gmail = AsyncMock(  # type: ignore[method-assign]
            return_value=({"new@example.com": acc}, {}, set())
        )
        svc._upsert_person = AsyncMock()  # type: ignore[method-assign]
        svc._upsert_person_pair_observations = AsyncMock()  # type: ignore[method-assign]
        svc._rebuild_user_org_observations = AsyncMock()  # type: ignore[method-assign]
        svc._commit_progress = AsyncMock()  # type: ignore[method-assign]

        mock_enricher_cls.return_value.enrich_after_import = AsyncMock()
        mock_excerpt_cls.return_value.seed_excerpts_for_user = AsyncMock()

        await svc.run_sync(source.id)

        svc._upsert_person.assert_awaited_once()
        assert source.sync_state == SyncState.COMPLETE.value

    @patch("contactsafe_server.services.import_service.InteractionExcerptService")
    @patch("contactsafe_server.services.import_service.IngestEnrichmentService")
    @patch("contactsafe_server.services.import_service.EntityResolver")
    async def test_skips_already_upserted_contacts(
        self,
        mock_resolver_cls: MagicMock,
        mock_enricher_cls: MagicMock,
        mock_excerpt_cls: MagicMock,
    ) -> None:
        user_id: uuid.UUID = uuid.uuid4()
        source: MagicMock = _make_source(user_id=user_id)
        user: MagicMock = _make_user(user_id)

        db: MagicMock = _make_db()
        db.get = AsyncMock(side_effect=[source, user])

        acc: ContactAccumulator = ContactAccumulator(
            email="done@example.com",
            display_name="Done",
            last_seen_at=datetime(2025, 1, 1, tzinfo=UTC),
        )

        gmail: MagicMock = MagicMock()
        gmail.get_valid_access_token = AsyncMock(return_value=("token", None))

        svc: ImportService = _make_service(db=db, gmail=gmail)
        svc._get_credential_for_source = AsyncMock(return_value=_make_cred())  # type: ignore[method-assign]
        svc._scan_and_ingest_gmail = AsyncMock(  # type: ignore[method-assign]
            return_value=({"done@example.com": acc}, {}, {"done@example.com"})
        )
        svc._upsert_person = AsyncMock()  # type: ignore[method-assign]
        svc._upsert_person_pair_observations = AsyncMock()  # type: ignore[method-assign]
        svc._rebuild_user_org_observations = AsyncMock()  # type: ignore[method-assign]
        svc._commit_progress = AsyncMock()  # type: ignore[method-assign]

        mock_enricher_cls.return_value.enrich_after_import = AsyncMock()
        mock_excerpt_cls.return_value.seed_excerpts_for_user = AsyncMock()

        await svc.run_sync(source.id)

        svc._upsert_person.assert_not_awaited()

    async def test_marks_failed_on_exception(self) -> None:
        source: MagicMock = _make_source()
        user: MagicMock = _make_user(source.user_id)
        db: MagicMock = _make_db()
        db.get = AsyncMock(side_effect=[source, user])

        svc: ImportService = _make_service(db=db)
        svc._get_credential_for_source = AsyncMock(return_value=None)  # type: ignore[method-assign]

        with pytest.raises(ValueError, match="No valid Google OAuth"):
            await svc.run_sync(source.id)

        assert source.sync_state == SyncState.FAILED.value
        assert source.sync_error is not None

    @patch("contactsafe_server.services.import_service.EntityResolver")
    async def test_marks_failed_on_gmail_error(
        self,
        mock_resolver_cls: MagicMock,
    ) -> None:
        source: MagicMock = _make_source()
        user: MagicMock = _make_user(source.user_id)
        db: MagicMock = _make_db()
        db.get = AsyncMock(side_effect=[source, user])

        gmail: MagicMock = MagicMock()
        gmail.get_valid_access_token = AsyncMock(return_value=("token", None))

        svc: ImportService = _make_service(db=db, gmail=gmail)
        svc._get_credential_for_source = AsyncMock(return_value=_make_cred())  # type: ignore[method-assign]
        svc._scan_and_ingest_gmail = AsyncMock(side_effect=RuntimeError("gmail down"))  # type: ignore[method-assign]

        with pytest.raises(RuntimeError, match="gmail down"):
            await svc.run_sync(source.id)

        assert source.sync_state == SyncState.FAILED.value
        assert "gmail down" in (source.sync_error or "")

    @patch("contactsafe_server.services.import_service.InteractionExcerptService")
    @patch("contactsafe_server.services.import_service.IngestEnrichmentService")
    @patch("contactsafe_server.services.import_service.EntityResolver")
    async def test_refreshed_tokens_are_persisted(
        self,
        mock_resolver_cls: MagicMock,
        mock_enricher_cls: MagicMock,
        mock_excerpt_cls: MagicMock,
    ) -> None:
        user_id: uuid.UUID = uuid.uuid4()
        source: MagicMock = _make_source(user_id=user_id)
        user: MagicMock = _make_user(user_id)

        db: MagicMock = _make_db()
        db.get = AsyncMock(side_effect=[source, user])

        refreshed_tokens: MagicMock = MagicMock()
        refreshed_tokens.access_token = "new_access"

        gmail: MagicMock = MagicMock()
        gmail.get_valid_access_token = AsyncMock(
            return_value=("old_token", refreshed_tokens)
        )

        svc: ImportService = _make_service(db=db, gmail=gmail)
        cred: MagicMock = _make_cred()
        svc._get_credential_for_source = AsyncMock(return_value=cred)  # type: ignore[method-assign]
        svc._persist_tokens = AsyncMock()  # type: ignore[method-assign]
        svc._scan_and_ingest_gmail = AsyncMock(return_value=({}, {}, set()))  # type: ignore[method-assign]
        svc._upsert_person_pair_observations = AsyncMock()  # type: ignore[method-assign]
        svc._rebuild_user_org_observations = AsyncMock()  # type: ignore[method-assign]
        svc._commit_progress = AsyncMock()  # type: ignore[method-assign]

        mock_enricher_cls.return_value.enrich_after_import = AsyncMock()
        mock_excerpt_cls.return_value.seed_excerpts_for_user = AsyncMock()

        await svc.run_sync(source.id)

        svc._persist_tokens.assert_awaited_once_with(cred, refreshed_tokens)


# ---------------------------------------------------------------------------
# run_import (deprecated wrapper)
# ---------------------------------------------------------------------------

class TestRunImport:
    async def test_delegates_to_run_sync(self) -> None:
        source_id: uuid.UUID = uuid.uuid4()
        source: MagicMock = MagicMock()
        source.id = source_id

        scalars_mock: MagicMock = MagicMock()
        scalars_mock.all.return_value = [source]
        result_mock: MagicMock = MagicMock()
        result_mock.scalars.return_value = scalars_mock

        db: MagicMock = _make_db()
        db.execute = AsyncMock(return_value=result_mock)

        svc: ImportService = _make_service(db=db)
        svc.run_sync = AsyncMock()  # type: ignore[method-assign]

        await svc.run_import(uuid.uuid4())

        svc.run_sync.assert_awaited_once_with(source_id)

    async def test_no_sources_does_nothing(self) -> None:
        scalars_mock: MagicMock = MagicMock()
        scalars_mock.all.return_value = []
        result_mock: MagicMock = MagicMock()
        result_mock.scalars.return_value = scalars_mock

        db: MagicMock = _make_db()
        db.execute = AsyncMock(return_value=result_mock)

        svc: ImportService = _make_service(db=db)
        svc.run_sync = AsyncMock()  # type: ignore[method-assign]

        await svc.run_import(uuid.uuid4())

        svc.run_sync.assert_not_awaited()


# ---------------------------------------------------------------------------
# _load_user_identity
# ---------------------------------------------------------------------------

class TestLoadUserIdentity:
    async def test_collects_user_email_and_source_account(self) -> None:
        scalars_mock: MagicMock = MagicMock()
        scalars_mock.all.return_value = []

        result_mock: MagicMock = MagicMock()
        result_mock.scalars.return_value = scalars_mock

        db: MagicMock = _make_db()
        db.execute = AsyncMock(return_value=result_mock)

        source: MagicMock = MagicMock()
        source.user_id = uuid.uuid4()
        source.external_account_id = "alt@example.com"

        svc: ImportService = _make_service(db=db)
        emails, local_parts = await svc._load_user_identity(
            user_email="main@example.com",
            source=source,
        )

        assert "main@example.com" in emails
        assert "alt@example.com" in emails
        assert "main" in local_parts
        assert "alt" in local_parts

    async def test_includes_db_identities(self) -> None:
        scalars_mock: MagicMock = MagicMock()
        scalars_mock.all.return_value = ["extra@example.com"]

        result_mock: MagicMock = MagicMock()
        result_mock.scalars.return_value = scalars_mock

        db: MagicMock = _make_db()
        db.execute = AsyncMock(return_value=result_mock)

        source: MagicMock = MagicMock()
        source.user_id = uuid.uuid4()
        source.external_account_id = None

        svc: ImportService = _make_service(db=db)
        emails, local_parts = await svc._load_user_identity(
            user_email="main@example.com",
            source=source,
        )

        assert "extra@example.com" in emails
        assert "extra" in local_parts

    async def test_no_external_account_id(self) -> None:
        scalars_mock: MagicMock = MagicMock()
        scalars_mock.all.return_value = []

        result_mock: MagicMock = MagicMock()
        result_mock.scalars.return_value = scalars_mock

        db: MagicMock = _make_db()
        db.execute = AsyncMock(return_value=result_mock)

        source: MagicMock = MagicMock()
        source.user_id = uuid.uuid4()
        source.external_account_id = None

        svc: ImportService = _make_service(db=db)
        emails, _ = await svc._load_user_identity(
            user_email="main@example.com",
            source=source,
        )

        assert emails == {"main@example.com"}


# ---------------------------------------------------------------------------
# _get_credential_for_source
# ---------------------------------------------------------------------------

class TestGetCredentialForSource:
    async def test_returns_source_scoped_cred(self) -> None:
        cred: MagicMock = _make_cred()
        result_mock: MagicMock = MagicMock()
        result_mock.scalar_one_or_none.return_value = cred

        db: MagicMock = _make_db()
        db.execute = AsyncMock(return_value=result_mock)

        svc: ImportService = _make_service(db=db)
        found = await svc._get_credential_for_source(_make_source())

        assert found is cred
        db.execute.assert_awaited_once()

    async def test_falls_back_to_account_match(self) -> None:
        cred: MagicMock = _make_cred()
        no_result: MagicMock = MagicMock()
        no_result.scalar_one_or_none.return_value = None

        found_result: MagicMock = MagicMock()
        found_result.scalar_one_or_none.return_value = cred

        db: MagicMock = _make_db()
        db.execute = AsyncMock(side_effect=[no_result, found_result])

        svc: ImportService = _make_service(db=db)
        found = await svc._get_credential_for_source(_make_source())

        assert found is cred
        assert db.execute.await_count == 2

    async def test_falls_back_to_user_provider(self) -> None:
        cred: MagicMock = _make_cred()
        no_result: MagicMock = MagicMock()
        no_result.scalar_one_or_none.return_value = None

        found_result: MagicMock = MagicMock()
        found_result.scalar_one_or_none.return_value = cred

        db: MagicMock = _make_db()
        db.execute = AsyncMock(side_effect=[no_result, no_result, found_result])

        svc: ImportService = _make_service(db=db)
        found = await svc._get_credential_for_source(_make_source())

        assert found is cred
        assert db.execute.await_count == 3

    async def test_returns_none_when_nothing_found(self) -> None:
        no_result: MagicMock = MagicMock()
        no_result.scalar_one_or_none.return_value = None

        db: MagicMock = _make_db()
        db.execute = AsyncMock(return_value=no_result)

        svc: ImportService = _make_service(db=db)
        found = await svc._get_credential_for_source(_make_source())

        assert found is None


# ---------------------------------------------------------------------------
# _persist_tokens
# ---------------------------------------------------------------------------

class TestPersistTokens:
    async def test_updates_credential_fields(self) -> None:
        db: MagicMock = _make_db()
        encryptor: MagicMock = MagicMock()
        encryptor.encrypt = MagicMock(return_value=b"new_encrypted")

        svc: ImportService = _make_service(db=db, encryptor=encryptor)

        cred: MagicMock = _make_cred()
        tokens: MagicMock = MagicMock()
        tokens.access_token = "new_token"
        tokens.expires_at = datetime(2099, 6, 1, tzinfo=UTC)
        tokens.scopes = ["scope1", "scope2"]

        await svc._persist_tokens(cred, tokens)

        assert cred.access_token_encrypted == b"new_encrypted"
        assert cred.token_expires_at == tokens.expires_at
        assert cred.scopes == ["scope1", "scope2"]
        db.flush.assert_awaited_once()


# ---------------------------------------------------------------------------
# _accumulate_message – covers pitch tagging & header accumulation
# ---------------------------------------------------------------------------

class TestAccumulateMessage:
    def test_accumulates_from_to_cc(self) -> None:
        svc: ImportService = _make_service()
        contacts: dict[str, ContactAccumulator] = {}
        pair_stats: dict[tuple[str, str], tuple[int, datetime | None]] = {}
        meta: GmailMessageMeta = GmailMessageMeta(
            id="m1",
            internal_date_ms="1700000000000",
            from_header="Alice <alice@example.com>",
            to_header="Owner <owner@example.com>",
            cc_header="Bob <bob@example.com>",
            snippet=None,
        )
        ref: GmailMessageRef = GmailMessageRef(id="m1", internal_date_ms="1700000000000")

        svc._accumulate_message(
            contacts=contacts,
            pair_stats=pair_stats,
            meta=meta,
            ref=ref,
            user_email="owner@example.com",
        )

        assert "alice@example.com" in contacts
        assert "bob@example.com" in contacts
        assert "owner@example.com" not in contacts

    @patch("contactsafe_server.services.import_service.is_pitch_outreach_snippet", return_value=True)
    @patch("contactsafe_server.services.import_service.message_from_user", return_value=True)
    def test_tags_pitch_recipients(self, _msg_from: MagicMock, _pitch: MagicMock) -> None:
        svc: ImportService = _make_service()
        contacts: dict[str, ContactAccumulator] = {}
        pair_stats: dict[tuple[str, str], tuple[int, datetime | None]] = {}
        meta: GmailMessageMeta = GmailMessageMeta(
            id="m1",
            internal_date_ms="1700000000000",
            from_header="Owner <owner@example.com>",
            to_header="Target <target@example.com>",
            cc_header=None,
            snippet="Check out our product",
        )
        ref: GmailMessageRef = GmailMessageRef(id="m1", internal_date_ms="1700000000000")

        svc._accumulate_message(
            contacts=contacts,
            pair_stats=pair_stats,
            meta=meta,
            ref=ref,
            user_email="owner@example.com",
        )

        assert contacts["target@example.com"].pitch_outbound_count >= 1


# ---------------------------------------------------------------------------
# _accumulate_header edge cases
# ---------------------------------------------------------------------------

class TestAccumulateHeader:
    def test_skips_none_header(self) -> None:
        svc: ImportService = _make_service()
        contacts: dict[str, ContactAccumulator] = {}
        svc._accumulate_header(
            contacts,
            header=None,
            user_emails={"me@example.com"},
            user_local_parts={"me"},
            seen_at=None,
            from_user=False,
        )
        assert len(contacts) == 0

    def test_skips_self_contact(self) -> None:
        svc: ImportService = _make_service()
        contacts: dict[str, ContactAccumulator] = {}
        svc._accumulate_header(
            contacts,
            header="Me <me@example.com>",
            user_emails={"me@example.com"},
            user_local_parts={"me"},
            seen_at=None,
            from_user=False,
        )
        assert len(contacts) == 0

    def test_updates_existing_contact(self) -> None:
        svc: ImportService = _make_service()
        contacts: dict[str, ContactAccumulator] = {}
        ts1: datetime = datetime(2025, 1, 1, tzinfo=UTC)
        ts2: datetime = datetime(2025, 6, 1, tzinfo=UTC)

        svc._accumulate_header(
            contacts,
            header="Alice <alice@example.com>",
            user_emails={"me@example.com"},
            user_local_parts={"me"},
            seen_at=ts1,
            from_user=False,
        )
        svc._accumulate_header(
            contacts,
            header="Alice <alice@example.com>",
            user_emails={"me@example.com"},
            user_local_parts={"me"},
            seen_at=ts2,
            from_user=True,
        )

        assert contacts["alice@example.com"].message_count == 2
        assert contacts["alice@example.com"].inbound_count == 1
        assert contacts["alice@example.com"].outbound_count == 1


# ---------------------------------------------------------------------------
# _tag_pitch_recipients edge cases
# ---------------------------------------------------------------------------

class TestTagPitchRecipients:
    def test_skips_none_header(self) -> None:
        svc: ImportService = _make_service()
        contacts: dict[str, ContactAccumulator] = {}
        svc._tag_pitch_recipients(
            contacts,
            header=None,
            user_emails={"me@example.com"},
            user_local_parts={"me"},
            seen_at=None,
        )
        assert len(contacts) == 0

    def test_creates_new_accumulator_for_pitch(self) -> None:
        svc: ImportService = _make_service()
        contacts: dict[str, ContactAccumulator] = {}
        svc._tag_pitch_recipients(
            contacts,
            header="Target <target@example.com>",
            user_emails={"me@example.com"},
            user_local_parts={"me"},
            seen_at=datetime(2025, 1, 1, tzinfo=UTC),
        )

        assert "target@example.com" in contacts
        assert contacts["target@example.com"].pitch_outbound_count == 1

    def test_increments_existing_pitch_count(self) -> None:
        svc: ImportService = _make_service()
        contacts: dict[str, ContactAccumulator] = {
            "target@example.com": ContactAccumulator(
                email="target@example.com",
                display_name="Target",
                last_seen_at=None,
            ),
        }
        svc._tag_pitch_recipients(
            contacts,
            header="Target <target@example.com>",
            user_emails={"me@example.com"},
            user_local_parts={"me"},
            seen_at=None,
        )

        assert contacts["target@example.com"].pitch_outbound_count == 1


# ---------------------------------------------------------------------------
# _collect_participants
# ---------------------------------------------------------------------------

class TestCollectParticipants:
    def test_excludes_self_and_collects_others(self) -> None:
        svc: ImportService = _make_service()
        result: list[str] = svc._collect_participants(
            user_emails={"me@example.com"},
            user_local_parts={"me"},
            headers=(
                "Me <me@example.com>",
                "Alice <alice@example.com>, Bob <bob@example.com>",
                None,
            ),
        )
        assert "me@example.com" not in result
        assert "alice@example.com" in result
        assert "bob@example.com" in result

    def test_deduplicates(self) -> None:
        svc: ImportService = _make_service()
        result: list[str] = svc._collect_participants(
            user_emails={"me@example.com"},
            user_local_parts={"me"},
            headers=(
                "Alice <alice@example.com>",
                "Alice <alice@example.com>",
                None,
            ),
        )
        assert result == ["alice@example.com"]


# ---------------------------------------------------------------------------
# _accumulate_pair_stats
# ---------------------------------------------------------------------------

class TestAccumulatePairStats:
    def test_new_pair_creates_entry(self) -> None:
        svc: ImportService = _make_service()
        pair_stats: dict[tuple[str, str], tuple[int, datetime | None]] = {}
        ts: datetime = datetime(2025, 6, 1, tzinfo=UTC)

        svc._accumulate_pair_stats(
            pair_stats=pair_stats,
            participants=["alice@example.com", "bob@example.com"],
            seen_at=ts,
        )

        key: tuple[str, str] = ("alice@example.com", "bob@example.com")
        assert pair_stats[key] == (1, ts)

    def test_increments_existing_pair(self) -> None:
        svc: ImportService = _make_service()
        ts1: datetime = datetime(2025, 1, 1, tzinfo=UTC)
        ts2: datetime = datetime(2025, 6, 1, tzinfo=UTC)
        key: tuple[str, str] = ("alice@example.com", "bob@example.com")
        pair_stats: dict[tuple[str, str], tuple[int, datetime | None]] = {
            key: (1, ts1),
        }

        svc._accumulate_pair_stats(
            pair_stats=pair_stats,
            participants=["alice@example.com", "bob@example.com"],
            seen_at=ts2,
        )

        assert pair_stats[key] == (2, ts2)

    def test_keeps_later_seen_at(self) -> None:
        svc: ImportService = _make_service()
        ts_later: datetime = datetime(2025, 12, 1, tzinfo=UTC)
        key: tuple[str, str] = ("a@example.com", "b@example.com")
        pair_stats: dict[tuple[str, str], tuple[int, datetime | None]] = {
            key: (1, ts_later),
        }

        svc._accumulate_pair_stats(
            pair_stats=pair_stats,
            participants=["a@example.com", "b@example.com"],
            seen_at=datetime(2025, 1, 1, tzinfo=UTC),
        )

        assert pair_stats[key][1] == ts_later


# ---------------------------------------------------------------------------
# _upsert_person (mocked resolver + db)
# ---------------------------------------------------------------------------

class TestUpsertPerson:
    @patch("contactsafe_server.services.import_service.record_employment", new_callable=AsyncMock)
    @patch("contactsafe_server.services.import_service.is_automation_or_generic_domain", return_value=False)
    @patch("contactsafe_server.services.import_service.classify_contact")
    async def test_creates_observation_and_records_employment(
        self,
        mock_classify: MagicMock,
        _auto_domain: MagicMock,
        mock_employment: AsyncMock,
    ) -> None:
        classification: MagicMock = MagicMock()
        classification.is_human = True
        classification.is_broadcast = False
        classification.is_automated = False
        mock_classify.return_value = classification

        person: MagicMock = MagicMock()
        person.id = uuid.uuid4()
        person.canonical_name = None
        person.updated_at = None

        resolver: MagicMock = MagicMock()
        resolver.resolve_person = AsyncMock(return_value=person)
        resolver.resolve_org = AsyncMock(return_value=MagicMock(id=uuid.uuid4()))

        db: MagicMock = _make_db()
        svc: ImportService = _make_service(db=db)

        acc: ContactAccumulator = ContactAccumulator(
            email="friend@company.com",
            display_name="Friend",
            last_seen_at=datetime(2025, 6, 1, tzinfo=UTC),
        )
        acc.message_count = 5
        acc.outbound_count = 2
        acc.inbound_count = 3

        source_id: uuid.UUID = uuid.uuid4()
        user_id: uuid.UUID = uuid.uuid4()

        await svc._upsert_person(
            user_id, "me@example.com", acc, source_id=source_id, resolver=resolver
        )

        db.execute.assert_awaited_once()
        mock_employment.assert_awaited_once()
        assert person.canonical_name == "Friend"

    @patch("contactsafe_server.services.import_service.classify_contact")
    async def test_skips_employment_for_automated(
        self,
        mock_classify: MagicMock,
    ) -> None:
        classification: MagicMock = MagicMock()
        classification.is_human = False
        classification.is_broadcast = True
        classification.is_automated = True
        mock_classify.return_value = classification

        person: MagicMock = MagicMock()
        person.id = uuid.uuid4()
        person.canonical_name = "Already Set"
        person.updated_at = datetime(2099, 1, 1, tzinfo=UTC)

        resolver: MagicMock = MagicMock()
        resolver.resolve_person = AsyncMock(return_value=person)

        db: MagicMock = _make_db()
        svc: ImportService = _make_service(db=db)

        acc: ContactAccumulator = ContactAccumulator(
            email="noreply@company.com",
            display_name="No Reply",
            last_seen_at=datetime(2025, 1, 1, tzinfo=UTC),
        )

        await svc._upsert_person(
            uuid.uuid4(), "me@example.com", acc, source_id=uuid.uuid4(), resolver=resolver
        )

        db.execute.assert_awaited_once()
        assert person.canonical_name == "Already Set"

    @patch("contactsafe_server.services.import_service.record_employment", new_callable=AsyncMock)
    @patch("contactsafe_server.services.import_service.is_automation_or_generic_domain", return_value=True)
    @patch("contactsafe_server.services.import_service.classify_contact")
    async def test_skips_employment_for_generic_domain(
        self,
        mock_classify: MagicMock,
        _auto_domain: MagicMock,
        mock_employment: AsyncMock,
    ) -> None:
        classification: MagicMock = MagicMock()
        classification.is_human = True
        classification.is_broadcast = False
        classification.is_automated = False
        mock_classify.return_value = classification

        person: MagicMock = MagicMock()
        person.id = uuid.uuid4()
        person.canonical_name = "Existing"
        person.updated_at = datetime(2099, 1, 1, tzinfo=UTC)

        resolver: MagicMock = MagicMock()
        resolver.resolve_person = AsyncMock(return_value=person)

        db: MagicMock = _make_db()
        svc: ImportService = _make_service(db=db)

        acc: ContactAccumulator = ContactAccumulator(
            email="person@gmail.com",
            display_name="Person",
            last_seen_at=datetime(2025, 1, 1, tzinfo=UTC),
        )

        await svc._upsert_person(
            uuid.uuid4(), "me@example.com", acc, source_id=uuid.uuid4(), resolver=resolver
        )

        mock_employment.assert_not_awaited()

    @patch("contactsafe_server.services.import_service.record_employment", new_callable=AsyncMock)
    @patch("contactsafe_server.services.import_service.is_automation_or_generic_domain", return_value=False)
    @patch("contactsafe_server.services.import_service.classify_contact")
    async def test_updates_canonical_name_when_newer(
        self,
        mock_classify: MagicMock,
        _auto_domain: MagicMock,
        _mock_employment: AsyncMock,
    ) -> None:
        classification: MagicMock = MagicMock()
        classification.is_human = True
        classification.is_broadcast = False
        classification.is_automated = False
        mock_classify.return_value = classification

        person: MagicMock = MagicMock()
        person.id = uuid.uuid4()
        person.canonical_name = "Old Name"
        person.updated_at = datetime(2024, 1, 1, tzinfo=UTC)

        resolver: MagicMock = MagicMock()
        resolver.resolve_person = AsyncMock(return_value=person)
        resolver.resolve_org = AsyncMock(return_value=MagicMock(id=uuid.uuid4()))

        svc: ImportService = _make_service()

        acc: ContactAccumulator = ContactAccumulator(
            email="friend@corp.com",
            display_name="New Name",
            last_seen_at=datetime(2025, 6, 1, tzinfo=UTC),
        )

        await svc._upsert_person(
            uuid.uuid4(), "me@example.com", acc, source_id=uuid.uuid4(), resolver=resolver
        )

        assert person.canonical_name == "New Name"

    @patch("contactsafe_server.services.import_service.record_employment", new_callable=AsyncMock)
    @patch("contactsafe_server.services.import_service.is_automation_or_generic_domain", return_value=False)
    @patch("contactsafe_server.services.import_service.classify_contact")
    async def test_keeps_canonical_name_when_email_placeholder(
        self,
        mock_classify: MagicMock,
        _auto_domain: MagicMock,
        _mock_employment: AsyncMock,
    ) -> None:
        """canonical_name == email triggers an update even if person.updated_at is newer."""
        classification: MagicMock = MagicMock()
        classification.is_human = True
        classification.is_broadcast = False
        classification.is_automated = False
        mock_classify.return_value = classification

        person: MagicMock = MagicMock()
        person.id = uuid.uuid4()
        person.canonical_name = "friend@corp.com"
        person.updated_at = datetime(2099, 1, 1, tzinfo=UTC)

        resolver: MagicMock = MagicMock()
        resolver.resolve_person = AsyncMock(return_value=person)
        resolver.resolve_org = AsyncMock(return_value=MagicMock(id=uuid.uuid4()))

        svc: ImportService = _make_service()

        acc: ContactAccumulator = ContactAccumulator(
            email="friend@corp.com",
            display_name="Real Name",
            last_seen_at=datetime(2025, 1, 1, tzinfo=UTC),
        )

        await svc._upsert_person(
            uuid.uuid4(), "me@example.com", acc, source_id=uuid.uuid4(), resolver=resolver
        )

        assert person.canonical_name == "Real Name"


# ---------------------------------------------------------------------------
# _upsert_person_pair_observations
# ---------------------------------------------------------------------------

class TestUpsertPersonPairObservations:
    async def test_empty_pairs_returns_immediately(self) -> None:
        db: MagicMock = _make_db()
        svc: ImportService = _make_service(db=db)

        await svc._upsert_person_pair_observations(
            user_id=uuid.uuid4(),
            source_id=uuid.uuid4(),
            person_pair_counts={},
            resolver=MagicMock(),
        )

        db.execute.assert_not_awaited()

    @patch("contactsafe_server.services.import_service.record_relationship", new_callable=AsyncMock)
    async def test_skips_when_email_not_resolved(self, mock_rel: AsyncMock) -> None:
        all_mock: MagicMock = MagicMock()
        all_mock.all.return_value = []
        result_mock: MagicMock = MagicMock()
        result_mock.all = all_mock.all

        db: MagicMock = _make_db()
        db.execute = AsyncMock(return_value=result_mock)

        svc: ImportService = _make_service(db=db)

        ts: datetime = datetime(2025, 6, 1, tzinfo=UTC)
        await svc._upsert_person_pair_observations(
            user_id=uuid.uuid4(),
            source_id=uuid.uuid4(),
            person_pair_counts={("a@ex.com", "b@ex.com"): (3, ts)},
            resolver=MagicMock(),
        )

        mock_rel.assert_not_awaited()

    @patch("contactsafe_server.services.import_service.record_relationship", new_callable=AsyncMock)
    async def test_skips_same_person_pair(self, mock_rel: AsyncMock) -> None:
        person_id: uuid.UUID = uuid.uuid4()
        all_mock: MagicMock = MagicMock()
        all_mock.all.return_value = [
            ("a@ex.com", person_id),
            ("b@ex.com", person_id),
        ]
        result_mock: MagicMock = MagicMock()
        result_mock.all = all_mock.all

        db: MagicMock = _make_db()
        db.execute = AsyncMock(return_value=result_mock)

        svc: ImportService = _make_service(db=db)

        await svc._upsert_person_pair_observations(
            user_id=uuid.uuid4(),
            source_id=uuid.uuid4(),
            person_pair_counts={("a@ex.com", "b@ex.com"): (1, None)},
            resolver=MagicMock(),
        )

        mock_rel.assert_not_awaited()

    @patch("contactsafe_server.services.import_service.record_relationship", new_callable=AsyncMock)
    async def test_inserts_valid_pair(self, mock_rel: AsyncMock) -> None:
        id_a: uuid.UUID = uuid.uuid4()
        id_b: uuid.UUID = uuid.uuid4()
        all_mock: MagicMock = MagicMock()
        all_mock.all.return_value = [
            ("a@ex.com", id_a),
            ("b@ex.com", id_b),
        ]
        result_mock: MagicMock = MagicMock()
        result_mock.all = all_mock.all

        db: MagicMock = _make_db()
        db.execute = AsyncMock(return_value=result_mock)

        svc: ImportService = _make_service(db=db)
        ts: datetime = datetime(2025, 6, 1, tzinfo=UTC)

        await svc._upsert_person_pair_observations(
            user_id=uuid.uuid4(),
            source_id=uuid.uuid4(),
            person_pair_counts={("a@ex.com", "b@ex.com"): (5, ts)},
            resolver=MagicMock(),
        )

        assert db.execute.await_count == 2  # initial select + upsert
        mock_rel.assert_awaited_once()
        db.flush.assert_awaited_once()


# ---------------------------------------------------------------------------
# _commit_progress
# ---------------------------------------------------------------------------

class TestCommitProgress:
    async def test_commits_and_refreshes(self) -> None:
        db: MagicMock = _make_db()
        svc: ImportService = _make_service(db=db)
        source: MagicMock = _make_source()

        await svc._commit_progress(source)

        db.commit.assert_awaited_once()
        db.refresh.assert_awaited_once_with(source)
