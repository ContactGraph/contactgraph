"""Pub/sub for job discovery, scoring, and graph progress events."""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from dataclasses import dataclass, field
from typing import Literal, TypedDict

logger: logging.Logger = logging.getLogger(__name__)


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
    _listener_tasks: dict[tuple[uuid.UUID, int], asyncio.Task[None]] = field(
        default_factory=dict,
        repr=False,
    )
    _channel_prefix: str = ""

    def register(self, user_id: uuid.UUID) -> asyncio.Queue[TEvent | None]:
        queue: asyncio.Queue[TEvent | None] = asyncio.Queue()
        self._subscribers.setdefault(user_id, []).append(queue)
        self._start_redis_listener(user_id, queue)
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
        task_key: tuple[uuid.UUID, int] = (user_id, id(queue))
        listener: asyncio.Task[None] | None = self._listener_tasks.pop(task_key, None)
        if listener is not None:
            listener.cancel()
        if not subscribers:
            del self._subscribers[user_id]

    def publish(self, user_id: uuid.UUID, event: TEvent) -> None:
        for queue in self._subscribers.get(user_id, []):
            queue.put_nowait(event)
        self._schedule_redis_publish(user_id, event)

    def _schedule_redis_publish(self, user_id: uuid.UUID, event: TEvent) -> None:
        from contactsafe_server.config import get_settings

        if not get_settings().use_arq_worker:
            return
        try:
            loop: asyncio.AbstractEventLoop = asyncio.get_running_loop()
        except RuntimeError:
            return
        loop.create_task(self._publish_redis(user_id, event))

    async def _publish_redis(self, user_id: uuid.UUID, event: TEvent) -> None:
        if not self._channel_prefix:
            return
        try:
            from contactsafe_server.redis_state import get_redis_client

            client = await get_redis_client()
            channel: str = f"{self._channel_prefix}:{user_id}"
            await client.publish(channel, json.dumps(event))
        except Exception:
            logger.exception("Failed to publish event to Redis for user %s", user_id)

    def _start_redis_listener(
        self,
        user_id: uuid.UUID,
        queue: asyncio.Queue[TEvent | None],
    ) -> None:
        from contactsafe_server.config import get_settings

        if not get_settings().use_arq_worker or not self._channel_prefix:
            return
        try:
            loop: asyncio.AbstractEventLoop = asyncio.get_running_loop()
        except RuntimeError:
            return
        task_key: tuple[uuid.UUID, int] = (user_id, id(queue))
        if task_key in self._listener_tasks:
            return
        self._listener_tasks[task_key] = loop.create_task(
            self._redis_listener(user_id, queue),
            name=f"redis-listener-{self._channel_prefix}-{user_id}",
        )

    async def _redis_listener(
        self,
        user_id: uuid.UUID,
        queue: asyncio.Queue[TEvent | None],
    ) -> None:
        if not self._channel_prefix:
            return
        try:
            from contactsafe_server.redis_state import get_redis_client

            client = await get_redis_client()
            pubsub = client.pubsub()
            channel: str = f"{self._channel_prefix}:{user_id}"
            await pubsub.subscribe(channel)
            async for message in pubsub.listen():
                if message["type"] != "message":
                    continue
                data_raw: object = message.get("data")
                if not isinstance(data_raw, str):
                    continue
                event: TEvent = json.loads(data_raw)
                queue.put_nowait(event)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Redis event listener failed for user %s", user_id)


@dataclass
class JobEventBus(_EventBus[JobEvent]):
    _channel_prefix: str = "job_events"


@dataclass
class GraphEventBus(_EventBus[GraphEvent]):
    _channel_prefix: str = "graph_events"


job_event_bus: JobEventBus = JobEventBus()
graph_event_bus: GraphEventBus = GraphEventBus()
