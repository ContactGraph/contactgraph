"""Unauthenticated public endpoints for SEO landing pages."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from starlette.responses import Response

from contactsafe_core.contact_schemas import (
    PublicCompaniesByCategoryResult,
    PublicCompanyDetailResult,
)
from contactsafe_server.deps import AppContext, build_app_context
from contactsafe_server.services.public_company_category_service import (
    PublicCompanyCategoryService,
)

router: APIRouter = APIRouter(tags=["public"])

_CACHE_MAX_AGE_SECONDS: int = 3600


def _get_app_context(request: Request) -> AppContext:
    ctx: AppContext | None = getattr(request.app.state, "app_context", None)
    if ctx is None:
        ctx = build_app_context()
    return ctx


@router.get("/companies-by-category")
async def companies_by_category(
    request: Request,
    category: Annotated[str, Query(min_length=1, max_length=128)],
) -> Response:
    ctx: AppContext = _get_app_context(request)
    async with ctx.session_factory() as db:
        service = PublicCompanyCategoryService(db)
        result: PublicCompaniesByCategoryResult | None = (
            await service.list_companies_by_category(category)
        )

    if result is None:
        raise HTTPException(status_code=404, detail="Unknown category")

    payload: PublicCompaniesByCategoryResult = result
    return JSONResponse(
        content=payload.model_dump(mode="json"),
        headers={"Cache-Control": f"public, max-age={_CACHE_MAX_AGE_SECONDS}"},
    )


@router.get("/companies/{slug}")
async def company_detail(
    request: Request,
    slug: str,
) -> Response:
    ctx: AppContext = _get_app_context(request)
    async with ctx.session_factory() as db:
        service = PublicCompanyCategoryService(db)
        result: PublicCompanyDetailResult | None = await service.get_company_by_slug(slug)

    if result is None:
        raise HTTPException(status_code=404, detail="Company not found")

    payload: PublicCompanyDetailResult = result
    return JSONResponse(
        content=payload.model_dump(mode="json"),
        headers={"Cache-Control": f"public, max-age={_CACHE_MAX_AGE_SECONDS}"},
    )
