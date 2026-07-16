"""TheirStack webhook handler for real-time job notifications."""

from __future__ import annotations

import hashlib
import hmac
import logging
from typing import Any, cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from contactsafe_server.config import Settings
from contactsafe_server.db.models import Org, OrgListMembership, User
from contactsafe_server.services.job_discovery_service import JobDiscoveryService
from contactsafe_server.services.job_discovery_types import DiscoveredJob
from contactsafe_server.services.theirstack_client import _parse_datetime, _snippet

logger: logging.Logger = logging.getLogger(__name__)


def verify_theirstack_signature(
    payload: bytes,
    signature_header: str,
    secret: str,
) -> bool:
    if not signature_header or not secret:
        return False
    expected: str = "sha256=" + hmac.new(
        secret.encode("utf-8"),
        payload,
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, signature_header)


def parse_theirstack_job_event(body: dict[str, Any]) -> DiscoveredJob | None:
    job: dict[str, Any] = body
    if "job" in body and isinstance(body["job"], dict):
        job = cast(dict[str, Any], body["job"])
    job_id: str = str(job.get("id", "")).strip()
    title: str = str(job.get("job_title", job.get("title", ""))).strip()
    apply_url: str = str(
        job.get("url", job.get("final_url", job.get("apply_url", ""))),
    ).strip()
    if not apply_url:
        apply_url = str(job.get("source_url", "")).strip()
    if not job_id or not title or not apply_url:
        return None
    location: str | None = None
    if job.get("location"):
        location = str(job["location"]).strip()
    elif job.get("short_location"):
        location = str(job["short_location"]).strip()
    department: str | None = None
    if job.get("job_department"):
        department = str(job["job_department"]).strip()
    description: str | None = None
    if job.get("description"):
        description = _snippet(str(job["description"]))
    salary_min: int | None = None
    salary_max: int | None = None
    if job.get("min_salary_usd") is not None:
        try:
            salary_min = int(job["min_salary_usd"])
        except (TypeError, ValueError):
            salary_min = None
    if job.get("max_salary_usd") is not None:
        try:
            salary_max = int(job["max_salary_usd"])
        except (TypeError, ValueError):
            salary_max = None
    remote_status: str | None = None
    if job.get("remote") is True:
        remote_status = "remote"
    elif job.get("hybrid") is True:
        remote_status = "hybrid"
    posted_at = _parse_datetime(job.get("date_posted", job.get("posted_at")))
    return DiscoveredJob(
        external_job_id=job_id,
        source="theirstack",
        title=title,
        url=apply_url,
        location=location,
        department=department,
        description_snippet=description,
        salary_min=salary_min,
        salary_max=salary_max,
        remote_status=remote_status,
        posted_at=posted_at,
    )


async def resolve_org_for_theirstack_job(
    db: AsyncSession,
    job_payload: dict[str, Any],
) -> Org | None:
    company: dict[str, Any] | None = None
    if isinstance(job_payload.get("company"), dict):
        company = cast(dict[str, Any], job_payload["company"])
    domain: str | None = None
    if company and company.get("domain"):
        domain = str(company["domain"]).strip().lower()
    elif job_payload.get("company_domain"):
        domain = str(job_payload["company_domain"]).strip().lower()
    if domain:
        result = await db.execute(
            select(Org).where(Org.primary_domain == domain).limit(1),
        )
        org: Org | None = result.scalar_one_or_none()
        if org is not None:
            return org
    name: str | None = None
    if company and company.get("name"):
        name = str(company["name"]).strip()
    elif job_payload.get("company_name"):
        name = str(job_payload["company_name"]).strip()
    if name:
        result = await db.execute(
            select(Org).where(Org.canonical_name.ilike(name)).limit(1),
        )
        return result.scalar_one_or_none()
    return None


async def handle_theirstack_webhook(
    db: AsyncSession,
    settings: Settings,
    payload: bytes,
    signature_header: str | None,
    body: dict[str, Any],
) -> bool:
    secret: str | None = settings.theirstack_webhook_secret
    if secret and signature_header:
        if not verify_theirstack_signature(payload, signature_header, secret):
            logger.warning("TheirStack webhook signature verification failed")
            return False

    discovered: DiscoveredJob | None = parse_theirstack_job_event(body)
    if discovered is None:
        logger.warning("TheirStack webhook payload missing job fields")
        return False

    org: Org | None = await resolve_org_for_theirstack_job(db, body)
    if org is None:
        logger.info("TheirStack webhook: no matching org for job %s", discovered.external_job_id)
        return True

    monitored_result = await db.execute(
        select(User.id)
        .where(
            User.job_monitor_enabled.is_(True),
            User.job_monitor_list_id.is_not(None),
        )
        .join(
            OrgListMembership,
            OrgListMembership.org_list_id == User.job_monitor_list_id,
        )
        .where(OrgListMembership.org_id == org.id),
    )
    if monitored_result.scalar_one_or_none() is None:
        return True

    service = JobDiscoveryService(db, settings)
    await service.upsert_discovered_job(org.id, discovered)
    await db.commit()
    return True
