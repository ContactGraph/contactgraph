"""TheirStack job postings API client."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Any, cast

import httpx

from contactsafe_server.config import Settings
from contactsafe_server.db.models import Org
from contactsafe_server.services.job_discovery_types import DiscoveredJob

logger: logging.Logger = logging.getLogger(__name__)

_DESCRIPTION_SNIPPET_MAX: int = 500


class TheirStackClient:
    def __init__(self, settings: Settings) -> None:
        self._api_key: str | None = settings.theirstack_api_key
        self._base_url: str = settings.theirstack_base_url.rstrip("/")
        self._timeout: float = settings.theirstack_request_timeout_seconds
        self._max_age_days: int = settings.theirstack_job_max_age_days

    def is_configured(self) -> bool:
        return self._api_key is not None and bool(self._api_key.strip())

    async def search_jobs_for_org(self, org: Org, limit: int = 50) -> list[DiscoveredJob]:
        if not self.is_configured():
            return []

        payload: dict[str, Any] = {
            "posted_at_max_age_days": self._max_age_days,
            "limit": limit,
        }
        if org.primary_domain:
            payload["company_domain_or"] = [org.primary_domain]
        elif org.linkedin_url:
            payload["company_linkedin_url_or"] = [org.linkedin_url]
        else:
            payload["company_name_or"] = [org.canonical_name]

        data: dict[str, Any] = await self._post_json("/v1/jobs/search", payload)
        jobs_raw: list[dict[str, Any]] = cast(list[dict[str, Any]], data.get("data", []))
        discovered: list[DiscoveredJob] = []
        for job in jobs_raw:
            job_id: str = str(job.get("id", "")).strip()
            title: str = str(job.get("job_title", job.get("title", ""))).strip()
            apply_url: str = str(
                job.get("url", job.get("final_url", job.get("apply_url", "")),
            )).strip()
            if not job_id or not title:
                continue
            if not apply_url:
                apply_url = str(job.get("source_url", "")).strip()
            if not apply_url:
                continue
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
            salary_min: int | None = _parse_int(
                job.get("min_annual_salary_usd", job.get("min_salary_usd")),
            )
            salary_max: int | None = _parse_int(
                job.get("max_annual_salary_usd", job.get("max_salary_usd")),
            )
            remote_status: str | None = None
            if job.get("remote") is True:
                remote_status = "remote"
            elif job.get("hybrid") is True:
                remote_status = "hybrid"
            posted_at: datetime | None = _parse_datetime(
                job.get("date_posted", job.get("posted_at")),
            )
            discovered.append(
                DiscoveredJob(
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
                ),
            )
        return discovered

    async def _post_json(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        if not self._api_key:
            return {}
        url: str = f"{self._base_url}{path}"
        headers: dict[str, str] = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        max_retries: int = 3
        for attempt in range(max_retries):
            try:
                async with httpx.AsyncClient(timeout=self._timeout) as client:
                    response = await client.post(url, json=payload, headers=headers)
                    if response.status_code == 429 and attempt < max_retries - 1:
                        retry_after: float = float(
                            response.headers.get("Retry-After", "5"),
                        )
                        logger.info("TheirStack 429, retrying after %.1fs", retry_after)
                        await asyncio.sleep(retry_after)
                        continue
                    response.raise_for_status()
                    result: dict[str, Any] = response.json()
                    return result
            except httpx.HTTPStatusError:
                if attempt < max_retries - 1:
                    await asyncio.sleep(2.0 * (attempt + 1))
                    continue
                logger.warning("TheirStack request failed for %s", path, exc_info=True)
                return {}
            except Exception:
                logger.warning("TheirStack request failed for %s", path, exc_info=True)
                return {}
        return {}


def _snippet(text: str) -> str:
    import re

    stripped: str = re.sub(r"<[^>]+>", " ", text)
    stripped = stripped.replace("&lt;", "<").replace("&gt;", ">")
    stripped = stripped.replace("&amp;", "&").replace("&quot;", '"')
    stripped = stripped.replace("&#39;", "'").replace("&nbsp;", " ")
    cleaned: str = " ".join(stripped.split())
    if len(cleaned) <= _DESCRIPTION_SNIPPET_MAX:
        return cleaned
    return cleaned[:_DESCRIPTION_SNIPPET_MAX - 1].rstrip() + "…"


def _parse_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    text: str = str(value).strip()
    if not text:
        return None
    normalized: str = text.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(normalized)
    except ValueError:
        return None


def _parse_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
