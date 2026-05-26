import asyncio
import logging
import threading
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from contactsafe_core.enums import SourceType, SyncState
from contactsafe_server.db.connection import get_session_factory
from contactsafe_server.db.models import Source
from contactsafe_server.oauth.google import GoogleOAuthClient
from contactsafe_server.services.gmail_client import GmailClient
from contactsafe_server.services.import_service import ImportService

logger = logging.getLogger(__name__)

_active_sync_source_ids: set[uuid.UUID] = set()
_active_sync_user_ids: set[uuid.UUID] = set()
_scheduling_lock: threading.Lock = threading.Lock()


def schedule_source_sync(source_id: uuid.UUID, user_id: uuid.UUID) -> bool:
    """Fire-and-forget background sync. Returns False if one is already running."""
    with _scheduling_lock:
        if (
            source_id in _active_sync_source_ids
            or user_id in _active_sync_user_ids
        ):
            return False
        _active_sync_source_ids.add(source_id)
        _active_sync_user_ids.add(user_id)
    asyncio.create_task(
        _run_sync_task(source_id, user_id),
        name=f"source-sync-{source_id}",
    )
    return True


def release_sync_lock(source_id: uuid.UUID, user_id: uuid.UUID) -> None:
    with _scheduling_lock:
        _active_sync_source_ids.discard(source_id)
        _active_sync_user_ids.discard(user_id)


def is_source_sync_running(source_id: uuid.UUID) -> bool:
    with _scheduling_lock:
        return source_id in _active_sync_source_ids


def is_user_sync_running(user_id: uuid.UUID) -> bool:
    with _scheduling_lock:
        return user_id in _active_sync_user_ids


async def _run_sync_task(source_id: uuid.UUID, user_id: uuid.UUID) -> None:
    from contactsafe_server.deps import build_app_context

    ctx = build_app_context()
    google_client: GoogleOAuthClient = GoogleOAuthClient(ctx.settings)
    factory = get_session_factory(ctx.settings)
    chain_contacts_source_id: uuid.UUID | None = None
    try:
        async with factory() as db:
            source: Source | None = await db.get(Source, source_id)
            if source is None:
                logger.warning("Source %s not found, skipping sync", source_id)
                return

            if source.source_type == SourceType.GOOGLE_CONTACTS.value:
                from contactsafe_server.services.people_api_client import PeopleApiClient
                from contactsafe_server.services.google_contacts_import_service import (
                    GoogleContactsImportService,
                )

                people = PeopleApiClient(ctx.settings, google_client)
                service_contacts = GoogleContactsImportService(
                    db=db,
                    settings=ctx.settings,
                    encryptor=ctx.encryptor,
                    people_client=people,
                )
                try:
                    await service_contacts.run_sync(source_id)
                    await db.commit()
                    logger.info("Google Contacts sync completed for source %s", source_id)
                except Exception:
                    await db.commit()
                    logger.exception("Google Contacts sync failed for source %s", source_id)
            elif source.source_type == SourceType.GOOGLE_CALENDAR.value:
                from contactsafe_server.services.calendar_api_client import CalendarApiClient
                from contactsafe_server.services.google_calendar_import_service import GoogleCalendarImportService

                calendar = CalendarApiClient(google_client)
                service_calendar = GoogleCalendarImportService(
                    db=db,
                    encryptor=ctx.encryptor,
                    calendar_client=calendar,
                )
                try:
                    await service_calendar.run_sync(source_id)
                    await db.commit()
                    logger.info("Google Calendar sync completed for source %s", source_id)
                except Exception:
                    await db.commit()
                    logger.exception("Google Calendar sync failed for source %s", source_id)
            else:
                gmail = GmailClient(ctx.settings, google_client)
                service = ImportService(
                    db=db,
                    settings=ctx.settings,
                    encryptor=ctx.encryptor,
                    gmail=gmail,
                )
                try:
                    await service.run_sync(source_id)
                    await db.commit()
                    logger.info("Source sync completed for source %s", source_id)
                except Exception:
                    await db.commit()
                    logger.exception("Source sync failed for source %s", source_id)

                chain_contacts_source_id = await _find_pending_contacts_source(
                    db, user_id,
                )
    finally:
        release_sync_lock(source_id, user_id)

    if chain_contacts_source_id is not None:
        logger.info(
            "Auto-scheduling Google Contacts sync %s after Gmail sync for user %s",
            chain_contacts_source_id,
            user_id,
        )
        schedule_source_sync(chain_contacts_source_id, user_id)


async def _find_pending_contacts_source(
    db: AsyncSession,
    user_id: uuid.UUID,
) -> uuid.UUID | None:
    """Return the ID of a pending Google Contacts source for this user, if any."""
    result = await db.execute(
        select(Source.id).where(
            Source.user_id == user_id,
            Source.source_type == SourceType.GOOGLE_CONTACTS.value,
            Source.sync_state == SyncState.PENDING.value,
        ).limit(1)
    )
    return result.scalar_one_or_none()
