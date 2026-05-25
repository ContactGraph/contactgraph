import json
import logging
from typing import Any

from starlette.types import ASGIApp, Send, Scope

from contactsafe_server.config import Settings
from contactsafe_server.services.jwt_service import JWTService

logger: logging.Logger = logging.getLogger(__name__)


class McpAuthMiddleware:
    """Validate Bearer JWT on MCP requests and inject user_id into ASGI scope state."""

    def __init__(
        self,
        app: ASGIApp,
        *,
        settings: Settings,
        jwt_service: JWTService,
    ) -> None:
        self._app: ASGIApp = app
        self._settings: Settings = settings
        self._jwt: JWTService = jwt_service
        self._resource_metadata: str = (
            f'{settings.base_url.rstrip("/")}/.well-known/oauth-protected-resource'
        )

    async def __call__(self, scope: Scope, receive: object, send: Send) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return

        if scope.get("method") == "OPTIONS":
            await self._app(scope, receive, send)
            return

        auth_header: str | None = self._get_authorization_header(scope)
        if auth_header is None:
            logger.warning("MCP auth: no Authorization header present")
            await self._send_unauthorized(send, error_description="Authentication required")
            return

        if not auth_header.lower().startswith("bearer "):
            logger.warning("MCP auth: Authorization header is not Bearer (got %s…)", auth_header[:20])
            await self._send_unauthorized(send, error_description="Authentication required")
            return

        token: str = auth_header[7:].strip()
        if not token:
            logger.warning("MCP auth: empty Bearer token")
            await self._send_unauthorized(send, error_description="Authentication required")
            return

        try:
            claims: dict[str, Any] = self._jwt.decode_token(token)
        except ValueError:
            logger.warning("MCP auth: JWT decode failed for token %s…", token[:12], exc_info=True)
            await self._send_unauthorized(send, error_description="Invalid or expired Bearer token")
            return

        if claims.get("typ") == "refresh":
            logger.warning("MCP auth: rejected refresh token for user %s", claims.get("sub"))
            await self._send_unauthorized(send, error_description="Refresh tokens cannot be used for API access")
            return

        user_id: str = str(claims.get("sub", ""))
        if not user_id:
            logger.warning("MCP auth: token missing sub claim")
            await self._send_unauthorized(send, error_description="Token missing subject")
            return

        state: dict[str, Any] = scope.setdefault("state", {})  # type: ignore[assignment]
        state["user_id"] = user_id
        state["jwt_scopes"] = str(claims.get("scope", ""))
        await self._app(scope, receive, send)

    @staticmethod
    def _get_authorization_header(scope: Scope) -> str | None:
        for key, value in scope.get("headers", []):
            if key.lower() == b"authorization":
                return value.decode("latin-1")
        return None

    async def _send_unauthorized(
        self,
        send: Send,
        *,
        error_description: str = "Invalid or expired Bearer token",
    ) -> None:
        www_auth: str = (
            f'Bearer resource_metadata="{self._resource_metadata}", '
            'error="invalid_token"'
        )
        body: bytes = json.dumps(
            {
                "error": "invalid_token",
                "error_description": error_description,
            }
        ).encode()
        headers: list[tuple[bytes, bytes]] = [
            (b"content-type", b"application/json"),
            (b"content-length", str(len(body)).encode()),
            (b"www-authenticate", www_auth.encode()),
        ]
        await send({"type": "http.response.start", "status": 401, "headers": headers})
        await send({"type": "http.response.body", "body": body})
