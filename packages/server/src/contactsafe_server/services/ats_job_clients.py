"""Direct ATS public API clients for Greenhouse, Lever, and Ashby."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, cast
import httpx

from contactsafe_server.services.job_discovery_types import DiscoveredJob, JobSource

logger: logging.Logger = logging.getLogger(__name__)

_DESCRIPTION_SNIPPET_MAX: int = 500


class AtsJobClient:
    def __init__(self, timeout_seconds: float = 30.0) -> None:
        self._timeout: float = timeout_seconds

    async def fetch_jobs(
        self,
        provider: JobSource,
        board_token: str,
    ) -> list[DiscoveredJob]:
        if provider == "greenhouse":
            return await self._fetch_greenhouse(board_token)
        if provider == "lever":
            return await self._fetch_lever(board_token)
        if provider == "ashby":
            return await self._fetch_ashby(board_token)
        return []

    async def _fetch_greenhouse(self, board_token: str) -> list[DiscoveredJob]:
        url: str = (
            f"https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs"
            "?content=true"
        )
        data: dict[str, Any] = await self._get_json(url)
        jobs_raw: list[dict[str, Any]] = cast(list[dict[str, Any]], data.get("jobs", []))
        discovered: list[DiscoveredJob] = []
        for job in jobs_raw:
            job_id: str = str(job.get("id", ""))
            title: str = str(job.get("title", "")).strip()
            apply_url: str = str(job.get("absolute_url", "")).strip()
            if not job_id or not title or not apply_url:
                continue
            location_obj: dict[str, Any] | None = job.get("location")
            location: str | None = None
            if isinstance(location_obj, dict):
                location = str(location_obj.get("name", "")).strip() or None
            departments: list[str] = []
            for dept in job.get("departments", []):
                if isinstance(dept, dict) and dept.get("name"):
                    departments.append(str(dept["name"]))
            department: str | None = ", ".join(departments) if departments else None
            content: str | None = None
            if job.get("content"):
                content = _snippet(str(job["content"]))
            posted_at: datetime | None = _parse_datetime(job.get("updated_at"))
            discovered.append(
                DiscoveredJob(
                    external_job_id=job_id,
                    source="greenhouse",
                    title=title,
                    url=apply_url,
                    location=location,
                    department=department,
                    description_snippet=content,
                    posted_at=posted_at,
                ),
            )
        return discovered

    async def _fetch_lever(self, board_token: str) -> list[DiscoveredJob]:
        url: str = f"https://api.lever.co/v0/postings/{board_token}?mode=json"
        data: Any = await self._get_json(url)
        if not isinstance(data, list):
            return []
        discovered: list[DiscoveredJob] = []
        for job in cast(list[dict[str, Any]], data):
            job_id: str = str(job.get("id", "")).strip()
            title: str = str(job.get("text", "")).strip()
            apply_url: str = str(job.get("hostedUrl", "")).strip()
            if not job_id or not title or not apply_url:
                continue
            categories: dict[str, Any] = cast(dict[str, Any], job.get("categories", {}))
            location: str | None = None
            if categories.get("location"):
                location = str(categories["location"]).strip()
            department_parts: list[str] = []
            if categories.get("team"):
                department_parts.append(str(categories["team"]).strip())
            if categories.get("department"):
                department_parts.append(str(categories["department"]).strip())
            department: str | None = (
                ", ".join(department_parts) if department_parts else None
            )
            remote_status: str | None = None
            if job.get("workplaceType"):
                remote_status = str(job["workplaceType"]).strip().lower()
            salary_min: int | None = None
            salary_max: int | None = None
            salary_range: dict[str, Any] | None = job.get("salaryRange")
            if isinstance(salary_range, dict):
                salary_min = _parse_int(salary_range.get("min"))
                salary_max = _parse_int(salary_range.get("max"))
            description: str | None = None
            if job.get("descriptionPlain"):
                description = _snippet(str(job["descriptionPlain"]))
            discovered.append(
                DiscoveredJob(
                    external_job_id=job_id,
                    source="lever",
                    title=title,
                    url=apply_url,
                    location=location,
                    department=department,
                    description_snippet=description,
                    salary_min=salary_min,
                    salary_max=salary_max,
                    remote_status=remote_status,
                ),
            )
        return discovered

    async def _fetch_ashby(self, board_token: str) -> list[DiscoveredJob]:
        url: str = (
            f"https://api.ashbyhq.com/posting-api/job-board/{board_token}"
            "?includeCompensation=true"
        )
        data: dict[str, Any] = await self._get_json(url)
        jobs_raw: list[dict[str, Any]] = cast(list[dict[str, Any]], data.get("jobs", []))
        discovered: list[DiscoveredJob] = []
        for job in jobs_raw:
            job_id: str = str(job.get("id", "")).strip()
            title: str = str(job.get("title", "")).strip()
            apply_url: str = str(job.get("applyUrl", "")).strip()
            if not job_id or not title or not apply_url:
                continue
            location: str | None = None
            if job.get("location"):
                location = str(job["location"]).strip()
            department: str | None = None
            if job.get("department"):
                department = str(job["department"]).strip()
            remote_status: str | None = None
            if job.get("isRemote"):
                remote_status = "remote"
            salary_min: int | None = None
            salary_max: int | None = None
            compensation: dict[str, Any] | None = job.get("compensation")
            if isinstance(compensation, dict):
                summary: str | None = compensation.get("compensationTierSummary")
                if summary:
                    salary_min, salary_max = _parse_salary_summary(str(summary))
            description: str | None = None
            if job.get("descriptionPlain"):
                description = _snippet(str(job["descriptionPlain"]))
            posted_at: datetime | None = _parse_datetime(job.get("publishedAt"))
            discovered.append(
                DiscoveredJob(
                    external_job_id=job_id,
                    source="ashby",
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

    async def _get_json(self, url: str) -> Any:
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.get(url)
                response.raise_for_status()
                return response.json()
        except Exception:
            logger.warning("ATS job fetch failed for %s", url, exc_info=True)
            return {} if "job-board" in url or "boards-api" in url else []


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


def _parse_salary_summary(summary: str) -> tuple[int | None, int | None]:
    import re

    numbers: list[int] = [int(match) for match in re.findall(r"\d[\d,]*", summary)]
    if not numbers:
        return None, None
    if len(numbers) >= 2:
        return numbers[0], numbers[1]
    return numbers[0], None
