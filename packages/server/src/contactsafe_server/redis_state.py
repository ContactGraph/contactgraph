"""Cross-process state stored in Redis (scoring progress, cancellation flags)."""

from __future__ import annotations

import json
import uuid
from typing import Any

import redis.asyncio as aioredis

from contactsafe_server.config import Settings, get_settings

_redis_client: aioredis.Redis | None = None


async def get_redis_client(settings: Settings | None = None) -> aioredis.Redis:
    global _redis_client
    cfg: Settings = settings or get_settings()
    if _redis_client is None:
        _redis_client = aioredis.from_url(cfg.redis_url, decode_responses=True)
    return _redis_client


async def close_redis_client() -> None:
    global _redis_client
    if _redis_client is not None:
        await _redis_client.aclose()
        _redis_client = None


def _scoring_progress_key(user_id: uuid.UUID) -> str:
    return f"scoring_progress:{user_id}"


def _scoring_cancelled_key(user_id: uuid.UUID) -> str:
    return f"scoring_cancelled:{user_id}"


async def set_scoring_progress(
    user_id: uuid.UUID,
    scored: int,
    total: int,
    *,
    settings: Settings | None = None,
) -> None:
    client: aioredis.Redis = await get_redis_client(settings)
    payload: dict[str, int] = {"scored": scored, "total": total}
    await client.setex(_scoring_progress_key(user_id), 3600, json.dumps(payload))


async def clear_scoring_progress(
    user_id: uuid.UUID,
    *,
    settings: Settings | None = None,
) -> None:
    client: aioredis.Redis = await get_redis_client(settings)
    await client.delete(_scoring_progress_key(user_id))


async def get_scoring_progress_redis(
    user_id: uuid.UUID,
    *,
    settings: Settings | None = None,
) -> tuple[int, int] | None:
    client: aioredis.Redis = await get_redis_client(settings)
    raw: str | None = await client.get(_scoring_progress_key(user_id))
    if raw is None:
        return None
    data: dict[str, Any] = json.loads(raw)
    scored: int = int(data.get("scored", 0))
    total: int = int(data.get("total", 0))
    return scored, total


async def set_scoring_cancelled(
    user_id: uuid.UUID,
    *,
    settings: Settings | None = None,
) -> None:
    client: aioredis.Redis = await get_redis_client(settings)
    await client.setex(_scoring_cancelled_key(user_id), 3600, "1")


async def clear_scoring_cancelled(
    user_id: uuid.UUID,
    *,
    settings: Settings | None = None,
) -> None:
    client: aioredis.Redis = await get_redis_client(settings)
    await client.delete(_scoring_cancelled_key(user_id))


async def is_scoring_cancelled_redis(
    user_id: uuid.UUID,
    *,
    settings: Settings | None = None,
) -> bool:
    client: aioredis.Redis = await get_redis_client(settings)
    value: str | None = await client.get(_scoring_cancelled_key(user_id))
    return value is not None


async def set_worker_flag(
    name: str,
    active: bool,
    *,
    settings: Settings | None = None,
) -> None:
    client: aioredis.Redis = await get_redis_client(settings)
    key: str = f"worker:flag:{name}"
    if active:
        await client.setex(key, 3600, "1")
    else:
        await client.delete(key)


async def is_worker_flag_active(
    name: str,
    *,
    settings: Settings | None = None,
) -> bool:
    client: aioredis.Redis = await get_redis_client(settings)
    value: str | None = await client.get(f"worker:flag:{name}")
    return value is not None


async def record_worker_run(
    pipeline: str,
    *,
    duration_ms: int | None = None,
    settings: Settings | None = None,
) -> None:
    from datetime import UTC, datetime

    client: aioredis.Redis = await get_redis_client(settings)
    payload: dict[str, object] = {
        "at": datetime.now(tz=UTC).isoformat(),
        "duration_ms": duration_ms,
    }
    await client.setex(
        f"worker:last_run:{pipeline}",
        86400 * 7,
        json.dumps(payload),
    )


async def get_worker_last_run(
    pipeline: str,
    *,
    settings: Settings | None = None,
) -> tuple[str | None, int | None]:
    client: aioredis.Redis = await get_redis_client(settings)
    raw: str | None = await client.get(f"worker:last_run:{pipeline}")
    if raw is None:
        return None, None
    data: dict[str, object] = json.loads(raw)
    at: str | None = data.get("at") if isinstance(data.get("at"), str) else None
    duration_raw: object = data.get("duration_ms")
    duration_ms: int | None = int(duration_raw) if isinstance(duration_raw, int) else None
    return at, duration_ms
