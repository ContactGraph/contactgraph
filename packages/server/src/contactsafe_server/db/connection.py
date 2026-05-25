from collections.abc import AsyncIterator
from typing import Any, Final

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from contactsafe_server.config import Settings, get_settings

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def get_engine(settings: Settings | None = None) -> AsyncEngine:
    global _engine
    if _engine is None:
        cfg: Settings = settings or get_settings()
        connect_args: dict[str, Any] = cfg.database_connect_args
        _engine = create_async_engine(
            str(cfg.database_url),
            echo=cfg.database_echo,
            pool_pre_ping=True,
            connect_args=connect_args if connect_args else {},
        )
    return _engine


def get_session_factory(settings: Settings | None = None) -> async_sessionmaker[AsyncSession]:
    global _session_factory
    if _session_factory is None:
        engine: Final[AsyncEngine] = get_engine(settings)
        _session_factory = async_sessionmaker(engine, expire_on_commit=False)
    return _session_factory


async def init_db(settings: Settings | None = None) -> None:
    get_session_factory(settings)


async def shutdown_db() -> None:
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _session_factory = None


async def session_scope() -> AsyncIterator[AsyncSession]:
    factory: async_sessionmaker[AsyncSession] = get_session_factory()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
