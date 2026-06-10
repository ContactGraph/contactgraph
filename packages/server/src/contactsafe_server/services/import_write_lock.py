import logging
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger: logging.Logger = logging.getLogger(__name__)

_USER_IMPORT_LOCK_NAMESPACE: int = 0x635F_0001


def user_import_lock_keys(user_id: uuid.UUID) -> tuple[int, int]:
    """Stable pg_advisory_lock keys for serializing per-user graph import writes."""
    return (_USER_IMPORT_LOCK_NAMESPACE, user_id.int % (2**31))


@asynccontextmanager
async def user_import_write_lock(
    session: AsyncSession,
    user_id: uuid.UUID,
) -> AsyncIterator[None]:
    """Serialize DB-heavy import work for one user across concurrent source syncs."""
    key1, key2 = user_import_lock_keys(user_id)
    logger.info("Waiting for import write lock for user %s", user_id)
    await session.execute(
        text("SELECT pg_advisory_lock(:key1, :key2)"),
        {"key1": key1, "key2": key2},
    )
    logger.info("Acquired import write lock for user %s", user_id)
    try:
        yield
    finally:
        await session.execute(
            text("SELECT pg_advisory_unlock(:key1, :key2)"),
            {"key1": key1, "key2": key2},
        )
        logger.info("Released import write lock for user %s", user_id)
