from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from mcp.server.fastmcp import FastMCP
from starlette.applications import Starlette

from contactsafe_server.config import Settings, get_settings
from contactsafe_server.db.connection import init_db, shutdown_db
from contactsafe_server.deps import build_app_context, build_jwt_service
from contactsafe_server.mcp.auth_middleware import McpAuthMiddleware
from contactsafe_server.mcp.path_middleware import NormalizeMcpPathMiddleware
from contactsafe_server.mcp.server import create_mcp_server
from contactsafe_server.oauth.router import router as oauth_router
from contactsafe_server.oauth.well_known import router as well_known_router


def create_app() -> FastAPI:
    settings: Settings = get_settings()
    mcp_server: FastMCP = create_mcp_server(settings)
    # FastMCP defaults to /mcp; mounting at /mcp would make the real path /mcp/mcp.
    mcp_server.settings.streamable_http_path = "/"
    mcp_http_app: Starlette = mcp_server.streamable_http_app()
    mcp_http_app = McpAuthMiddleware(
        mcp_http_app,
        settings=settings,
        jwt_service=build_jwt_service(settings),
    )

    @asynccontextmanager
    async def app_lifespan(_app: FastAPI) -> AsyncGenerator[None, None]:
        build_app_context()
        await init_db(settings)
        # Mounted Starlette apps do not run their own lifespan under FastAPI; start MCP here.
        async with mcp_server.session_manager.run():
            yield
        await shutdown_db()

    app: FastAPI = FastAPI(
        title="ContactSafe",
        description="Agent-native personal graph — MCP server and OAuth API",
        version="0.1.0",
        lifespan=app_lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"] if settings.app_env == "development" else [],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(NormalizeMcpPathMiddleware, mcp_path=settings.mcp_path)

    app.include_router(oauth_router)
    app.include_router(well_known_router)
    app.mount(settings.mcp_path, mcp_http_app)

    @app.get("/health")  # pyright: ignore[reportUnusedFunction]
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/", include_in_schema=False)  # pyright: ignore[reportUnusedFunction]
    async def landing_page() -> HTMLResponse:
        return HTMLResponse(
            """<!doctype html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
  <title>ContactSafe</title>
  <style>
    :root { color-scheme: dark; }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      min-height: 100vh;
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, sans-serif;
      background: radial-gradient(circle at 20% 15%, #1a2966 0%, #04050d 35%, #020308 100%);
      color: #e8ecff;
      display: grid;
      place-items: center;
      padding: 2rem;
    }
    .wrap { max-width: 920px; width: 100%; }
    .panel {
      border: 1px solid rgba(143, 168, 255, 0.35);
      border-radius: 22px;
      background: linear-gradient(180deg, rgba(11, 17, 40, 0.86), rgba(6, 10, 24, 0.9));
      box-shadow: 0 26px 110px rgba(53, 88, 255, 0.24);
      padding: clamp(1.6rem, 3vw, 3rem);
      backdrop-filter: blur(8px);
    }
    .kicker { color: #8db7ff; font-size: .82rem; letter-spacing: .13em; text-transform: uppercase; }
    h1 { margin: .8rem 0; font-size: clamp(2rem, 6vw, 4rem); line-height: 1.05; }
    p { margin: 0; color: #bad0ff; font-size: clamp(1rem, 1.9vw, 1.3rem); max-width: 45ch; }
  </style>
</head>
<body>
  <main class=\"wrap\">
    <section class=\"panel\">
      <div class=\"kicker\">ContactSafe • Private Preview</div>
      <h1>Your relationship graph, finally agent-native.</h1>
      <p>
        ContactSafe turns scattered inboxes, calendars, and chats into a trusted memory layer for AI.
        Query your network in plain language, surface high-signal context instantly, and ship better decisions.
      </p>
    </section>
  </main>
</body>
</html>"""
        )

    @app.get("/skill.md", include_in_schema=False)  # pyright: ignore[reportUnusedFunction]
    async def serve_skill_md() -> FileResponse:
        repo_root: Path = Path(__file__).resolve().parents[4]
        skill_path: Path = repo_root / "skill.md"
        return FileResponse(skill_path, media_type="text/markdown")

    return app


app: FastAPI = create_app()


def run() -> None:
    import uvicorn

    cfg: Settings = get_settings()
    uvicorn.run(
        "contactsafe_server.main:app",
        host="0.0.0.0",
        port=8000,
        reload=cfg.app_env == "development",
    )


if __name__ == "__main__":
    run()
