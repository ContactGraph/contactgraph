"""Tests for import_scheduler.py — contacts-sync chaining after Gmail sync."""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from contactsafe_core.enums import SourceType, SyncState
from contactsafe_server.services.import_scheduler import (
    _find_pending_contacts_source,
    _run_sync_task,
)

pytestmark = pytest.mark.anyio


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_source(
    *,
    source_type: str = SourceType.GOOGLE_MAIL.value,
    user_id: uuid.UUID | None = None,
) -> MagicMock:
    source: MagicMock = MagicMock()
    source.id = uuid.uuid4()
    source.user_id = user_id or uuid.uuid4()
    source.source_type = source_type
    return source


def _make_db(source: MagicMock | None) -> MagicMock:
    db: MagicMock = MagicMock()
    db.get = AsyncMock(return_value=source)
    db.commit = AsyncMock()
    db.execute = AsyncMock()
    return db


def _make_ctx() -> MagicMock:
    ctx: MagicMock = MagicMock()
    ctx.settings = MagicMock()
    ctx.encryptor = MagicMock()
    return ctx


def _make_session_context(db: MagicMock) -> MagicMock:
    session_ctx: MagicMock = MagicMock()
    session_ctx.__aenter__ = AsyncMock(return_value=db)
    session_ctx.__aexit__ = AsyncMock(return_value=False)
    return session_ctx


# ---------------------------------------------------------------------------
# _find_pending_contacts_source
# ---------------------------------------------------------------------------


async def test_find_pending_contacts_source_returns_id() -> None:
    user_id: uuid.UUID = uuid.uuid4()
    contacts_id: uuid.UUID = uuid.uuid4()
    db: MagicMock = MagicMock()
    result_mock: MagicMock = MagicMock()
    result_mock.scalar_one_or_none.return_value = contacts_id
    db.execute = AsyncMock(return_value=result_mock)

    found: uuid.UUID | None = await _find_pending_contacts_source(db, user_id)
    assert found == contacts_id
    db.execute.assert_awaited_once()


async def test_find_pending_contacts_source_returns_none() -> None:
    user_id: uuid.UUID = uuid.uuid4()
    db: MagicMock = MagicMock()
    result_mock: MagicMock = MagicMock()
    result_mock.scalar_one_or_none.return_value = None
    db.execute = AsyncMock(return_value=result_mock)

    found: uuid.UUID | None = await _find_pending_contacts_source(db, user_id)
    assert found is None


# ---------------------------------------------------------------------------
# _run_sync_task — contacts chaining after Gmail sync
# ---------------------------------------------------------------------------


async def test_run_sync_chains_contacts_after_gmail() -> None:
    """After a Gmail sync, a pending contacts source should be auto-scheduled."""
    user_id: uuid.UUID = uuid.uuid4()
    mail_source: MagicMock = _make_source(
        source_type=SourceType.GOOGLE_MAIL.value,
        user_id=user_id,
    )
    contacts_source_id: uuid.UUID = uuid.uuid4()

    db: MagicMock = _make_db(mail_source)
    find_result: MagicMock = MagicMock()
    find_result.scalar_one_or_none.return_value = contacts_source_id
    db.execute = AsyncMock(return_value=find_result)

    ctx: MagicMock = _make_ctx()
    factory: MagicMock = MagicMock(return_value=_make_session_context(db))

    with (
        patch("contactsafe_server.deps.build_app_context", return_value=ctx),
        patch("contactsafe_server.services.import_scheduler.get_session_factory", return_value=factory),
        patch("contactsafe_server.services.import_scheduler.ImportService") as mock_import_cls,
        patch("contactsafe_server.services.import_scheduler.GmailClient"),
        patch("contactsafe_server.services.import_scheduler.GoogleOAuthClient"),
        patch("contactsafe_server.services.import_scheduler.schedule_source_sync") as mock_schedule,
        patch("contactsafe_server.services.import_scheduler.release_sync_lock") as mock_release,
    ):
        mock_import_cls.return_value.run_sync = AsyncMock()
        await _run_sync_task(mail_source.id, user_id)

        mock_release.assert_called_once_with(mail_source.id, user_id)
        mock_schedule.assert_called_once_with(contacts_source_id, user_id)


async def test_run_sync_no_chain_when_no_pending_contacts() -> None:
    """No contacts source is scheduled when none is pending."""
    user_id: uuid.UUID = uuid.uuid4()
    mail_source: MagicMock = _make_source(
        source_type=SourceType.GOOGLE_MAIL.value,
        user_id=user_id,
    )

    db: MagicMock = _make_db(mail_source)
    find_result: MagicMock = MagicMock()
    find_result.scalar_one_or_none.return_value = None
    db.execute = AsyncMock(return_value=find_result)

    ctx: MagicMock = _make_ctx()
    factory: MagicMock = MagicMock(return_value=_make_session_context(db))

    with (
        patch("contactsafe_server.deps.build_app_context", return_value=ctx),
        patch("contactsafe_server.services.import_scheduler.get_session_factory", return_value=factory),
        patch("contactsafe_server.services.import_scheduler.ImportService") as mock_import_cls,
        patch("contactsafe_server.services.import_scheduler.GmailClient"),
        patch("contactsafe_server.services.import_scheduler.GoogleOAuthClient"),
        patch("contactsafe_server.services.import_scheduler.schedule_source_sync") as mock_schedule,
        patch("contactsafe_server.services.import_scheduler.release_sync_lock"),
    ):
        mock_import_cls.return_value.run_sync = AsyncMock()
        await _run_sync_task(mail_source.id, user_id)

        mock_schedule.assert_not_called()


async def test_run_sync_no_chain_for_contacts_source() -> None:
    """A contacts sync completing should NOT chain another contacts sync."""
    user_id: uuid.UUID = uuid.uuid4()
    contacts_source: MagicMock = _make_source(
        source_type=SourceType.GOOGLE_CONTACTS.value,
        user_id=user_id,
    )

    db: MagicMock = _make_db(contacts_source)
    ctx: MagicMock = _make_ctx()
    factory: MagicMock = MagicMock(return_value=_make_session_context(db))

    with (
        patch("contactsafe_server.deps.build_app_context", return_value=ctx),
        patch("contactsafe_server.services.import_scheduler.get_session_factory", return_value=factory),
        patch("contactsafe_server.services.google_contacts_import_service.GoogleContactsImportService") as mock_contacts_cls,
        patch("contactsafe_server.services.people_api_client.PeopleApiClient"),
        patch("contactsafe_server.services.import_scheduler.GoogleOAuthClient"),
        patch("contactsafe_server.services.import_scheduler.schedule_source_sync") as mock_schedule,
        patch("contactsafe_server.services.import_scheduler.release_sync_lock"),
    ):
        mock_contacts_cls.return_value.run_sync = AsyncMock()
        await _run_sync_task(contacts_source.id, user_id)

        mock_schedule.assert_not_called()
