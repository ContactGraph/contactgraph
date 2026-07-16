"""Tests for public company category listings."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from contactsafe_server.db.models import Org, OrgJob
from contactsafe_server.services.public_company_category_service import (
    PublicCompanyCategoryService,
    is_valid_category_slug,
)


@pytest.mark.parametrize(
    "slug",
    [
        "top-tech-companies-hiring",
        "ai-startups-hiring",
        "remote-first-companies-hiring",
        "series-a-startups-hiring",
        "fintech-companies-hiring",
        "healthtech-companies-hiring",
    ],
)
def test_valid_category_slugs(slug: str) -> None:
    assert is_valid_category_slug(slug) is True


def test_invalid_category_slug() -> None:
    assert is_valid_category_slug("not-a-category") is False


@pytest.mark.asyncio
async def test_list_top_tech_companies(db_session: AsyncSession) -> None:
    org: Org = Org(
        id=uuid.uuid4(),
        canonical_name="Example Tech Co",
        description="A software company building cloud products.",
        categories=["naics:51"],
        company_size_band="51-200",
    )
    db_session.add(org)
    await db_session.flush()

    db_session.add_all(
        [
            OrgJob(
                org_id=org.id,
                external_job_id="job-1",
                source="greenhouse",
                title="Senior Engineer",
                url="https://example.com/jobs/1",
                is_active=True,
                remote_status="hybrid",
                posted_at=datetime.now(tz=UTC),
            ),
            OrgJob(
                org_id=org.id,
                external_job_id="job-2",
                source="greenhouse",
                title="Product Manager",
                url="https://example.com/jobs/2",
                is_active=True,
                remote_status="remote",
                posted_at=datetime.now(tz=UTC),
            ),
        ]
    )
    await db_session.commit()

    service = PublicCompanyCategoryService(db_session)
    result = await service.list_companies_by_category("top-tech-companies-hiring")

    assert result is not None
    assert result.total_companies == 1
    assert result.total_jobs == 2
    assert result.companies[0].name == "Example Tech Co"
    assert result.companies[0].slug == "example-tech-co"
    assert len(result.companies[0].sample_jobs) == 2


@pytest.mark.asyncio
async def test_get_company_by_slug(db_session: AsyncSession) -> None:
    org: Org = Org(
        id=uuid.uuid4(),
        canonical_name="Baylor Genetics",
        description="Clinical genomics laboratory.",
        categories=["naics:62"],
        company_size_band="201-500",
    )
    db_session.add(org)
    await db_session.flush()

    db_session.add(
        OrgJob(
            org_id=org.id,
            external_job_id="job-1",
            source="greenhouse",
            title="Lab Director",
            url="https://example.com/jobs/lab-director",
            is_active=True,
            remote_status="onsite",
            posted_at=datetime.now(tz=UTC),
        )
    )
    await db_session.commit()

    service = PublicCompanyCategoryService(db_session)
    result = await service.get_company_by_slug("baylor-genetics")

    assert result is not None
    assert result.name == "Baylor Genetics"
    assert result.slug == "baylor-genetics"
    assert result.active_job_count == 1
    assert result.jobs[0].title == "Lab Director"


@pytest.mark.asyncio
async def test_unknown_category_returns_none(db_session: AsyncSession) -> None:
    service = PublicCompanyCategoryService(db_session)
    result = await service.list_companies_by_category("unknown-category")
    assert result is None
