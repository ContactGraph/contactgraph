"""In-memory pub/sub for job discovery and scoring progress events."""

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


JobEvent = (
    DiscoveryProgressEvent
    | DiscoveryCompleteEvent
    | DiscoveryCancelledEvent
    | ScoringProgressEvent
    | ScoringCompleteEvent
    | ScoringCancelledEvent
)


@dataclass
class JobEventBus:
    _subscribers: dict[uuid.UUID, list[asyncio.Queue[JobEvent | None]]] = field(
        default_factory=dict,
    )

    def register(self, user_id: uuid.UUID) -> asyncio.Queue[JobEvent | None]:
        queue: asyncio.Queue[JobEvent | None] = asyncio.Queue()
        self._subscribers.setdefault(user_id, []).append(queue)
        return queue

    def unregister(
        self,
        user_id: uuid.UUID,
        queue: asyncio.Queue[JobEvent | None],
    ) -> None:
        subscribers: list[asyncio.Queue[JobEvent | None]] | None = self._subscribers.get(
            user_id,
        )
        if subscribers is None:
            return
        if queue in subscribers:
            subscribers.remove(queue)
        if not subscribers:
            del self._subscribers[user_id]

    def publish(self, user_id: uuid.UUID, event: JobEvent) -> None:
        for queue in self._subscribers.get(user_id, []):
            queue.put_nowait(event)


job_event_bus: JobEventBus = JobEventBus()
