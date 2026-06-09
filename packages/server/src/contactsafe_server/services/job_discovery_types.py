"""Shared types for job discovery."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

JobSource = Literal["greenhouse", "lever", "ashby", "theirstack"]


@dataclass(frozen=True, slots=True)
class DiscoveredJob:
    external_job_id: str
    source: JobSource
    title: str
    url: str
    location: str | None = None
    department: str | None = None
    description_snippet: str | None = None
    salary_min: int | None = None
    salary_max: int | None = None
    remote_status: str | None = None
    posted_at: datetime | None = None
