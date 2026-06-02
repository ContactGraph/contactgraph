import os
import socket
from collections.abc import AsyncIterator, Iterator
from typing import Final
from urllib.parse import urlparse

import pytest
from cryptography.fernet import Fernet
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

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
from contactsafe_server.db.connection import shutdown_db  # noqa: E402
from contactsafe_server.main import create_app  # noqa: E402

get_settings.cache_clear()


@pytest.fixture(scope="session")
def postgres_available() -> bool:
    settings = get_settings()
    raw_url: str = str(settings.database_url).replace("+asyncpg", "")
    parsed = urlparse(raw_url)
    host: str = parsed.hostname or "localhost"
    port: int = parsed.port or 5432
    try:
        with socket.create_connection((host, port), timeout=2):
            return True
    except OSError:
        return False


@pytest.fixture(scope="session")
async def db_engine(postgres_available: bool) -> AsyncIterator[AsyncEngine]:
    if not postgres_available:
        pytest.skip("Postgres not available")

    settings = get_settings()
    engine = create_async_engine(
        str(settings.database_url),
        poolclass=NullPool,
    )
    try:
        async with engine.connect() as conn:
            await conn.execute(__import__("sqlalchemy").text("SELECT 1"))
    except Exception as exc:
        await engine.dispose()
        pytest.skip(f"Postgres not available: {exc}")

    yield engine
    await engine.dispose()


@pytest.fixture
async def db_session(db_engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    connection = await db_engine.connect()
    transaction = await connection.begin()
    session = AsyncSession(
        bind=connection,
        join_transaction_mode="create_savepoint",
        expire_on_commit=False,
    )
    try:
        yield session
    finally:
        await session.close()
        await transaction.rollback()
        await connection.close()


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


@pytest.fixture(autouse=True)
async def reset_global_db_engine() -> AsyncIterator[None]:
    await shutdown_db()
    yield
    await shutdown_db()
