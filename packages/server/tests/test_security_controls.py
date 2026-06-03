"""Tests for contact-data security controls."""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from contactsafe_core.enums import SourceType, SyncState
from contactsafe_server.db.models import ConnectSession, Source, User
from contactsafe_server.services.connect_session_poll import (
    assign_poll_secret,
    verify_poll_secret,
)
from contactsafe_server.services.contacts_service import ContactsService
from contactsafe_server.services.source_service import SourceService
from contactsafe_server.services.upload_payload_crypto import (
    build_upload_payload,
    read_upload_payload,
)
from contactsafe_server.services.crypto import TokenEncryptor


@pytest.mark.asyncio
async def test_require_source_owned_by_rejects_other_user(
    db_session: AsyncSession,
) -> None:
    owner: User = User(email="owner@example.com")
    other: User = User(email="other@example.com")
    db_session.add_all([owner, other])
    await db_session.flush()

    source: Source = Source(
        user_id=owner.id,
        source_type=SourceType.GOOGLE_MAIL.value,
        label="owner@gmail.com",
        external_account_id="owner@gmail.com",
        sync_state=SyncState.PENDING.value,
    )
    db_session.add(source)
    await db_session.flush()

    service: SourceService = SourceService(db_session)
    with pytest.raises(ValueError, match="Unknown source_id"):
        await service.require_source_owned_by(source.id, other.id)

    loaded: Source = await service.require_source_owned_by(source.id, owner.id)
    assert loaded.id == source.id


@pytest.mark.asyncio
async def test_get_org_returns_none_without_user_contacts(
    db_session: AsyncSession,
) -> None:
    from contactsafe_server.db.models import Org

    user: User = User(email="viewer@example.com")
    db_session.add(user)
    await db_session.flush()

    org: Org = Org(canonical_name="Acme Corp")
    db_session.add(org)
    await db_session.flush()

    service: ContactsService = ContactsService(db_session)
    detail = await service.get_org(user.id, org.id)
    assert detail is None


def test_poll_secret_verification() -> None:
    session: ConnectSession = ConnectSession(
        state="test-state",
        status="pending",
        requested_scopes=["contactsafe:read"],
    )
    secret: str = assign_poll_secret(session)
    assert session.poll_secret_hash is not None
    assert verify_poll_secret(session, secret)
    assert not verify_poll_secret(session, "wrong-secret")


def test_upload_payload_encrypt_roundtrip() -> None:
    from cryptography.fernet import Fernet

    key: str = Fernet.generate_key().decode()
    encryptor: TokenEncryptor = TokenEncryptor(key)
    payload = build_upload_payload(
        filename="contacts.vcf",
        content="BEGIN:VCARD\nEND:VCARD",
        encryptor=encryptor,
    )
    assert "content_encrypted" in payload
    assert "content" not in payload

    filename, content = read_upload_payload(payload, encryptor)
    assert filename == "contacts.vcf"
    assert "VCARD" in content
