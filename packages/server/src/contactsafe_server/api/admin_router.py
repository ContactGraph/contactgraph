"""Admin-only API routes."""

from __future__ import annotations

from typing import Annotated

from contactsafe_core.contact_schemas import WorkerStatusResult
from fastapi import APIRouter, Depends, HTTPException

from contactsafe_server.api.router import AuthenticatedUser, Ctx, _authenticate
from contactsafe_server.services.worker_status_service import get_worker_status

router: APIRouter = APIRouter()


async def _require_admin(
    auth: AuthenticatedUser = Depends(_authenticate),
) -> AuthenticatedUser:
    if not auth.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    return auth


AdminUser = Annotated[AuthenticatedUser, Depends(_require_admin)]


@router.post("/admin/worker-status", response_model=WorkerStatusResult)
async def api_admin_worker_status(
    ctx: Ctx,
    _admin: AdminUser,
) -> WorkerStatusResult:
    async with ctx.session_factory() as db:
        return await get_worker_status(db, ctx.settings)
