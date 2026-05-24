from urllib.parse import parse_qsl, urlencode

from starlette.responses import RedirectResponse
from starlette.types import ASGIApp, Receive, Scope, Send


class NormalizeMcpPathMiddleware:
    """Rewrite ``/mcp`` → ``/mcp/`` so MCP clients that omit the trailing slash connect."""

    def __init__(
        self,
        app: ASGIApp,
        *,
        mcp_path: str,
        browser_redirect_target: str,
    ) -> None:
        self._app: ASGIApp = app
        self._bare_path: str = mcp_path.rstrip("/") or "/mcp"
        self._slash_path: str = f"{self._bare_path}/"
        self._browser_redirect_target: str = browser_redirect_target.rstrip("/")

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and scope["path"] == self._bare_path:
            if self._is_browser_request(scope):
                await self._redirect_browser(scope, send)
                return
            scope = dict(scope)
            scope["path"] = self._slash_path
            raw_path: bytes | None = scope.get("raw_path")  # type: ignore[assignment]
            if isinstance(raw_path, (bytes, bytearray)):
                scope["raw_path"] = self._slash_path.encode()

        if scope["type"] == "http" and scope["path"] == self._slash_path and self._is_browser_request(scope):
            await self._redirect_browser(scope, send)
            return

        await self._app(scope, receive, send)

    async def _redirect_browser(self, scope: Scope, send: Send) -> None:
        query_string: str = scope.get("query_string", b"").decode("latin-1")
        target: str = self._browser_redirect_target
        if query_string:
            params: list[tuple[str, str]] = parse_qsl(query_string, keep_blank_values=True)
            if params:
                target = f"{target}?{urlencode(params)}"
        response = RedirectResponse(url=target, status_code=307)
        async def _noop_receive() -> dict[str, object]:
            return {"type": "http.request", "body": b"", "more_body": False}

        await response(scope, receive=_noop_receive, send=send)

    @staticmethod
    def _is_browser_request(scope: Scope) -> bool:
        for key, value in scope.get("headers", []):
            if key.lower() != b"accept":
                continue
            if b"text/html" in value.lower():
                return True
        return False
