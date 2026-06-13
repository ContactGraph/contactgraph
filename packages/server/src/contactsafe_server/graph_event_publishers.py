"""Publish graph-related SSE events from import and enrichment services."""

from __future__ import annotations

import uuid

from contactsafe_core.enums import SyncState
from contactsafe_server.db.models import Source
from contactsafe_server.events import (
    OrgEnrichmentCompleteEvent,
    OrgEnrichmentFailedEvent,
    OrgEnrichmentProgressEvent,
    SourceSyncCompleteEvent,
    SourceSyncFailedEvent,
    SourceSyncProgressEvent,
    graph_event_bus,
)


def source_sync_event_for(source: Source) -> (
    SourceSyncProgressEvent | SourceSyncCompleteEvent | SourceSyncFailedEvent
):
    source_id: str = str(source.id)
    source_type: str = source.source_type
    sync_state: str = source.sync_state

    if sync_state == SyncState.COMPLETE.value:
        return {
            "type": "source_sync_complete",
            "source_id": source_id,
            "source_type": source_type,
            "contacts_found": source.contacts_found,
            "contacts_resolved": source.contacts_resolved,
        }

    if sync_state == SyncState.FAILED.value:
        return {
            "type": "source_sync_failed",
            "source_id": source_id,
            "source_type": source_type,
            "sync_error": source.sync_error,
        }

    return {
        "type": "source_sync_progress",
        "source_id": source_id,
        "source_type": source_type,
        "sync_state": sync_state,
        "contacts_found": source.contacts_found,
        "contacts_resolved": source.contacts_resolved,
        "contacts_pending": source.contacts_pending,
        "sync_error": source.sync_error,
    }


def publish_source_sync_update(source: Source) -> None:
    """Emit the appropriate source sync event for the current source state."""
    graph_event_bus.publish(source.user_id, source_sync_event_for(source))


def publish_org_enrichment_progress(
    user_id: uuid.UUID,
    *,
    orgs_enriched: int,
    orgs_total: int,
    progress_message: str | None,
) -> None:
    event: OrgEnrichmentProgressEvent = {
        "type": "org_enrichment_progress",
        "orgs_enriched": orgs_enriched,
        "orgs_total": orgs_total,
        "progress_message": progress_message,
        "state": "running",
    }
    graph_event_bus.publish(user_id, event)


def publish_org_enrichment_complete(
    user_id: uuid.UUID,
    *,
    orgs_enriched: int,
    orgs_total: int,
) -> None:
    event: OrgEnrichmentCompleteEvent = {
        "type": "org_enrichment_complete",
        "orgs_enriched": orgs_enriched,
        "orgs_total": orgs_total,
    }
    graph_event_bus.publish(user_id, event)


def publish_org_enrichment_failed(
    user_id: uuid.UUID,
    *,
    orgs_enriched: int,
    orgs_total: int,
    error: str | None,
) -> None:
    event: OrgEnrichmentFailedEvent = {
        "type": "org_enrichment_failed",
        "orgs_enriched": orgs_enriched,
        "orgs_total": orgs_total,
        "error": error,
    }
    graph_event_bus.publish(user_id, event)
