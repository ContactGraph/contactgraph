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
      color: #ebeeff;
      background:
        radial-gradient(1200px 600px at 12% -8%, rgba(102, 132, 255, 0.34), transparent 58%),
        radial-gradient(900px 500px at 88% 8%, rgba(115, 61, 255, 0.28), transparent 62%),
        radial-gradient(500px 300px at 50% 100%, rgba(29, 131, 255, 0.20), transparent 65%),
        linear-gradient(165deg, #02030a 0%, #040814 45%, #03040b 100%);
      display: grid;
      place-items: center;
      padding: clamp(1rem, 2vw, 2.5rem);
      overflow-x: hidden;
    }
    .veil::before {
      content: \"\";
      position: fixed;
      inset: 0;
      pointer-events: none;
      background: repeating-linear-gradient(
        180deg,
        rgba(180, 205, 255, 0.045) 0,
        rgba(180, 205, 255, 0.045) 1px,
        transparent 2px,
        transparent 4px
      );
      opacity: .35;
      mix-blend-mode: screen;
    }
    .wrap {
      position: relative;
      max-width: 980px;
      width: 100%;
    }
    .orb {
      position: absolute;
      filter: blur(24px);
      opacity: .85;
      pointer-events: none;
      z-index: 0;
    }
    .orb.one {
      width: 220px;
      height: 220px;
      border-radius: 999px;
      background: rgba(85, 126, 255, 0.55);
      top: -30px;
      left: -48px;
    }
    .orb.two {
      width: 260px;
      height: 260px;
      border-radius: 999px;
      background: rgba(145, 91, 255, 0.42);
      right: -70px;
      bottom: -40px;
    }
    .panel {
      position: relative;
      z-index: 1;
      border: 1px solid rgba(148, 173, 255, 0.30);
      border-radius: 24px;
      padding: clamp(1.4rem, 3vw, 3rem);
      background:
        linear-gradient(180deg, rgba(11, 16, 37, 0.86), rgba(6, 10, 24, 0.90)),
        radial-gradient(circle at top, rgba(124, 155, 255, 0.12), transparent 60%);
      box-shadow:
        0 28px 120px rgba(53, 88, 255, 0.25),
        inset 0 1px 0 rgba(255, 255, 255, 0.08);
      backdrop-filter: blur(10px);
    }
    .kicker {
      display: inline-block;
      color: #8db7ff;
      font-size: .76rem;
      letter-spacing: .18em;
      text-transform: uppercase;
      padding: .38rem .66rem;
      border: 1px solid rgba(141, 183, 255, 0.34);
      border-radius: 999px;
      background: rgba(38, 62, 125, 0.24);
    }
    h1 {
      margin: 1rem 0 .9rem;
      font-size: clamp(2.2rem, 6.3vw, 4.6rem);
      line-height: 1.03;
      letter-spacing: -0.03em;
      max-width: 12ch;
      text-wrap: balance;
    }
    .lead {
      margin: 0;
      color: #bdd2ff;
      font-size: clamp(1rem, 2vw, 1.22rem);
      line-height: 1.58;
      max-width: 52ch;
    }
    .signal {
      margin-top: 1.3rem;
      font-size: .86rem;
      letter-spacing: .15em;
      text-transform: uppercase;
      color: #89aefe;
      opacity: .88;
    }
  </style>
</head>
<body class=\"veil\">
  <main class=\"wrap\">
    <div class=\"orb one\" aria-hidden=\"true\"></div>
    <div class=\"orb two\" aria-hidden=\"true\"></div>
    <section class=\"panel\">
      <div class=\"kicker\">ContactSafe • Signal Layer</div>
      <h1>Intelligence hides in who knows who.</h1>
      <p class=\"lead\">
        ContactSafe distills your inboxes, calendars, and messages into a living relationship graph for AI.
        Ask one question, and the right context appears before the meeting, before the pitch, before the moment is gone.
      </p>
      <div class=\"signal\">Private preview opening soon</div>
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
