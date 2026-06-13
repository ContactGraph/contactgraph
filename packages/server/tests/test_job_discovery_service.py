from __future__ import annotations

import uuid
from typing import Any, cast

import pytest
from contactsafe_server.config import get_settings
from contactsafe_server.db.models import JobDiscoveryRun, JobScrapeRun, Org
from contactsafe_server.services.job_discovery_service import JobDiscoveryService


class FakeDb:
    def __init__(self, org: Org | None = None) -> None:
        self.org = org
        self.added: list[object] = []
        self.commits = 0
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
    user_id = uuid.uuid4()
    victim_org_id = uuid.uuid4()
    db = FakeDb(
        Org(
            id=victim_org_id,
            canonical_name="Victim Org",
            categories=[],
            attributes={},
        ),
    )
    service = JobDiscoveryService(cast(Any, db), get_settings())
    discover_called = False

    async def has_running_run(_user_id: uuid.UUID) -> bool:
        return False

    async def list_monitored_org_ids(_user_id: uuid.UUID) -> list[uuid.UUID]:
        return []

    async def discover_jobs_for_org(_org: Org) -> tuple[int, int, str, str | None]:
        nonlocal discover_called
        discover_called = True
        return 1, 1, "theirstack", None

    monkeypatch.setattr(service, "_has_running_run", has_running_run)
    monkeypatch.setattr(service, "_list_monitored_org_ids", list_monitored_org_ids)
    monkeypatch.setattr(service, "_discover_jobs_for_org", discover_jobs_for_org)

    result = await service.discover_single_org(user_id, victim_org_id)

    assert result.scheduled is False
    assert result.jobs_found == 0
    assert result.new_jobs == 0
    assert "monitored job list" in result.message
    assert discover_called is False
    assert db.added == []
    assert db.commits == 0
    assert db.get_calls == []


@pytest.mark.asyncio
async def test_discover_single_org_records_run_for_monitored_org(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user_id = uuid.uuid4()
    org_id = uuid.uuid4()
    db = FakeDb(
        Org(
            id=org_id,
            canonical_name="Allowed Org",
            categories=[],
            attributes={},
        ),
    )
    service = JobDiscoveryService(cast(Any, db), get_settings())

    async def has_running_run(_user_id: uuid.UUID) -> bool:
        return False

    async def list_monitored_org_ids(_user_id: uuid.UUID) -> list[uuid.UUID]:
        return [org_id]

    async def discover_jobs_for_org(_org: Org) -> tuple[int, int, str, str | None]:
        return 3, 2, "theirstack", None

    async def classify_new_jobs(_user_id: uuid.UUID) -> None:
        return None

    monkeypatch.setattr(service, "_has_running_run", has_running_run)
    monkeypatch.setattr(service, "_list_monitored_org_ids", list_monitored_org_ids)
    monkeypatch.setattr(service, "_discover_jobs_for_org", discover_jobs_for_org)
    monkeypatch.setattr(service, "_classify_new_jobs", classify_new_jobs)

    result = await service.discover_single_org(user_id, org_id)

    assert result.scheduled is True
    assert result.jobs_found == 3
    assert result.new_jobs == 2
    assert db.commits == 2
    assert any(isinstance(item, JobDiscoveryRun) for item in db.added)
    assert any(isinstance(item, JobScrapeRun) for item in db.added)

    run = next(item for item in db.added if isinstance(item, JobDiscoveryRun))
    assert run.user_id == user_id
    assert run.state == "complete"
    assert run.orgs_total == 1
    assert run.orgs_processed == 1
    assert run.jobs_found == 3
    assert run.new_jobs == 2


@pytest.mark.asyncio
async def test_discover_single_org_rejects_when_discovery_is_already_running(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user_id = uuid.uuid4()
    org_id = uuid.uuid4()
    db = FakeDb()
    service = JobDiscoveryService(cast(Any, db), get_settings())
    listed_orgs = False

    async def has_running_run(_user_id: uuid.UUID) -> bool:
        return True

    async def list_monitored_org_ids(_user_id: uuid.UUID) -> list[uuid.UUID]:
        nonlocal listed_orgs
        listed_orgs = True
        return [org_id]

    monkeypatch.setattr(service, "_has_running_run", has_running_run)
    monkeypatch.setattr(service, "_list_monitored_org_ids", list_monitored_org_ids)

    result = await service.discover_single_org(user_id, org_id)

    assert result.scheduled is False
    assert result.message == "Job discovery is already running."
    assert listed_orgs is False
    assert db.added == []
    assert db.commits == 0
