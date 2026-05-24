import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from contactsafe_server.db.models import Org, Person, PersonEdge, User
from contactsafe_server.services.employment_service import EmploymentService


@pytest.mark.asyncio
async def test_upsert_current_employment_syncs_person_denorm(
    db_session: AsyncSession,
) -> None:
    user = User(email=f"emp-{uuid.uuid4()}@example.com")
    db_session.add(user)
    await db_session.flush()

    org = Org(
        user_id=user.id,
        canonical_name="Basebase",
        domain="basebase.com",
        aliases=["basebase"],
    )
    person = Person(
        user_id=user.id,
        canonical_name="Vincent Bannister",
        email_addresses=["vincent@basebase.com"],
        last_seen_in_email=datetime.now(tz=UTC),
    )
    db_session.add_all([org, person])
    await db_session.flush()
    db_session.add(
        PersonEdge(
            user_id=user.id,
            person_id=person.id,
            tie_strength_score=0.5,
            is_human=True,
            is_broadcast=False,
            is_automated=False,
        )
    )
    await db_session.flush()

    service = EmploymentService(db_session)
    await service.upsert_current_employment(
        user_id=user.id,
        person_id=person.id,
        org_id=org.id,
        role_title="Founder",
    )
    await db_session.refresh(person)

    assert person.current_org_id == org.id
    assert person.current_org_name == "Basebase"
    assert person.current_role == "Founder"
