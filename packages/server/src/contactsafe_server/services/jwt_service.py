import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from authlib.jose import jwt
from authlib.jose.errors import JoseError

from contactsafe_server.config import Settings

logger: logging.Logger = logging.getLogger(__name__)

MCP_SCOPES: tuple[str, ...] = (
    "contactsafe:read",
    "contactsafe:write",
    "contactsafe:admin",
)
DEFAULT_MCP_SCOPES: tuple[str, ...] = ("contactsafe:read", "contactsafe:write")


class JWTService:
    def __init__(self, settings: Settings) -> None:
        self._settings: Settings = settings

    def create_access_token(self, user_id: uuid.UUID, scopes: list[str]) -> str:
        now: datetime = datetime.now(tz=UTC)
        expire: datetime = now + timedelta(
            minutes=self._settings.jwt_access_token_expire_minutes
        )
        payload: dict[str, Any] = {
            "sub": str(user_id),
            "iss": self._settings.effective_jwt_issuer,
            "aud": self._settings.effective_jwt_audience,
            "exp": int(expire.timestamp()),
            "iat": int(now.timestamp()),
            "scope": " ".join(scopes),
        }
        header: dict[str, str] = {"alg": self._settings.jwt_algorithm}
        token: bytes = jwt.encode(
            header,
            payload,
            self._settings.effective_jwt_signing_key,
        )
        return token.decode() if isinstance(token, bytes) else str(token)

    def create_refresh_token(self, user_id: uuid.UUID, scopes: list[str]) -> str:
        now: datetime = datetime.now(tz=UTC)
        expire: datetime = now + timedelta(days=self._settings.jwt_refresh_token_expire_days)
        payload: dict[str, Any] = {
            "sub": str(user_id),
            "iss": self._settings.effective_jwt_issuer,
            "aud": self._settings.effective_jwt_audience,
            "exp": int(expire.timestamp()),
            "iat": int(now.timestamp()),
            "scope": " ".join(scopes),
            "typ": "refresh",
        }
        header: dict[str, str] = {"alg": self._settings.jwt_algorithm}
        token: bytes = jwt.encode(
            header,
            payload,
            self._settings.effective_jwt_signing_key,
        )
        return token.decode() if isinstance(token, bytes) else str(token)

    def decode_token(self, token: str) -> dict[str, Any]:
        expected_iss: str = self._settings.effective_jwt_issuer
        expected_aud: str = self._settings.effective_jwt_audience
        try:
            claims = jwt.decode(
                token,
                self._settings.effective_jwt_signing_key,
                claims_options={
                    "iss": {"essential": True, "value": expected_iss},
                    "aud": {"essential": True, "value": expected_aud},
                    "exp": {"essential": True},
                    "sub": {"essential": True},
                    "typ": {"values": [None]},
                },
            )
            claims.validate()
        except JoseError as exc:
            logger.warning("JWT validation failed: %s", exc)
            raise ValueError("Invalid or expired token") from exc
        return dict(claims)

    def decode_refresh_token(self, token: str) -> dict[str, Any]:
        expected_iss: str = self._settings.effective_jwt_issuer
        expected_aud: str = self._settings.effective_jwt_audience
        try:
            claims = jwt.decode(
                token,
                self._settings.effective_jwt_signing_key,
                claims_options={
                    "iss": {"essential": True, "value": expected_iss},
                    "aud": {"essential": True, "value": expected_aud},
                    "exp": {"essential": True},
                    "sub": {"essential": True},
                    "typ": {"essential": True, "value": "refresh"},
                },
            )
            claims.validate()
        except JoseError as exc:
            logger.warning("Refresh JWT validation failed: %s", exc)
            raise ValueError("Invalid or expired token") from exc
        return dict(claims)

    def create_unsubscribe_token(self, user_id: uuid.UUID) -> str:
        now: datetime = datetime.now(tz=UTC)
        expire: datetime = now + timedelta(
            days=self._settings.email_unsubscribe_token_expire_days,
        )
        payload: dict[str, Any] = {
            "sub": str(user_id),
            "iss": self._settings.effective_jwt_issuer,
            "exp": int(expire.timestamp()),
            "iat": int(now.timestamp()),
            "typ": "unsubscribe",
        }
        header: dict[str, str] = {"alg": self._settings.jwt_algorithm}
        token: bytes = jwt.encode(
            header,
            payload,
            self._settings.effective_jwt_signing_key,
        )
        return token.decode() if isinstance(token, bytes) else str(token)

    def decode_unsubscribe_token(self, token: str) -> uuid.UUID:
        expected_iss: str = self._settings.effective_jwt_issuer
        try:
            claims = jwt.decode(
                token,
                self._settings.effective_jwt_signing_key,
                claims_options={
                    "iss": {"essential": True, "value": expected_iss},
                    "exp": {"essential": True},
                    "sub": {"essential": True},
                    "typ": {"essential": True, "value": "unsubscribe"},
                },
            )
            claims.validate()
        except JoseError as exc:
            logger.warning("Unsubscribe JWT validation failed: %s", exc)
            raise ValueError("Invalid or expired token") from exc
        sub: str = str(claims.get("sub", ""))
        if not sub:
            raise ValueError("Invalid or expired token")
        return uuid.UUID(sub)

    @staticmethod
    def parse_scopes(scope_claim: str | list[str] | None) -> list[str]:
        if scope_claim is None:
            return list(DEFAULT_MCP_SCOPES)
        if isinstance(scope_claim, list):
            return scope_claim
        return [s for s in scope_claim.split() if s]
