import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from contactsafe_core.enums import EnrichmentRunState
from contactsafe_server.db.models import User, UserPersonObservation
from contactsafe_server.services.enrichment_service import EnrichmentService


@pytest.mark.asyncio
async def test_start_enrichment_requires_imported_contacts(
    db_session: AsyncSession,
) -> None:
    user: User = User(email="no-import@example.com")
    db_session.add(user)
    await db_session.flush()

    svc = EnrichmentService(db_session)
    result = await svc.start_enrichment(user.id)

    assert result.scheduled is False
    assert "import" in result.message.lower()


@pytest.mark.asyncio
async def test_get_enrichment_status_when_never_run(
    db_session: AsyncSession,
) -> None:
    user: User = User(email="fresh@example.com")
    db_session.add(user)
    await db_session.flush()

    svc = EnrichmentService(db_session)
    status = await svc.get_enrichment_status(user.id)

    assert status.state == EnrichmentRunState.PENDING
    assert status.run_id is None


@pytest.mark.asyncio
async def test_start_enrichment_schedules_when_contacts_exist(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from contactsafe_server.db.models import Person

    user: User = User(email="ready@example.com")
    db_session.add(user)
    await db_session.flush()

    person: Person = Person(canonical_name="Friend", primary_email="friend@example.com")
    db_session.add(person)
    await db_session.flush()

    obs = UserPersonObservation(
        user_id=user.id,
        person_id=person.id,
        is_human=True,
    )
    db_session.add(obs)
    await db_session.flush()

    scheduled: list[uuid.UUID] = []

    monkeypatch.setattr(
        "contactsafe_server.services.enrichment_service.schedule_enrichment",
        lambda user_id, run_id: scheduled.append(run_id) or True,
    )
    monkeypatch.setattr(
        "contactsafe_server.services.enrichment_service.is_enrichment_running",
        lambda uid: False,
    )

    svc = EnrichmentService(db_session)
    result = await svc.start_enrichment(user.id)

    assert result.scheduled is True
    assert result.run_id is not None
    assert scheduled == [result.run_id]
