"""Tests for outreach logging, the queue filters, and independence triage."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from contactsafe_server.db.models import (
    Base,
    OutreachAttempt,
    Person,
    User,
    UserPersonObservation,
)
from contactsafe_server.services.outreach_service import (
    OutreachService,
    assess_independence,
)


@pytest.fixture(autouse=True)
async def _setup_tables(db_engine):
    async with db_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def _user(db: AsyncSession) -> User:
    user = User(id=uuid.uuid4(), email=f"u{uuid.uuid4().hex[:8]}@example.com")
    db.add(user)
    await db.flush()
    return user


async def _person(
    db: AsyncSession,
    user: User,
    name: str,
    *,
    org: str | None = None,
    tags: list[str] | None = None,
    tie: float = 0.5,
    is_human: bool = True,
) -> Person:
    person = Person(id=uuid.uuid4(), canonical_name=name, current_org_name=org)
    if tags is not None:
        person.descriptive_tags = tags
    db.add(person)
    await db.flush()
    db.add(
        UserPersonObservation(
            user_id=user.id,
            person_id=person.id,
            tie_strength_score=tie,
            is_human=is_human,
            is_broadcast=False,
            is_automated=False,
        )
    )
    await db.flush()
    return person


# --- independence heuristic (pure, no DB) ------------------------------------------


class TestAssessIndependence:
    def test_org_name_equals_person_name(self) -> None:
        v = assess_independence(
            canonical_name="Rowan Vale", org_name="Rowan Vale", descriptive_tags=None
        )
        assert v.is_independent
        assert v.reason is not None

    def test_own_name_plus_practice_word(self) -> None:
        v = assess_independence(
            canonical_name="Devon Reyes", org_name="Devon Reyes Music", descriptive_tags=None
        )
        assert v.is_independent

    def test_surname_plus_practice_word(self) -> None:
        v = assess_independence(
            canonical_name="Marta Quill", org_name="Quill Ceramics", descriptive_tags=None
        )
        assert v.is_independent

    def test_employed_creative_is_not_independent(self) -> None:
        """The distinction the whole feature exists for: a designer at a company is not
        an independent maker, even though both carry creative tags."""
        v = assess_independence(
            canonical_name="Priya Nandor", org_name="Northwind Systems", descriptive_tags=["designer"]
        )
        assert not v.is_independent
        assert v.reason is None

    def test_no_employer_with_creative_tag(self) -> None:
        v = assess_independence(
            canonical_name="Kit Sorrell", org_name=None, descriptive_tags=["musician", "artist"]
        )
        assert v.is_independent

    def test_no_employer_no_tags_is_not_a_signal(self) -> None:
        """Absent enrichment is not evidence of independence."""
        v = assess_independence(canonical_name="Jane Doe", org_name=None, descriptive_tags=[])
        assert not v.is_independent

    def test_case_and_punctuation_insensitive(self) -> None:
        v = assess_independence(
            canonical_name="A.J. Okonkwo", org_name="AJ  OKONKWO", descriptive_tags=None
        )
        assert v.is_independent

    def test_empty_name_is_not_independent(self) -> None:
        v = assess_independence(canonical_name=None, org_name="Anything", descriptive_tags=None)
        assert not v.is_independent

    def test_personal_domain_as_employer(self) -> None:
        """Independents routinely list their own website as their org. Found by running
        this against a real graph, where it was the most common miss."""
        v = assess_independence(
            canonical_name="Lena Marsh", org_name="www.lenamarsh.com", descriptive_tags=None
        )
        assert v.is_independent

    def test_company_domain_is_not_the_person(self) -> None:
        v = assess_independence(
            canonical_name="Priya Nandor", org_name="northwindsystems.com", descriptive_tags=["designer"]
        )
        assert not v.is_independent


# --- logging -----------------------------------------------------------------------


class TestLogOutreach:
    async def test_log_and_list(self, db_session: AsyncSession) -> None:
        user = await _user(db_session)
        person = await _person(db_session, user, "Marta Quill", org="Marta Quill Design")
        svc = OutreachService(db_session)

        result = await svc.log_outreach(
            user.id, person_id=person.id, channel="dm_instagram", note="asked about the booth"
        )
        assert result.attempt is not None
        assert result.attempt.channel == "dm_instagram"
        assert result.attempt.status == "sent"
        assert result.attempt.person_name == "Marta Quill"

        listed = await svc.list_outreach(user.id, person_id=person.id)
        assert len(listed.attempts) == 1

    async def test_many_attempts_per_person_are_kept(self, db_session: AsyncSession) -> None:
        """Outreach is a log. A second attempt must not overwrite the first."""
        user = await _user(db_session)
        person = await _person(db_session, user, "AJ Okonkwo")
        svc = OutreachService(db_session)
        await svc.log_outreach(user.id, person_id=person.id, channel="email")
        await svc.log_outreach(user.id, person_id=person.id, channel="text_sms")
        listed = await svc.list_outreach(user.id, person_id=person.id)
        assert len(listed.attempts) == 2

    async def test_rejects_unknown_channel(self, db_session: AsyncSession) -> None:
        user = await _user(db_session)
        person = await _person(db_session, user, "Someone")
        svc = OutreachService(db_session)
        with pytest.raises(ValueError, match="Unknown channel"):
            await svc.log_outreach(user.id, person_id=person.id, channel="carrier_pigeon")

    async def test_rejects_unknown_person(self, db_session: AsyncSession) -> None:
        user = await _user(db_session)
        svc = OutreachService(db_session)
        with pytest.raises(ValueError, match="No person"):
            await svc.log_outreach(user.id, person_id=uuid.uuid4(), channel="email")

    async def test_update_status_to_replied(self, db_session: AsyncSession) -> None:
        user = await _user(db_session)
        person = await _person(db_session, user, "Lena Marsh")
        svc = OutreachService(db_session)
        logged = await svc.log_outreach(user.id, person_id=person.id, channel="email")
        assert logged.attempt is not None

        updated = await svc.update_outreach(
            user.id, attempt_id=logged.attempt.attempt_id, status="replied"
        )
        assert updated.attempt is not None
        assert updated.attempt.status == "replied"

    async def test_cannot_update_another_users_attempt(self, db_session: AsyncSession) -> None:
        owner = await _user(db_session)
        other = await _user(db_session)
        person = await _person(db_session, owner, "Private Person")
        svc = OutreachService(db_session)
        logged = await svc.log_outreach(owner.id, person_id=person.id, channel="email")
        assert logged.attempt is not None
        with pytest.raises(ValueError, match="No outreach attempt"):
            await svc.update_outreach(
                other.id, attempt_id=logged.attempt.attempt_id, status="replied"
            )


# --- the queue ---------------------------------------------------------------------


class TestOutreachQueue:
    async def test_uncontacted_excludes_people_already_contacted(
        self, db_session: AsyncSession
    ) -> None:
        user = await _user(db_session)
        contacted = await _person(db_session, user, "Contacted Person")
        await _person(db_session, user, "Fresh Person")
        svc = OutreachService(db_session)
        await svc.log_outreach(user.id, person_id=contacted.id, channel="email")

        result = await svc.outreach_queue(user.id, queue_filter="uncontacted")
        names = {p.person_name for p in result.people}
        assert "Fresh Person" in names
        assert "Contacted Person" not in names

    async def test_awaiting_reply_drops_people_who_replied(
        self, db_session: AsyncSession
    ) -> None:
        user = await _user(db_session)
        waiting = await _person(db_session, user, "Still Waiting")
        answered = await _person(db_session, user, "Already Replied")
        svc = OutreachService(db_session)
        await svc.log_outreach(user.id, person_id=waiting.id, channel="email")
        logged = await svc.log_outreach(user.id, person_id=answered.id, channel="email")
        assert logged.attempt is not None
        await svc.update_outreach(user.id, attempt_id=logged.attempt.attempt_id, status="replied")

        result = await svc.outreach_queue(user.id, queue_filter="awaiting_reply")
        names = {p.person_name for p in result.people}
        assert "Still Waiting" in names
        assert "Already Replied" not in names

    async def test_stale_uses_the_cutoff(self, db_session: AsyncSession) -> None:
        user = await _user(db_session)
        old = await _person(db_session, user, "Went Quiet")
        recent = await _person(db_session, user, "Just Messaged")
        svc = OutreachService(db_session)
        await svc.log_outreach(
            user.id,
            person_id=old.id,
            channel="email",
            occurred_at=datetime.now(UTC) - timedelta(days=90),
        )
        await svc.log_outreach(user.id, person_id=recent.id, channel="email")

        result = await svc.outreach_queue(user.id, queue_filter="stale", stale_after_days=30)
        names = {p.person_name for p in result.people}
        assert "Went Quiet" in names
        assert "Just Messaged" not in names

    async def test_due_surfaces_past_next_step(self, db_session: AsyncSession) -> None:
        user = await _user(db_session)
        due = await _person(db_session, user, "Follow Up Now")
        later = await _person(db_session, user, "Follow Up Later")
        svc = OutreachService(db_session)
        await svc.log_outreach(
            user.id,
            person_id=due.id,
            channel="email",
            next_step_at=datetime.now(UTC) - timedelta(days=1),
        )
        await svc.log_outreach(
            user.id,
            person_id=later.id,
            channel="email",
            next_step_at=datetime.now(UTC) + timedelta(days=7),
        )

        result = await svc.outreach_queue(user.id, queue_filter="due")
        names = {p.person_name for p in result.people}
        assert "Follow Up Now" in names
        assert "Follow Up Later" not in names

    async def test_queue_carries_the_independence_verdict(
        self, db_session: AsyncSession
    ) -> None:
        user = await _user(db_session)
        await _person(db_session, user, "Rowan Vale", org="Rowan Vale")
        await _person(db_session, user, "Priya Nandor", org="Northwind Systems", tags=["designer"])
        svc = OutreachService(db_session)

        result = await svc.outreach_queue(user.id, queue_filter="uncontacted")
        verdicts = {p.person_name: p.is_independent for p in result.people}
        assert verdicts["Rowan Vale"] is True
        assert verdicts["Priya Nandor"] is False

    async def test_queue_is_scoped_to_the_user(self, db_session: AsyncSession) -> None:
        owner = await _user(db_session)
        stranger = await _user(db_session)
        await _person(db_session, owner, "Owner Contact")
        svc = OutreachService(db_session)
        result = await svc.outreach_queue(stranger.id, queue_filter="uncontacted")
        assert result.people == []

    async def test_rejects_unknown_filter(self, db_session: AsyncSession) -> None:
        user = await _user(db_session)
        svc = OutreachService(db_session)
        with pytest.raises(ValueError, match="Unknown filter"):
            await svc.outreach_queue(user.id, queue_filter="everyone")


# --- candidate lists ---------------------------------------------------------------


class TestPersonLists:
    async def test_create_add_remove(self, db_session: AsyncSession) -> None:
        user = await _user(db_session)
        a = await _person(db_session, user, "Person A")
        b = await _person(db_session, user, "Person B")
        svc = OutreachService(db_session)

        list_id = await svc.create_person_list(user.id, name="Maker candidates")
        assert await svc.edit_person_list(user.id, person_list_id=list_id, add=[a.id, b.id]) == 2
        assert await svc.edit_person_list(user.id, person_list_id=list_id, remove=[a.id]) == 1

        lists = await svc.list_person_lists(user.id)
        assert lists.lists[0].name == "Maker candidates"
        assert lists.lists[0].member_count == 1

    async def test_create_is_idempotent_by_name(self, db_session: AsyncSession) -> None:
        user = await _user(db_session)
        svc = OutreachService(db_session)
        first = await svc.create_person_list(user.id, name="Dupe")
        second = await svc.create_person_list(user.id, name="Dupe")
        assert first == second

    async def test_cannot_edit_another_users_list(self, db_session: AsyncSession) -> None:
        owner = await _user(db_session)
        other = await _user(db_session)
        svc = OutreachService(db_session)
        list_id = await svc.create_person_list(owner.id, name="Private")
        with pytest.raises(ValueError, match="No person list"):
            await svc.edit_person_list(other.id, person_list_id=list_id, add=[])

    async def test_queue_can_filter_to_a_list(self, db_session: AsyncSession) -> None:
        user = await _user(db_session)
        inside = await _person(db_session, user, "On The List")
        await _person(db_session, user, "Not On The List")
        svc = OutreachService(db_session)
        list_id = await svc.create_person_list(user.id, name="Shortlist")
        await svc.edit_person_list(user.id, person_list_id=list_id, add=[inside.id])

        result = await svc.outreach_queue(
            user.id, queue_filter="uncontacted", person_list_id=list_id
        )
        assert [p.person_name for p in result.people] == ["On The List"]


# --- the regression that matters ---------------------------------------------------


class TestOutreachSurvivesPersonMerge:
    async def test_attempts_move_to_the_survivor(self, db_session: AsyncSession) -> None:
        """PersonDedupService._merge_person hard-deletes the losing Person row. Outreach is
        user-authored and cannot be recomputed from a re-sync, so losing it here would be
        silent, permanent data loss during a routine dedup."""
        from contactsafe_server.services.person_dedup_service import PersonDedupService

        user = await _user(db_session)
        survivor = await _person(db_session, user, "Jane Smith")
        duplicate = await _person(db_session, user, "Jane Smith")
        svc = OutreachService(db_session)
        await svc.log_outreach(user.id, person_id=duplicate.id, channel="dm_linkedin")
        await svc.log_outreach(user.id, person_id=survivor.id, channel="email")

        dedup = PersonDedupService(db_session)
        await dedup._merge_person(survivor=survivor, duplicate=duplicate)
        await db_session.flush()

        remaining = (
            await db_session.execute(
                OutreachAttempt.__table__.select().where(
                    OutreachAttempt.__table__.c.user_id == user.id
                )
            )
        ).all()
        assert len(remaining) == 2, "no attempt may be lost in a merge"
        assert all(r.person_id == survivor.id for r in remaining), (
            "every attempt must point at the survivor"
        )
