import asyncio
import uuid

import pytest
from contactsafe_server.services import import_scheduler


def _clear_scheduler_state() -> None:
    import_scheduler._active_sync_source_ids.clear()
    import_scheduler._active_sync_user_ids.clear()
    import_scheduler._active_sync_tasks_by_source_id.clear()
    import_scheduler._active_sync_task_users_by_source_id.clear()


@pytest.fixture(autouse=True)
def reset_scheduler_state() -> None:
    _clear_scheduler_state()
    yield
    _clear_scheduler_state()


@pytest.mark.asyncio
async def test_cancel_source_sync_keeps_lock_until_task_exits(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_id = uuid.uuid4()
    user_id = uuid.uuid4()
    started = asyncio.Event()
    finish = asyncio.Event()
    cancelled = asyncio.Event()

    async def fake_run_sync_task(task_source_id: uuid.UUID, task_user_id: uuid.UUID) -> None:
        assert task_source_id == source_id
        assert task_user_id == user_id
        started.set()
        try:
            await finish.wait()
        except asyncio.CancelledError:
            cancelled.set()
            raise
        finally:
            import_scheduler.release_sync_lock(task_source_id, task_user_id)

    monkeypatch.setattr(import_scheduler, "_run_sync_task", fake_run_sync_task)

    assert import_scheduler.schedule_source_sync(source_id, user_id) is True
    await asyncio.wait_for(started.wait(), timeout=1)

    assert import_scheduler.cancel_source_sync(source_id, user_id) is True
    assert import_scheduler.is_source_sync_running(source_id) is True
    assert import_scheduler.is_user_sync_running(user_id) is True
    assert import_scheduler.schedule_source_sync(source_id, user_id) is False

    await asyncio.wait_for(cancelled.wait(), timeout=1)
    await asyncio.sleep(0)

    assert import_scheduler.is_source_sync_running(source_id) is False
    assert import_scheduler.is_user_sync_running(user_id) is False


@pytest.mark.asyncio
async def test_cancel_source_sync_does_not_release_unrelated_user_lock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    active_source_id = uuid.uuid4()
    pending_source_id = uuid.uuid4()
    user_id = uuid.uuid4()
    started = asyncio.Event()
    finish = asyncio.Event()

    async def fake_run_sync_task(task_source_id: uuid.UUID, task_user_id: uuid.UUID) -> None:
        started.set()
        try:
            await finish.wait()
        finally:
            import_scheduler.release_sync_lock(task_source_id, task_user_id)

    monkeypatch.setattr(import_scheduler, "_run_sync_task", fake_run_sync_task)

    assert import_scheduler.schedule_source_sync(active_source_id, user_id) is True
    await asyncio.wait_for(started.wait(), timeout=1)

    assert import_scheduler.cancel_source_sync(pending_source_id, user_id) is False
    assert import_scheduler.is_source_sync_running(active_source_id) is True
    assert import_scheduler.is_user_sync_running(user_id) is True
    assert import_scheduler.schedule_source_sync(pending_source_id, user_id) is False

    finish.set()
    await asyncio.sleep(0)
