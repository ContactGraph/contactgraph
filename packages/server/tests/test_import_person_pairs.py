import uuid
from unittest.mock import AsyncMock, MagicMock

from contactsafe_server.config import Settings
from contactsafe_server.services.gmail_client import (
    GmailMessageListPage,
    GmailMessageMeta,
    GmailMessageRef,
)
from contactsafe_server.services.import_service import ImportService


async def test_phase2_sent_mail_builds_contacts_and_cooccurrence_edges() -> None:
    settings = Settings()
    settings.import_sent_max_messages = 10
    gmail = MagicMock()
    gmail.list_message_refs = AsyncMock(
        side_effect=[
            GmailMessageListPage(
                refs=[GmailMessageRef(id="m1", internal_date_ms="1700000000000")],
                next_page_token=None,
                result_size_estimate=1,
            )
        ]
    )
    gmail.get_message_metadata = AsyncMock(
        return_value=GmailMessageMeta(
            id="m1",
            internal_date_ms="1700000000000",
            from_header="Owner <owner@example.com>",
            to_header="Alice <alice@example.com>, Bob <bob@example.com>",
            cc_header="Carol <carol@example.com>",
            snippet=None,
        )
    )

    db = MagicMock()
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()

    service = ImportService(
        db=db,
        settings=settings,
        encryptor=MagicMock(),
        gmail=gmail,
    )
    service._upsert_person = AsyncMock()  # type: ignore[method-assign]

    resolver = AsyncMock()
    contacts: dict[str, object] = {}
    pair_stats: dict[tuple[str, str], tuple[int, object]] = {}

    await service._phase2_sent_mail_scan(
        access_token="token",
        user_email="owner@example.com",
        user_id=uuid.uuid4(),
        source=MagicMock(
            id=uuid.uuid4(),
            sync_state="syncing",
            contacts_found=0,
            contacts_resolved=0,
            contacts_pending=0,
        ),
        resolver=resolver,
        user_emails={"owner@example.com"},
        user_local_parts={"owner"},
        contacts=contacts,
        pair_stats=pair_stats,
        upserted_emails=set(),
    )

    assert "alice@example.com" in contacts
    assert "bob@example.com" in contacts
    assert "carol@example.com" in contacts
    assert pair_stats[("alice@example.com", "bob@example.com")][0] == 1
    assert pair_stats[("alice@example.com", "carol@example.com")][0] == 1
    assert pair_stats[("bob@example.com", "carol@example.com")][0] == 1
