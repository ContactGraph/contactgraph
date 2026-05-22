import asyncio
import logging
import uuid

from contactsafe_server.db.connection import get_session_factory
from contactsafe_server.deps import build_app_context
from contactsafe_server.oauth.google import GoogleOAuthClient
from contactsafe_server.services.gmail_client import GmailClient
from contactsafe_server.services.import_service import ImportService

logger = logging.getLogger(__name__)


def schedule_gmail_import(user_id: uuid.UUID) -> None:
    """Fire-and-forget background import after OAuth (uses its own DB session)."""
    asyncio.create_task(
        _run_import_task(user_id),
        name=f"gmail-import-{user_id}",
    )


async def _run_import_task(user_id: uuid.UUID) -> None:
    ctx = build_app_context()
    gmail = GmailClient(ctx.settings, GoogleOAuthClient(ctx.settings))
    factory = get_session_factory(ctx.settings)
    async with factory() as db:
        service = ImportService(
            db=db,
            settings=ctx.settings,
            encryptor=ctx.encryptor,
            gmail=gmail,
        )
        try:
            await service.run_import(user_id)
            await db.commit()
            logger.info("Gmail import completed for user %s", user_id)
        except Exception:
            await db.rollback()
            logger.exception("Gmail import failed for user %s", user_id)
