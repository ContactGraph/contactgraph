"""Apply mechanical seniority + geocode attributes onto OrgJob rows."""

from __future__ import annotations

from contactsafe_server.db.models import OrgJob
from contactsafe_server.services.job_geocode import geocode_location
from contactsafe_server.services.job_seniority import classify_seniority_level


def apply_job_attributes(job: OrgJob) -> None:
    """Set seniority_level and location_* fields from title/location text.

    Pure compute — no network I/O. Safe to call on insert and update.
    """
    job.seniority_level = classify_seniority_level(
        job.title,
        job.description_snippet,
    )
    geo: tuple[float, float, str] | None = geocode_location(job.location)
    if geo is None:
        job.location_lat = None
        job.location_lng = None
        job.location_normalized = None
        return
    lat, lng, label = geo
    job.location_lat = lat
    job.location_lng = lng
    job.location_normalized = label
