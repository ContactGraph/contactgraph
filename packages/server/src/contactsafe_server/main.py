from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from mcp.server.fastmcp import FastMCP
from starlette.applications import Starlette

from contactsafe_server.api.router import router as api_router
from contactsafe_server.config import Settings, get_settings
from contactsafe_server.db.connection import init_db, shutdown_db
from contactsafe_server.deps import AppContext, build_app_context, build_jwt_service
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
        ctx: AppContext = build_app_context()
        _app.state.app_context = ctx
        await init_db(settings)
        # Mounted Starlette apps do not run their own lifespan under FastAPI; start MCP here.
        async with mcp_server.session_manager.run():
            yield
        await shutdown_db()

    app: FastAPI = FastAPI(
        title="ContactGraph",
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
    app.add_middleware(
        NormalizeMcpPathMiddleware,
        mcp_path=settings.mcp_path,
        browser_redirect_target=settings.base_url,
    )

    app.include_router(oauth_router)
    app.include_router(well_known_router)
    app.include_router(api_router, prefix="/api")
    app.mount(settings.mcp_path, mcp_http_app)

    @app.get("/health")  # pyright: ignore[reportUnusedFunction]
    async def health() -> dict[str, str]:
        return {"status": "ok"}

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
