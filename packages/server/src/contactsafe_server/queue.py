"""Shared arq Redis pool for enqueuing background jobs from the API process."""

from __future__ import annotations

import logging
from typing import Any

from arq import create_pool
from arq.connections import ArqRedis, RedisSettings

from contactsafe_server.config import Settings, get_settings

logger: logging.Logger = logging.getLogger(__name__)

_pool: ArqRedis | None = None


def redis_settings_from_config(settings: Settings | None = None) -> RedisSettings:
    cfg: Settings = settings or get_settings()
    return RedisSettings.from_dsn(cfg.redis_url)


async def get_arq_pool(settings: Settings | None = None) -> ArqRedis:
    global _pool
    if _pool is None:
        _pool = await create_pool(redis_settings_from_config(settings))
    return _pool


async def close_arq_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


async def enqueue_background_job(
    job_name: str,
    *args: object,
    settings: Settings | None = None,
    **kwargs: Any,
) -> str | None:
    """Enqueue a job when arq is enabled; return job id or None if skipped."""
    cfg: Settings = settings or get_settings()
    if not cfg.use_arq_worker:
        return None
    try:
        pool: ArqRedis = await get_arq_pool(cfg)
        job = await pool.enqueue_job(job_name, *args, **kwargs)
        return job.job_id if job is not None else None
    except Exception:
        logger.exception("Failed to enqueue arq job %s", job_name)
        return None
