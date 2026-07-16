"""Public, unauthenticated company listings grouped by SEO category."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Final
from uuid import UUID

from sqlalchemy import Select, and_, case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from contactsafe_core.contact_schemas import (
    PublicCategoryCompanyItem,
    PublicCategoryJobItem,
    PublicCompaniesByCategoryResult,
    PublicCompanyDetailResult,
)
from contactsafe_server.db.models import Org, OrgJob
from contactsafe_server.services.company_slug import company_slug, matches_company_slug

VALID_CATEGORY_SLUGS: Final[frozenset[str]] = frozenset(
    {
        "top-tech-companies-hiring",
        "ai-startups-hiring",
        "remote-first-companies-hiring",
        "series-a-startups-hiring",
        "fintech-companies-hiring",
        "healthtech-companies-hiring",
    }
)

_MAX_COMPANIES: Final[int] = 50
_MAX_SAMPLE_JOBS: Final[int] = 3

_AI_STARTUP_SIZE_BANDS: Final[tuple[str, ...]] = (
    "1-10",
    "11-50",
    "51-200",
    "201-500",
)
_SERIES_A_SIZE_BANDS: Final[tuple[str, ...]] = ("11-50", "51-200")

_AI_DESCRIPTION_PATTERNS: Final[tuple[str, ...]] = (
    "%artificial intelligence%",
    "%machine learning%",
    "% ai %",
    "%llm%",
    "%generative ai%",
)

_FINTECH_DESCRIPTION_PATTERNS: Final[tuple[str, ...]] = (
    "%fintech%",
    "%financial%",
)

_HEALTHTECH_DESCRIPTION_PATTERNS: Final[tuple[str, ...]] = (
    "%health%",
    "%medical%",
    "%clinical%",
)


def is_valid_category_slug(slug: str) -> bool:
    return slug in VALID_CATEGORY_SLUGS


def _description_matches(patterns: tuple[str, ...]):
    clauses = [Org.description.ilike(pattern) for pattern in patterns]
    return or_(*clauses)


def _has_category_tag(tag: str):
    return Org.categories.any(tag)


def _active_job_count_expr() -> func.count:
    return func.count(OrgJob.id)


def _category_org_filter(category: str):
    if category == "top-tech-companies-hiring":
        return _has_category_tag("naics:51")

    if category == "ai-startups-hiring":
        return and_(
            _has_category_tag("naics:51"),
            _description_matches(_AI_DESCRIPTION_PATTERNS),
            Org.company_size_band.in_(_AI_STARTUP_SIZE_BANDS),
        )

    if category == "series-a-startups-hiring":
        return Org.company_size_band.in_(_SERIES_A_SIZE_BANDS)

    if category == "fintech-companies-hiring":
        return or_(
            _has_category_tag("naics:52"),
            and_(
                _has_category_tag("naics:51"),
                _description_matches(_FINTECH_DESCRIPTION_PATTERNS),
            ),
        )

    if category == "healthtech-companies-hiring":
        return or_(
            _has_category_tag("naics:62"),
            and_(
                _has_category_tag("naics:51"),
                _description_matches(_HEALTHTECH_DESCRIPTION_PATTERNS),
            ),
        )

    # remote-first-companies-hiring handled via HAVING in query builder
    return True


def _base_org_job_query(category: str) -> Select[tuple[UUID, str, str | None, str | None, str | None, int]]:
    job_count: func.count = _active_job_count_expr()
    stmt: Select[tuple[UUID, str, str | None, str | None, str | None, int]] = (
        select(
            Org.id,
            Org.canonical_name,
            Org.primary_domain,
            Org.description,
            Org.company_size_band,
            job_count.label("active_job_count"),
        )
        .join(OrgJob, OrgJob.org_id == Org.id)
        .where(OrgJob.is_active.is_(True))
        .group_by(
            Org.id,
            Org.canonical_name,
            Org.primary_domain,
            Org.description,
            Org.company_size_band,
        )
        .having(job_count > 0)
    )

    if category == "remote-first-companies-hiring":
        remote_jobs: func.sum = func.sum(
            case((OrgJob.remote_status == "remote", 1), else_=0)
        )
        stmt = stmt.having(remote_jobs * 2 > job_count)
    else:
        org_filter = _category_org_filter(category)
        if org_filter is not True:
            stmt = stmt.where(org_filter)

    return stmt.order_by(job_count.desc()).limit(_MAX_COMPANIES)


class PublicCompanyCategoryService:
    def __init__(self, db: AsyncSession) -> None:
        self._db: AsyncSession = db

    async def list_companies_by_category(
        self,
        category: str,
    ) -> PublicCompaniesByCategoryResult | None:
        if not is_valid_category_slug(category):
            return None

        result = await self._db.execute(_base_org_job_query(category))
        rows = result.all()
        if not rows:
            return PublicCompaniesByCategoryResult(
                category=category,
                companies=[],
                total_companies=0,
                total_jobs=0,
                generated_at=datetime.now(tz=UTC),
            )

        org_ids: list[UUID] = [row.id for row in rows]
        jobs_by_org: dict[UUID, list[PublicCategoryJobItem]] = await self._load_sample_jobs(
            org_ids
        )

        companies: list[PublicCategoryCompanyItem] = []
        total_jobs: int = 0
        for row in rows:
            active_job_count: int = int(row.active_job_count)
            total_jobs += active_job_count
            companies.append(
                PublicCategoryCompanyItem(
                    org_id=row.id,
                    slug=company_slug(row.canonical_name),
                    name=row.canonical_name,
                    primary_domain=row.primary_domain,
                    description=row.description,
                    company_size_band=row.company_size_band,
                    active_job_count=active_job_count,
                    sample_jobs=jobs_by_org.get(row.id, []),
                )
            )

        return PublicCompaniesByCategoryResult(
            category=category,
            companies=companies,
            total_companies=len(companies),
            total_jobs=total_jobs,
            generated_at=datetime.now(tz=UTC),
        )

    async def _load_sample_jobs(
        self,
        org_ids: list[UUID],
    ) -> dict[UUID, list[PublicCategoryJobItem]]:
        if not org_ids:
            return {}

        result = await self._db.execute(
            select(OrgJob)
            .where(
                OrgJob.org_id.in_(org_ids),
                OrgJob.is_active.is_(True),
            )
            .order_by(
                OrgJob.org_id,
                OrgJob.posted_at.desc().nullslast(),
                OrgJob.last_seen_at.desc(),
            )
        )
        jobs: list[OrgJob] = list(result.scalars().all())

        grouped: dict[UUID, list[PublicCategoryJobItem]] = {}
        for job in jobs:
            bucket: list[PublicCategoryJobItem] = grouped.setdefault(job.org_id, [])
            if len(bucket) >= _MAX_SAMPLE_JOBS:
                continue
            bucket.append(
                PublicCategoryJobItem(
                    job_id=job.id,
                    title=job.title,
                    location=job.location,
                    url=job.url,
                    remote_status=job.remote_status,
                    posted_at=job.posted_at,
                )
            )
        return grouped

    async def get_company_by_slug(
        self,
        slug: str,
    ) -> PublicCompanyDetailResult | None:
        normalized_slug: str = slug.strip().lower()
        if not normalized_slug:
            return None

        active_org_ids = (
            select(OrgJob.org_id)
            .where(OrgJob.is_active.is_(True))
            .distinct()
        )
        result = await self._db.execute(select(Org).where(Org.id.in_(active_org_ids)))
        orgs: list[Org] = list(result.scalars().all())
        org: Org | None = next(
            (
                candidate
                for candidate in orgs
                if matches_company_slug(
                    normalized_slug,
                    candidate.canonical_name,
                    candidate.primary_domain,
                )
            ),
            None,
        )
        if org is None:
            return None

        jobs_result = await self._db.execute(
            select(OrgJob)
            .where(
                OrgJob.org_id == org.id,
                OrgJob.is_active.is_(True),
            )
            .order_by(
                OrgJob.posted_at.desc().nullslast(),
                OrgJob.last_seen_at.desc(),
            )
        )
        jobs: list[OrgJob] = list(jobs_result.scalars().all())
        job_items: list[PublicCategoryJobItem] = [
            PublicCategoryJobItem(
                job_id=job.id,
                title=job.title,
                location=job.location,
                url=job.url,
                remote_status=job.remote_status,
                posted_at=job.posted_at,
            )
            for job in jobs
        ]

        return PublicCompanyDetailResult(
            org_id=org.id,
            slug=company_slug(org.canonical_name),
            name=org.canonical_name,
            primary_domain=org.primary_domain,
            description=org.description,
            company_size_band=org.company_size_band,
            active_job_count=len(job_items),
            jobs=job_items,
            generated_at=datetime.now(tz=UTC),
        )
