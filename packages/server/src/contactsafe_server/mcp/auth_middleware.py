import json
from typing import Any

from starlette.types import ASGIApp, Send, Scope

from contactsafe_server.config import Settings
from contactsafe_server.services.jwt_service import JWTService


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

        auth_header: str | None = self._get_authorization_header(scope)
        if auth_header is not None and auth_header.lower().startswith("bearer "):
            token: str = auth_header[7:].strip()
            if not token:
                await self._send_unauthorized(send)
                return
            try:
                claims: dict[str, Any] = self._jwt.decode_token(token)
                if claims.get("typ") == "refresh":
                    await self._send_unauthorized(send)
                    return
                user_id: str = str(claims.get("sub", ""))
                if not user_id:
                    await self._send_unauthorized(send)
                    return
                state: dict[str, Any] = scope.setdefault("state", {})  # type: ignore[assignment]
                state["user_id"] = user_id
                state["jwt_scopes"] = str(claims.get("scope", ""))
            except ValueError:
                await self._send_unauthorized(send)
                return

        await self._app(scope, receive, send)

    @staticmethod
    def _get_authorization_header(scope: Scope) -> str | None:
        for key, value in scope.get("headers", []):
            if key.lower() == b"authorization":
                return value.decode("latin-1")
        return None

    async def _send_unauthorized(self, send: Send) -> None:
        www_auth: str = (
            f'Bearer resource_metadata="{self._resource_metadata}", '
            'error="invalid_token"'
        )
        body: bytes = json.dumps(
            {
                "error": "invalid_token",
                "error_description": "Invalid or expired Bearer token",
            }
        ).encode()
        headers: list[tuple[bytes, bytes]] = [
            (b"content-type", b"application/json"),
            (b"content-length", str(len(body)).encode()),
            (b"www-authenticate", www_auth.encode()),
        ]
        await send({"type": "http.response.start", "status": 401, "headers": headers})
        await send({"type": "http.response.body", "body": body})
