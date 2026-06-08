import asyncio
import logging
import threading
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from contactsafe_core.enums import SourceType, SyncState
from contactsafe_server.db.connection import get_session_factory
from contactsafe_server.db.models import Source
from contactsafe_server.oauth.google import GoogleOAuthClient
from contactsafe_server.services.calendar_api_client import CalendarApiClient
from contactsafe_server.services.file_upload_import_service import FileUploadImportService
from contactsafe_server.services.gmail_client import GmailClient
from contactsafe_server.services.google_calendar_import_service import GoogleCalendarImportService
from contactsafe_server.services.import_service import ImportService
from contactsafe_server.services.people_api_client import PeopleApiClient

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
            logger.info(
                "Sync blocked: source %s or user %s already active (sources=%s, users=%s)",
                source_id, user_id, _active_sync_source_ids, _active_sync_user_ids,
            )
            return False
        _active_sync_source_ids.add(source_id)
        _active_sync_user_ids.add(user_id)
    logger.info("Scheduled sync task for source %s, user %s", source_id, user_id)
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


async def _mark_source_sync_failed(
    db: AsyncSession,
    source_id: uuid.UUID,
    error: str,
) -> None:
    source: Source | None = await db.get(Source, source_id)
    if source is None:
        return
    source.sync_state = SyncState.FAILED.value
    source.sync_error = error[:500]
    await db.commit()


async def _run_sync_task(source_id: uuid.UUID, user_id: uuid.UUID) -> None:
    from contactsafe_server.deps import build_app_context

    ctx = build_app_context()
    google_client: GoogleOAuthClient = GoogleOAuthClient(ctx.settings)
    factory = get_session_factory(ctx.settings)
    try:
        async with factory() as db:
            source: Source | None = await db.get(Source, source_id)
            if source is None:
                logger.warning("Source %s not found, skipping sync", source_id)
                return

            source_type: str = source.source_type
            logger.info("Starting sync for source %s (type=%s)", source_id, source_type)
            try:
                if source_type == SourceType.GOOGLE_MAIL.value:
                    gmail = GmailClient(ctx.settings, google_client)
                    people = PeopleApiClient(ctx.settings, google_client)
                    service = ImportService(
                        db=db,
                        settings=ctx.settings,
                        encryptor=ctx.encryptor,
                        gmail=gmail,
                        people_client=people,
                    )
                    await service.run_sync(source_id)
                elif source_type == SourceType.GOOGLE_CALENDAR.value:
                    calendar = CalendarApiClient(google_client)
                    service = GoogleCalendarImportService(
                        db=db,
                        encryptor=ctx.encryptor,
                        calendar_client=calendar,
                    )
                    await service.run_sync(source_id)
                elif source_type in {
                    SourceType.PHONE_CONTACTS_UPLOAD.value,
                    SourceType.LINKEDIN_CONNECTIONS_UPLOAD.value,
                    SourceType.LINKEDIN_PROFILE_UPLOAD.value,
                }:
                    service = FileUploadImportService(
                        db=db,
                        settings=ctx.settings,
                        encryptor=ctx.encryptor,
                    )
                    await service.run_sync(source_id)
                else:
                    logger.warning(
                        "Sync skipped for source %s with type %s",
                        source_id,
                        source_type,
                    )
                    return
                await db.commit()
                logger.info("Source sync completed for source %s", source_id)
            except Exception:
                await db.commit()
                logger.exception("Source sync failed for source %s", source_id)
    except Exception as exc:
        logger.exception("Background sync task failed for source %s", source_id)
        try:
            async with factory() as db:
                await _mark_source_sync_failed(db, source_id, str(exc))
        except Exception:
            logger.exception("Failed to mark source %s as failed", source_id)
    finally:
        release_sync_lock(source_id, user_id)
