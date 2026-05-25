import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from contactsafe_server.config import Settings
from contactsafe_server.services.gmail_client import GmailMessageMeta, GmailMessageRef
from contactsafe_server.services.import_service import ImportService


@pytest.mark.anyio
async def test_scan_gmail_builds_contacts_and_cooccurrence_edges() -> None:
    settings = Settings()
    settings.import_max_messages = 10
    gmail = MagicMock()
    gmail.list_message_refs = AsyncMock(
        side_effect=[([GmailMessageRef(id="m1", internal_date_ms="1700000000000")], None)]
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

    service = ImportService(
        db=MagicMock(),
        settings=settings,
        encryptor=MagicMock(),
        gmail=gmail,
        calendar=MagicMock(),
    )

    contacts, pairs = await service._scan_gmail(
        access_token="token",
        user_email="owner@example.com",
    )

    assert "alice@example.com" in contacts
    assert "bob@example.com" in contacts
    assert "carol@example.com" in contacts
    assert pairs[("alice@example.com", "bob@example.com")][0] == 1
    assert pairs[("alice@example.com", "carol@example.com")][0] == 1
    assert pairs[("bob@example.com", "carol@example.com")][0] == 1
