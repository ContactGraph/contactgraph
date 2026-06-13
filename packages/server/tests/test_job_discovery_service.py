from __future__ import annotations

import uuid
from typing import Any, cast
from unittest.mock import AsyncMock, patch

import pytest
from contactsafe_server.config import get_settings
from contactsafe_server.services.job_discovery_service import (
    JobDiscoveryService,
    ScrapeOrgResult,
)
from contactsafe_server.db.models import Org


class FakeDb:
    def __init__(self, org: Org | None = None) -> None:
        self.org: Org | None = org
        self.added: list[object] = []
        self.commits: int = 0
        self.get_calls: list[tuple[type[object], uuid.UUID]] = []

    async def get(self, model: type[object], row_id: uuid.UUID) -> object | None:
        self.get_calls.append((model, row_id))
        if model is Org and self.org is not None and self.org.id == row_id:
            return self.org
        return None

    def add(self, instance: object) -> None:
        self.added.append(instance)

    async def commit(self) -> None:
        self.commits += 1


@pytest.mark.asyncio
async def test_discover_single_org_rejects_unmonitored_org(monkeypatch: pytest.MonkeyPatch) -> None:
    user_id: uuid.UUID = uuid.uuid4()
    victim_org_id: uuid.UUID = uuid.uuid4()
    db = FakeDb(
        Org(
            id=victim_org_id,
            canonical_name="Victim Org",
            categories=[],
            attributes={},
        ),
    )
    service = JobDiscoveryService(cast(Any, db), get_settings())
    discover_called: bool = False

    async def list_monitored_org_ids(_user_id: uuid.UUID) -> list[uuid.UUID]:
        return []

    async def scrape_org_global(
        _org_id: uuid.UUID, *, force: bool = False
    ) -> ScrapeOrgResult:
        nonlocal discover_called
        discover_called = True
        return ScrapeOrgResult(jobs_found=1, new_jobs=1, source="theirstack", error=None, scanned=True)

    monkeypatch.setattr(service, "_list_monitored_org_ids", list_monitored_org_ids)
    monkeypatch.setattr(service, "scrape_org_global", scrape_org_global)

    with patch("contactsafe_server.config.get_settings") as mock_settings:
        mock_settings.return_value = get_settings()
        mock_settings.return_value.use_arq_worker = False
        result = await service.discover_single_org(user_id, victim_org_id)

    assert result.scheduled is False
    assert "monitored job list" in result.message
    assert discover_called is False


@pytest.mark.asyncio
async def test_discover_single_org_succeeds_for_monitored_org(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user_id: uuid.UUID = uuid.uuid4()
    org_id: uuid.UUID = uuid.uuid4()
    db = FakeDb(
        Org(
            id=org_id,
            canonical_name="Allowed Org",
            categories=[],
            attributes={},
        ),
    )
    service = JobDiscoveryService(cast(Any, db), get_settings())

    async def list_monitored_org_ids(_user_id: uuid.UUID) -> list[uuid.UUID]:
        return [org_id]

    async def scrape_org_global(
        _org_id: uuid.UUID, *, force: bool = False
    ) -> ScrapeOrgResult:
        return ScrapeOrgResult(jobs_found=3, new_jobs=2, source="theirstack", error=None, scanned=True)

    async def classify_new_jobs(_user_id: uuid.UUID) -> None:
        return None

    monkeypatch.setattr(service, "_list_monitored_org_ids", list_monitored_org_ids)
    monkeypatch.setattr(service, "scrape_org_global", scrape_org_global)
    monkeypatch.setattr(service, "_classify_new_jobs", classify_new_jobs)

    with (
        patch("contactsafe_server.config.get_settings") as mock_settings,
        patch("contactsafe_server.job_event_publishers.publish_scan_progress"),
    ):
        mock_settings.return_value = get_settings()
        mock_settings.return_value.use_arq_worker = False
        result = await service.discover_single_org(user_id, org_id)

    assert result.scheduled is True
    assert result.jobs_found == 3
    assert result.new_jobs == 2


@pytest.mark.asyncio
async def test_discover_single_org_schedules_via_arq_when_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user_id: uuid.UUID = uuid.uuid4()
    org_id: uuid.UUID = uuid.uuid4()
    db = FakeDb(
        Org(
            id=org_id,
            canonical_name="Queued Org",
            categories=[],
            attributes={},
        ),
    )
    service = JobDiscoveryService(cast(Any, db), get_settings())

    async def list_monitored_org_ids(_user_id: uuid.UUID) -> list[uuid.UUID]:
        return [org_id]

    monkeypatch.setattr(service, "_list_monitored_org_ids", list_monitored_org_ids)

    with (
        patch("contactsafe_server.config.get_settings") as mock_settings,
        patch("contactsafe_server.queue.enqueue_background_job", new_callable=AsyncMock) as mock_enqueue,
    ):
        mock_settings.return_value = get_settings()
        mock_settings.return_value.use_arq_worker = True
        mock_enqueue.return_value = f"scrape-org-{org_id}"
        result = await service.discover_single_org(user_id, org_id)

    assert result.scheduled is True
    assert "scheduled" in result.message
    mock_enqueue.assert_awaited_once()
