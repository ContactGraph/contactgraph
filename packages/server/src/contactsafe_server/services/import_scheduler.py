import asyncio
import logging
import threading
import uuid

from contactsafe_server.db.connection import get_session_factory
from contactsafe_server.oauth.google import GoogleOAuthClient
from contactsafe_server.services.gmail_client import GmailClient
from contactsafe_server.services.import_service import ImportService

logger = logging.getLogger(__name__)

_active_sync_source_ids: set[uuid.UUID] = set()
_scheduling_lock: threading.Lock = threading.Lock()


def schedule_source_sync(source_id: uuid.UUID) -> bool:
    """Fire-and-forget background sync. Returns False if one is already running."""
    with _scheduling_lock:
        if source_id in _active_sync_source_ids:
            return False
        _active_sync_source_ids.add(source_id)
    asyncio.create_task(
        _run_sync_task(source_id),
        name=f"source-sync-{source_id}",
    )
    return True


def is_source_sync_running(source_id: uuid.UUID) -> bool:
    with _scheduling_lock:
        return source_id in _active_sync_source_ids


async def _run_sync_task(source_id: uuid.UUID) -> None:
    from contactsafe_server.deps import build_app_context

    ctx = build_app_context()
    gmail = GmailClient(ctx.settings, GoogleOAuthClient(ctx.settings))
    factory = get_session_factory(ctx.settings)
    try:
        async with factory() as db:
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
                await db.rollback()
                logger.exception("Source sync failed for source %s", source_id)
    finally:
        with _scheduling_lock:
            _active_sync_source_ids.discard(source_id)
