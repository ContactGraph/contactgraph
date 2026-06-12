"""In-memory pub/sub for job discovery, scoring, and graph progress events."""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field
from typing import Literal, TypedDict


class DiscoveryProgressEvent(TypedDict):
    type: Literal["discovery_progress"]
    orgs_processed: int
    orgs_total: int
    jobs_found: int
    new_jobs: int
    progress_message: str | None


class DiscoveryCompleteEvent(TypedDict):
    type: Literal["discovery_complete"]
    jobs_found: int
    new_jobs: int


class DiscoveryCancelledEvent(TypedDict):
    type: Literal["discovery_cancelled"]


class ScoringProgressEvent(TypedDict):
    type: Literal["scoring_progress"]
    scored: int
    total: int


class ScoringCompleteEvent(TypedDict):
    type: Literal["scoring_complete"]
    scored: int
    total: int


class ScoringCancelledEvent(TypedDict):
    type: Literal["scoring_cancelled"]
    scored: int
    total: int


class ScanProgressEvent(TypedDict):
    type: Literal["scan_progress"]
    scanning_active: bool
    current_org_name: str | None


JobEvent = (
    DiscoveryProgressEvent
    | DiscoveryCompleteEvent
    | DiscoveryCancelledEvent
    | ScoringProgressEvent
    | ScoringCompleteEvent
    | ScoringCancelledEvent
    | ScanProgressEvent
)


class SourceSyncProgressEvent(TypedDict):
    type: Literal["source_sync_progress"]
    source_id: str
    source_type: str
    sync_state: str
    contacts_found: int
    contacts_resolved: int
    contacts_pending: int
    sync_error: str | None


class SourceSyncCompleteEvent(TypedDict):
    type: Literal["source_sync_complete"]
    source_id: str
    source_type: str
    contacts_found: int
    contacts_resolved: int


class SourceSyncFailedEvent(TypedDict):
    type: Literal["source_sync_failed"]
    source_id: str
    source_type: str
    sync_error: str | None


class OrgEnrichmentProgressEvent(TypedDict):
    type: Literal["org_enrichment_progress"]
    orgs_enriched: int
    orgs_total: int
    progress_message: str | None
    state: Literal["running"]


class OrgEnrichmentCompleteEvent(TypedDict):
    type: Literal["org_enrichment_complete"]
    orgs_enriched: int
    orgs_total: int


class OrgEnrichmentFailedEvent(TypedDict):
    type: Literal["org_enrichment_failed"]
    orgs_enriched: int
    orgs_total: int
    error: str | None


GraphEvent = (
    SourceSyncProgressEvent
    | SourceSyncCompleteEvent
    | SourceSyncFailedEvent
    | OrgEnrichmentProgressEvent
    | OrgEnrichmentCompleteEvent
    | OrgEnrichmentFailedEvent
)


@dataclass
class _EventBus[TEvent]:
    _subscribers: dict[uuid.UUID, list[asyncio.Queue[TEvent | None]]] = field(
        default_factory=dict,
    )

    def register(self, user_id: uuid.UUID) -> asyncio.Queue[TEvent | None]:
        queue: asyncio.Queue[TEvent | None] = asyncio.Queue()
        self._subscribers.setdefault(user_id, []).append(queue)
        return queue

    def unregister(
        self,
        user_id: uuid.UUID,
        queue: asyncio.Queue[TEvent | None],
    ) -> None:
        subscribers: list[asyncio.Queue[TEvent | None]] | None = self._subscribers.get(
            user_id,
        )
        if subscribers is None:
            return
        if queue in subscribers:
            subscribers.remove(queue)
        if not subscribers:
            del self._subscribers[user_id]

    def publish(self, user_id: uuid.UUID, event: TEvent) -> None:
        for queue in self._subscribers.get(user_id, []):
            queue.put_nowait(event)


@dataclass
class JobEventBus(_EventBus[JobEvent]):
    pass


@dataclass
class GraphEventBus(_EventBus[GraphEvent]):
    pass


job_event_bus: JobEventBus = JobEventBus()
graph_event_bus: GraphEventBus = GraphEventBus()
