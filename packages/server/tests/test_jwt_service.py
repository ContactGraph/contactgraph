"""Unit tests for JWTService."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from authlib.jose import jwt

from contactsafe_server.config import Settings
from contactsafe_server.services.jwt_service import JWTService


@pytest.fixture
def jwt_settings() -> Settings:
    return Settings(
        token_encryption_key="test-encryption-key",
        session_secret="test-session-secret",
        google_client_id="test-client",
        google_client_secret="test-secret",
        jwt_signing_key="jwt-test-signing-key",
        base_url="http://testserver",
    )


@pytest.fixture
def jwt_service(jwt_settings: Settings) -> JWTService:
    return JWTService(jwt_settings)


def test_create_and_decode_access_token(jwt_service: JWTService) -> None:
    user_id: uuid.UUID = uuid.uuid4()
    token: str = jwt_service.create_access_token(user_id, ["contactsafe:read"])
    claims: dict[str, object] = jwt_service.decode_token(token)
    assert claims["sub"] == str(user_id)
    assert claims["aud"] == "http://testserver/mcp"
    assert claims["scope"] == "contactsafe:read"
    assert claims.get("typ") is None


def test_decode_rejects_expired_token(jwt_service: JWTService, jwt_settings: Settings) -> None:
    user_id: uuid.UUID = uuid.uuid4()
    past: datetime = datetime.now(tz=UTC) - timedelta(hours=1)
    payload: dict[str, object] = {
        "sub": str(user_id),
        "iss": jwt_settings.effective_jwt_issuer,
        "aud": jwt_settings.effective_jwt_audience,
        "exp": int(past.timestamp()),
        "iat": int(past.timestamp()) - 60,
        "scope": "contactsafe:read",
    }
    token_bytes: bytes = jwt.encode(
        {"alg": jwt_settings.jwt_algorithm},
        payload,
        jwt_settings.effective_jwt_signing_key,
    )
    with pytest.raises(ValueError, match="Invalid or expired token"):
        jwt_service.decode_token(token_bytes.decode())


def test_decode_rejects_refresh_token(jwt_service: JWTService) -> None:
    user_id: uuid.UUID = uuid.uuid4()
    token: str = jwt_service.create_refresh_token(user_id, ["contactsafe:read"])
    with pytest.raises(ValueError, match="Invalid or expired token"):
        jwt_service.decode_token(token)


def test_decode_rejects_unsubscribe_token(jwt_service: JWTService) -> None:
    user_id: uuid.UUID = uuid.uuid4()
    token: str = jwt_service.create_unsubscribe_token(user_id)
    with pytest.raises(ValueError, match="Invalid or expired token"):
        jwt_service.decode_token(token)


def test_unsubscribe_token_round_trip(jwt_service: JWTService) -> None:
    user_id: uuid.UUID = uuid.uuid4()
    token: str = jwt_service.create_unsubscribe_token(user_id)
    decoded: uuid.UUID = jwt_service.decode_unsubscribe_token(token)
    assert decoded == user_id
