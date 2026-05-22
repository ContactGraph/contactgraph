from starlette.types import ASGIApp, Receive, Scope, Send


class NormalizeMcpPathMiddleware:
    """Rewrite ``/mcp`` → ``/mcp/`` so MCP clients that omit the trailing slash connect."""

    def __init__(self, app: ASGIApp, *, mcp_path: str) -> None:
        self._app: ASGIApp = app
        self._bare_path: str = mcp_path.rstrip("/") or "/mcp"
        self._slash_path: str = f"{self._bare_path}/"

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and scope["path"] == self._bare_path:
            scope = dict(scope)
            scope["path"] = self._slash_path
            raw_path: bytes | None = scope.get("raw_path")  # type: ignore[assignment]
            if isinstance(raw_path, (bytes, bytearray)):
                scope["raw_path"] = self._slash_path.encode()
        await self._app(scope, receive, send)
