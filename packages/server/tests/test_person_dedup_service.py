"""Tests for PersonDedupService."""

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from contactsafe_server.db.models import (
    Base,
    Person,
    PersonAlias,
    User,
    UserPersonObservation,
)
from contactsafe_server.services.person_dedup_service import PersonDedupService


@pytest.fixture(autouse=True)
async def _setup_tables(db_engine):
    async with db_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def test_dedup_merges_same_name_and_adds_tie_strength(
    db_session: AsyncSession,
) -> None:
    user: User = User(email=f"dedup-{uuid.uuid4()}@example.com")
    db_session.add(user)
    await db_session.flush()

    email_person: Person = Person(
        canonical_name="Heather Hughes",
        primary_email="heatherehughes@gmail.com",
    )
    phone_person: Person = Person(
        canonical_name="Heather Hughes",
        phone_numbers=["510-393-4698"],
    )
    db_session.add_all([email_person, phone_person])
    await db_session.flush()

    db_session.add_all(
        [
            PersonAlias(
                person_id=email_person.id,
                kind="email",
                value="heatherehughes@gmail.com",
            ),
            PersonAlias(
                person_id=phone_person.id,
                kind="phone",
                value="510-393-4698",
            ),
            UserPersonObservation(
                user_id=user.id,
                person_id=email_person.id,
                tie_strength_score=0.4,
                relationship_types=["gmail"],
            ),
            UserPersonObservation(
                user_id=user.id,
                person_id=phone_person.id,
                tie_strength_score=0.5,
                relationship_types=["phone_contacts_upload"],
            ),
        ]
    )
    await db_session.flush()

    service: PersonDedupService = PersonDedupService(db_session)
    result = await service.dedup_for_user(user.id)
    await db_session.flush()

    assert result.groups_merged == 1
    assert result.persons_removed == 1

    survivors: list[Person] = list(
        (await db_session.execute(select(Person))).scalars().all()
    )
    assert len(survivors) == 1
    survivor: Person = survivors[0]
    assert survivor.primary_email == "heatherehughes@gmail.com"
    assert "510-393-4698" in survivor.phone_numbers

    obs: UserPersonObservation | None = await db_session.get(
        UserPersonObservation,
        (user.id, survivor.id),
    )
    assert obs is not None
    assert obs.tie_strength_score == pytest.approx(0.9)
    assert set(obs.relationship_types) == {"gmail", "phone_contacts_upload"}

    alias_kinds: set[str] = {
        alias.kind
        for alias in (
            await db_session.execute(
                select(PersonAlias).where(PersonAlias.person_id == survivor.id)
            )
        ).scalars().all()
    }
    assert alias_kinds == {"email", "phone"}


async def test_dedup_keeps_distinct_names(db_session: AsyncSession) -> None:
    user: User = User(email=f"dedup-distinct-{uuid.uuid4()}@example.com")
    db_session.add(user)
    await db_session.flush()

    alice: Person = Person(canonical_name="Alice Smith")
    bob: Person = Person(canonical_name="Bob Jones")
    db_session.add_all([alice, bob])
    await db_session.flush()
    db_session.add_all(
        [
            UserPersonObservation(user_id=user.id, person_id=alice.id),
            UserPersonObservation(user_id=user.id, person_id=bob.id),
        ]
    )
    await db_session.flush()

    service: PersonDedupService = PersonDedupService(db_session)
    result = await service.dedup_for_user(user.id)

    assert result.groups_merged == 0
    assert result.persons_removed == 0
    assert len(list((await db_session.execute(select(Person))).scalars().all())) == 2
