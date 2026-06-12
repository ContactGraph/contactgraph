import asyncio
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
from contactsafe_server.middleware.rate_limit import RateLimitMiddleware
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
        from contactsafe_server.services.job_discovery_scheduler import (
            schedule_initial_job_discovery_delay,
        )
        from contactsafe_server.services.org_enrichment_scheduler import (
            schedule_initial_org_enrichment_delay,
        )

        job_discovery_task = asyncio.create_task(
            schedule_initial_job_discovery_delay(),
            name="job-discovery-startup",
        )
        org_enrichment_task = asyncio.create_task(
            schedule_initial_org_enrichment_delay(),
            name="org-enrichment-startup",
        )
        async with mcp_server.session_manager.run():
            yield
        job_discovery_task.cancel()
        org_enrichment_task.cancel()
        for periodic_task in (job_discovery_task, org_enrichment_task):
            try:
                await periodic_task
            except asyncio.CancelledError:
                pass
        await shutdown_db()
        from contactsafe_server.config import get_settings
        from contactsafe_server.queue import close_arq_pool
        from contactsafe_server.redis_state import close_redis_client

        if get_settings().use_arq_worker:
            await close_arq_pool()
            await close_redis_client()

    app: FastAPI = FastAPI(
        title="ContactGraph",
        description="Agent-native personal graph — MCP server and OAuth API",
        version="0.1.0",
        lifespan=app_lifespan,
    )

    dev_origins: list[str] = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
    ]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=dev_origins if settings.app_env == "development" else [],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(RateLimitMiddleware)
    app.add_middleware(
        NormalizeMcpPathMiddleware,
        mcp_path=settings.mcp_path,
        browser_redirect_target=settings.base_url,
    )

    app.include_router(oauth_router)
    app.include_router(well_known_router)
    app.include_router(api_router, prefix="/api")
    from contactsafe_server.api.admin_router import router as admin_router

    app.include_router(admin_router, prefix="/api")
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
