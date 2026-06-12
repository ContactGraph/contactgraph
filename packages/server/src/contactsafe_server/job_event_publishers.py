"""Publish job-related SSE events from discovery and scoring services."""

from __future__ import annotations

import uuid

from contactsafe_server.events import ScanProgressEvent, job_event_bus


def publish_scan_progress(
    user_id: uuid.UUID,
    *,
    scanning_active: bool,
    current_org_name: str | None = None,
) -> None:
    event: ScanProgressEvent = {
        "type": "scan_progress",
        "scanning_active": scanning_active,
        "current_org_name": current_org_name,
    }
    job_event_bus.publish(user_id, event)


def publish_scan_progress_for_users(
    user_ids: list[uuid.UUID],
    *,
    scanning_active: bool,
    current_org_name: str | None = None,
) -> None:
    for user_id in user_ids:
        publish_scan_progress(
            user_id,
            scanning_active=scanning_active,
            current_org_name=current_org_name,
        )
