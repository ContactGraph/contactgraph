import os
from collections.abc import AsyncIterator, Iterator
from typing import Final

import pytest
from cryptography.fernet import Fernet
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

os.environ.setdefault("APP_ENV", "development")
os.environ.setdefault("BASE_URL", "http://testserver")
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+asyncpg://contactsafe:contactsafe@localhost:5432/contactsafe",
)
os.environ.setdefault("TOKEN_ENCRYPTION_KEY", Fernet.generate_key().decode())
os.environ.setdefault("SESSION_SECRET", "test-session-secret-for-pytest-only")
os.environ.setdefault("GOOGLE_CLIENT_ID", "test-client-id")
os.environ.setdefault("GOOGLE_CLIENT_SECRET", "test-client-secret")
os.environ.setdefault("GOOGLE_REDIRECT_URI", "http://testserver/oauth/callback")

from contactsafe_server.config import get_settings  # noqa: E402
from contactsafe_server.db.models import Base  # noqa: E402
from contactsafe_server.main import create_app  # noqa: E402

get_settings.cache_clear()


@pytest.fixture(scope="session")
def postgres_available() -> bool:
    import asyncio

    async def _ping() -> bool:
        settings = get_settings()
        engine = create_async_engine(str(settings.database_url), pool_pre_ping=True)
        try:
            async with engine.connect() as conn:
                await conn.execute(__import__("sqlalchemy").text("SELECT 1"))
            return True
        except Exception:
            return False
        finally:
            await engine.dispose()

    return asyncio.run(_ping())


@pytest.fixture(scope="session")
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
async def db_session() -> AsyncIterator[AsyncSession]:
    settings = get_settings()
    try:
        engine = create_async_engine(str(settings.database_url), pool_pre_ping=True)
        async with engine.connect() as conn:
            await conn.execute(__import__("sqlalchemy").text("SELECT 1"))
    except Exception as exc:
        pytest.skip(f"Postgres not available: {exc}")
    engine = create_async_engine(str(settings.database_url), pool_pre_ping=True)
    factory: async_sessionmaker[AsyncSession] = async_sessionmaker(
        engine, expire_on_commit=False
    )
    async with engine.begin() as conn:
        await conn.execute(
            __import__("sqlalchemy").text("CREATE EXTENSION IF NOT EXISTS vector")
        )
        await conn.execute(
            __import__("sqlalchemy").text("CREATE EXTENSION IF NOT EXISTS pg_trgm")
        )
        await conn.run_sync(Base.metadata.create_all)
    async with factory() as session:
        yield session
        await session.commit()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    app = create_app()
    transport: Final[ASGITransport] = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac


@pytest.fixture(autouse=True)
def clear_settings_cache() -> Iterator[None]:
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
