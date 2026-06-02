import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from contactsafe_core.enums import SyncState
from contactsafe_server.config import Settings
from contactsafe_server.services.gmail_client import GmailMessageMeta, GmailMessageRef
from contactsafe_server.services.import_service import ImportService


def _message_meta(message_id: str, *, to_header: str) -> GmailMessageMeta:
    return GmailMessageMeta(
        id=message_id,
        internal_date_ms="1700000000000",
        from_header="Owner <owner@example.com>",
        to_header=to_header,
        cc_header=None,
        snippet=None,
    )


async def test_flush_ingest_progress_marks_partial_and_commits() -> None:
    settings = Settings()
    settings.import_partial_contact_target = 2
    settings.import_progress_commit_messages = 1

    db = MagicMock()
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()

    service = ImportService(
        db=db,
        settings=settings,
        encryptor=MagicMock(),
        gmail=MagicMock(),
    )
    service._upsert_person = AsyncMock()  # type: ignore[method-assign]

    source = MagicMock()
    source.id = uuid.uuid4()
    source.sync_state = SyncState.SYNCING.value
    source.contacts_found = 0
    source.contacts_resolved = 0
    source.contacts_pending = 0

    contacts = {
        "alice@example.com": MagicMock(
            email="alice@example.com",
            last_seen_at=None,
            message_count=1,
        ),
        "bob@example.com": MagicMock(
            email="bob@example.com",
            last_seen_at=None,
            message_count=1,
        ),
    }

    await service._flush_ingest_progress(
        contacts=contacts,
        upserted_emails=set(),
        user_id=uuid.uuid4(),
        user_email="owner@example.com",
        source=source,
        messages_scanned=25,
        resolver=MagicMock(),
    )

    assert source.sync_state == SyncState.PARTIAL.value
    assert source.contacts_found == 2
    assert source.contacts_resolved == 2
    db.commit.assert_awaited_once()
    assert service._upsert_person.await_count == 2


async def test_scan_and_ingest_commits_during_scan() -> None:
    settings = Settings()
    settings.import_max_messages = 2
    settings.import_progress_commit_messages = 1
    settings.import_partial_contact_target = 1

    db = MagicMock()
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()

    gmail = MagicMock()
    gmail.list_message_refs = AsyncMock(
        side_effect=[
            (
                [
                    GmailMessageRef(id="m1", internal_date_ms="1700000000000"),
                    GmailMessageRef(id="m2", internal_date_ms="1700000000000"),
                ],
                None,
            )
        ]
    )
    gmail.get_message_metadata = AsyncMock(
        side_effect=[
            _message_meta("m1", to_header="Alice <alice@example.com>"),
            _message_meta("m2", to_header="Bob <bob@example.com>"),
        ]
    )

    service = ImportService(
        db=db,
        settings=settings,
        encryptor=MagicMock(),
        gmail=gmail,
    )
    service._upsert_person = AsyncMock()  # type: ignore[method-assign]
    service._load_user_identity = AsyncMock(  # type: ignore[method-assign]
        return_value=({"owner@example.com"}, {"owner"})
    )

    source = MagicMock()
    source.id = uuid.uuid4()
    source.sync_state = SyncState.SYNCING.value
    source.contacts_found = 0
    source.contacts_resolved = 0
    source.contacts_pending = 0

    contacts, pairs, upserted = await service._scan_and_ingest_gmail(
        access_token="token",
        user_email="owner@example.com",
        user_id=uuid.uuid4(),
        source=source,
        resolver=MagicMock(),
    )

    assert "alice@example.com" in contacts
    assert "bob@example.com" in contacts
    assert len(pairs) == 0
    assert upserted == {"alice@example.com", "bob@example.com"}
    assert db.commit.await_count == 2
