"""Outreach logging, recall, and candidate triage.

Two ideas live here.

**Outreach is a log, not a status.** A relationship is a sequence of touches; collapsing it
to "last contacted" throws away the history that makes follow-up possible. Attempts are
appended and only their outcome is mutable.

**Independence is derived, never stored.** Whether someone is an independent practitioner
is computed at query time from data the graph already holds, following the precedent set by
TargetCompaniesService. Storing it would mean a column that silently goes stale every time
enrichment updates an employer.
"""

from __future__ import annotations

import logging
import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import Select, and_, delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from contactsafe_core.contact_schemas import (
    ListOutreachResult,
    LogOutreachResult,
    OutreachAttemptItem,
    OutreachQueueItem,
    OutreachQueueResult,
    PersonListItemSummary,
    PersonListsResult,
    UpdateOutreachResult,
)
from contactsafe_core.enums import OutreachChannel, OutreachQueueFilter, OutreachStatus
from contactsafe_server.db.models import (
    OutreachAttempt,
    Person,
    PersonList,
    PersonListMembership,
    UserPersonObservation,
)

logger: logging.Logger = logging.getLogger(__name__)

VALID_CHANNELS: frozenset[str] = frozenset(c.value for c in OutreachChannel)
VALID_STATUSES: frozenset[str] = frozenset(s.value for s in OutreachStatus)
VALID_FILTERS: frozenset[str] = frozenset(f.value for f in OutreachQueueFilter)

# A status that means "this thread is still open and the ball is in their court".
_AWAITING: frozenset[str] = frozenset({OutreachStatus.SENT.value})

# Words that turn a personal name into a practice name: "Marta Quill Design",
# "Devon Reyes Music". Deliberately short — every addition widens the net, and a false
# positive here mislabels a person, which is worse than missing one.
_PRACTICE_WORDS: frozenset[str] = frozenset(
    {
        "art",
        "arts",
        "atelier",
        "ceramics",
        "design",
        "designs",
        "films",
        "fineart",
        "gallery",
        "jewelry",
        "music",
        "photo",
        "photography",
        "pottery",
        "productions",
        "studio",
        "studios",
        "textiles",
        "workshop",
    }
)

# Tags that describe a practice rather than a job title. Used only as corroboration when
# there is no employer at all — on its own, "designer" says nothing about independence.
_CREATIVE_TAGS: frozenset[str] = frozenset(
    {
        "artist",
        "ceramicist",
        "craftsperson",
        "designer",
        "filmmaker",
        "illustrator",
        "jeweler",
        "maker",
        "musician",
        "painter",
        "performer",
        "photographer",
        "potter",
        "sculptor",
        "writer",
    }
)

_NON_WORD = re.compile(r"[^a-z0-9]+")

# An independent's "employer" is very often their own website. Stripping the URL scaffolding
# lets "www.lenamarsh.com" compare equal to "Lena Marsh" — found by running this against a real
# graph, where it was the single most common miss.
_URL_CHROME = re.compile(r"^(https?://)?(www\.)?|\.(com|net|org|co|io|art|studio|design|photo)(\.[a-z]{2})?/?$")


def _norm(value: str | None) -> str:
    if not value:
        return ""
    return " ".join(_NON_WORD.sub(" ", value.casefold()).split())


def _squash(value: str | None) -> str:
    """Normalized with all separators removed.

    Punctuated initials are the common case that plain tokenizing gets wrong: "A.J. Okonkwo"
    tokenizes to three words and "AJ Okonkwo" to two, so they never compare equal even though
    they are the same person. Comparing the squashed forms catches it, and also collapses
    a personal domain ("lenamarsh.com") onto the name it is built from.
    """
    if not value:
        return ""
    return _NON_WORD.sub("", _strip_url_chrome(value).casefold())


def _strip_url_chrome(value: str) -> str:
    """Reduce a URL-shaped org name to its distinctive part."""
    candidate = value.strip().casefold()
    if "." not in candidate and "/" not in candidate:
        return value
    return _URL_CHROME.sub("", candidate) or value


@dataclass(frozen=True)
class IndependenceVerdict:
    is_independent: bool
    reason: str | None


def assess_independence(
    *,
    canonical_name: str | None,
    org_name: str | None,
    descriptive_tags: list[str] | None,
) -> IndependenceVerdict:
    """Is this person's business essentially themselves?

    Pure and DB-free so it can be tested directly. The signal that carries the most weight
    is the simplest one: when the employer name *is* the person's name, the business is the
    person. That distinguishes an independent maker from a designer employed at a company —
    the distinction that matters for outreach and that a job-title taxonomy cannot make.
    """
    name = _norm(canonical_name)
    org = _norm(org_name)
    tags = {t.casefold().strip() for t in (descriptive_tags or [])}

    if not name:
        return IndependenceVerdict(False, None)

    if org:
        if org == name or _squash(canonical_name) == _squash(org_name):
            return IndependenceVerdict(True, "business name is their own name")

        org_words = org.split()
        name_words = name.split()
        # "Marta Quill" ⊂ "Marta Quill Design" — the personal name, plus a practice word.
        if len(org_words) > len(name_words) and org_words[: len(name_words)] == name_words:
            extra = set(org_words[len(name_words) :])
            if extra & _PRACTICE_WORDS:
                return IndependenceVerdict(True, "own name plus a practice word")
            return IndependenceVerdict(True, "business name starts with their own name")

        # Surname + practice word, without the given name: "Quill Ceramics".
        if len(name_words) > 1 and name_words[-1] in org_words:
            if set(org_words) & _PRACTICE_WORDS:
                return IndependenceVerdict(True, "surname plus a practice word")

        return IndependenceVerdict(False, None)

    # No employer recorded at all. On its own that means nothing — enrichment may simply not
    # have run. Only treat it as a signal when the tags describe a practice.
    if tags & _CREATIVE_TAGS:
        matched = sorted(tags & _CREATIVE_TAGS)[0]
        return IndependenceVerdict(True, f"no employer recorded, tagged {matched}")

    return IndependenceVerdict(False, None)


class OutreachService:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    # --- logging ---------------------------------------------------------------

    async def log_outreach(
        self,
        user_id: uuid.UUID,
        *,
        person_id: uuid.UUID,
        channel: str,
        status: str = OutreachStatus.SENT.value,
        occurred_at: datetime | None = None,
        note: str | None = None,
        next_step_at: datetime | None = None,
    ) -> LogOutreachResult:
        if channel not in VALID_CHANNELS:
            raise ValueError(f"Unknown channel '{channel}'. Expected one of: {sorted(VALID_CHANNELS)}")
        if status not in VALID_STATUSES:
            raise ValueError(f"Unknown status '{status}'. Expected one of: {sorted(VALID_STATUSES)}")

        person: Person | None = (
            await self._db.execute(select(Person).where(Person.id == person_id))
        ).scalar_one_or_none()
        if person is None:
            raise ValueError(f"No person with id {person_id}")

        attempt = OutreachAttempt(
            user_id=user_id,
            person_id=person_id,
            channel=channel,
            status=status,
            occurred_at=occurred_at or datetime.now(UTC),
            note=note,
            next_step_at=next_step_at,
        )
        self._db.add(attempt)
        await self._db.commit()
        await self._db.refresh(attempt)
        return LogOutreachResult(attempt=_to_item(attempt, person.canonical_name))

    async def update_outreach(
        self,
        user_id: uuid.UUID,
        *,
        attempt_id: uuid.UUID,
        status: str | None = None,
        note: str | None = None,
        next_step_at: datetime | None = None,
    ) -> UpdateOutreachResult:
        if status is not None and status not in VALID_STATUSES:
            raise ValueError(f"Unknown status '{status}'. Expected one of: {sorted(VALID_STATUSES)}")

        attempt: OutreachAttempt | None = (
            await self._db.execute(
                select(OutreachAttempt).where(
                    OutreachAttempt.id == attempt_id,
                    OutreachAttempt.user_id == user_id,
                )
            )
        ).scalar_one_or_none()
        if attempt is None:
            raise ValueError(f"No outreach attempt with id {attempt_id}")

        if status is not None:
            attempt.status = status
        if note is not None:
            attempt.note = note
        if next_step_at is not None:
            attempt.next_step_at = next_step_at
        await self._db.commit()
        await self._db.refresh(attempt)

        name: str | None = None
        if attempt.person_id is not None:
            name = (
                await self._db.execute(
                    select(Person.canonical_name).where(Person.id == attempt.person_id)
                )
            ).scalar_one_or_none()
        return UpdateOutreachResult(attempt=_to_item(attempt, name))

    async def list_outreach(
        self,
        user_id: uuid.UUID,
        *,
        person_id: uuid.UUID | None = None,
        limit: int = 100,
    ) -> ListOutreachResult:
        stmt = (
            select(OutreachAttempt, Person.canonical_name)
            .outerjoin(Person, Person.id == OutreachAttempt.person_id)
            .where(OutreachAttempt.user_id == user_id)
            .order_by(OutreachAttempt.occurred_at.desc())
            .limit(max(1, min(limit, 500)))
        )
        if person_id is not None:
            stmt = stmt.where(OutreachAttempt.person_id == person_id)
        rows = (await self._db.execute(stmt)).all()
        return ListOutreachResult(attempts=[_to_item(a, n) for a, n in rows])

    # --- the queue -------------------------------------------------------------

    async def outreach_queue(
        self,
        user_id: uuid.UUID,
        *,
        queue_filter: str = OutreachQueueFilter.UNCONTACTED.value,
        stale_after_days: int = 30,
        person_list_id: uuid.UUID | None = None,
        limit: int = 50,
    ) -> OutreachQueueResult:
        """Answer the four questions that motivated this: who haven't I contacted, who
        owes me a reply, who went quiet, and who did I promise to follow up with."""
        if queue_filter not in VALID_FILTERS:
            raise ValueError(f"Unknown filter '{queue_filter}'. Expected one of: {sorted(VALID_FILTERS)}")

        now = datetime.now(UTC)
        cutoff = now - timedelta(days=max(1, stale_after_days))

        # Per-person rollup of this user's attempts, computed once and joined.
        agg = (
            select(
                OutreachAttempt.person_id.label("person_id"),
                func.count(OutreachAttempt.id).label("attempt_count"),
                func.max(OutreachAttempt.occurred_at).label("last_at"),
                func.min(OutreachAttempt.next_step_at).label("next_at"),
            )
            .where(
                OutreachAttempt.user_id == user_id,
                OutreachAttempt.person_id.is_not(None),
            )
            .group_by(OutreachAttempt.person_id)
            .subquery()
        )

        stmt: Select[tuple[Person, UserPersonObservation, int | None, datetime | None, datetime | None]] = (
            select(Person, UserPersonObservation, agg.c.attempt_count, agg.c.last_at, agg.c.next_at)
            .join(
                UserPersonObservation,
                and_(
                    UserPersonObservation.person_id == Person.id,
                    UserPersonObservation.user_id == user_id,
                ),
            )
            .outerjoin(agg, agg.c.person_id == Person.id)
            # Newsletters and no-reply senders are not outreach targets.
            .where(UserPersonObservation.is_human.is_(True))
            .where(UserPersonObservation.is_broadcast.is_(False))
            .where(UserPersonObservation.is_automated.is_(False))
        )

        if person_list_id is not None:
            stmt = stmt.join(
                PersonListMembership,
                and_(
                    PersonListMembership.person_id == Person.id,
                    PersonListMembership.person_list_id == person_list_id,
                ),
            )

        if queue_filter == OutreachQueueFilter.UNCONTACTED.value:
            stmt = stmt.where(agg.c.person_id.is_(None))
            stmt = stmt.order_by(UserPersonObservation.tie_strength_score.desc().nullslast())
        elif queue_filter == OutreachQueueFilter.AWAITING_REPLY.value:
            stmt = stmt.where(
                agg.c.person_id.is_not(None),
                _latest_status_in(user_id, _AWAITING),
            )
            stmt = stmt.order_by(agg.c.last_at.asc())
        elif queue_filter == OutreachQueueFilter.STALE.value:
            stmt = stmt.where(
                agg.c.last_at.is_not(None),
                agg.c.last_at < cutoff,
                _latest_status_in(user_id, _AWAITING),
            )
            stmt = stmt.order_by(agg.c.last_at.asc())
        else:  # DUE
            stmt = stmt.where(agg.c.next_at.is_not(None), agg.c.next_at <= now)
            stmt = stmt.order_by(agg.c.next_at.asc())

        stmt = stmt.limit(max(1, min(limit, 200)))
        rows = (await self._db.execute(stmt)).all()

        people: list[OutreachQueueItem] = []
        for person, _obs, attempt_count, last_at, next_at in rows:
            verdict = assess_independence(
                canonical_name=person.canonical_name,
                org_name=person.current_org_name,
                descriptive_tags=person.descriptive_tags,
            )
            last_channel, last_status = await self._latest_channel_status(user_id, person.id)
            people.append(
                OutreachQueueItem(
                    person_id=person.id,
                    person_name=person.canonical_name,
                    org_name=person.current_org_name,
                    current_role=person.current_role,
                    is_independent=verdict.is_independent,
                    independent_reason=verdict.reason,
                    last_outreach_at=last_at,
                    last_outreach_channel=last_channel,  # type: ignore[arg-type]
                    last_outreach_status=last_status,  # type: ignore[arg-type]
                    attempt_count=attempt_count or 0,
                    next_step_at=next_at,
                )
            )
        return OutreachQueueResult(filter=queue_filter, people=people)  # type: ignore[arg-type]

    async def _latest_channel_status(
        self, user_id: uuid.UUID, person_id: uuid.UUID
    ) -> tuple[str | None, str | None]:
        row = (
            await self._db.execute(
                select(OutreachAttempt.channel, OutreachAttempt.status)
                .where(
                    OutreachAttempt.user_id == user_id,
                    OutreachAttempt.person_id == person_id,
                )
                .order_by(OutreachAttempt.occurred_at.desc())
                .limit(1)
            )
        ).first()
        if row is None:
            return None, None
        return row[0], row[1]

    # --- candidate lists -------------------------------------------------------

    async def create_person_list(self, user_id: uuid.UUID, *, name: str) -> uuid.UUID:
        cleaned = name.strip()
        if not cleaned:
            raise ValueError("List name cannot be empty")
        existing: PersonList | None = (
            await self._db.execute(
                select(PersonList).where(PersonList.user_id == user_id, PersonList.name == cleaned)
            )
        ).scalar_one_or_none()
        if existing is not None:
            return existing.id
        row = PersonList(user_id=user_id, name=cleaned)
        self._db.add(row)
        await self._db.commit()
        await self._db.refresh(row)
        return row.id

    async def edit_person_list(
        self,
        user_id: uuid.UUID,
        *,
        person_list_id: uuid.UUID,
        add: list[uuid.UUID] | None = None,
        remove: list[uuid.UUID] | None = None,
    ) -> int:
        owned: PersonList | None = (
            await self._db.execute(
                select(PersonList).where(
                    PersonList.id == person_list_id, PersonList.user_id == user_id
                )
            )
        ).scalar_one_or_none()
        if owned is None:
            raise ValueError(f"No person list with id {person_list_id}")

        for person_id in add or []:
            present = (
                await self._db.execute(
                    select(PersonListMembership).where(
                        PersonListMembership.person_list_id == person_list_id,
                        PersonListMembership.person_id == person_id,
                    )
                )
            ).scalar_one_or_none()
            if present is None:
                self._db.add(
                    PersonListMembership(person_list_id=person_list_id, person_id=person_id)
                )
        if remove:
            await self._db.execute(
                delete(PersonListMembership).where(
                    PersonListMembership.person_list_id == person_list_id,
                    PersonListMembership.person_id.in_(remove),
                )
            )
        await self._db.commit()
        count = (
            await self._db.execute(
                select(func.count())
                .select_from(PersonListMembership)
                .where(PersonListMembership.person_list_id == person_list_id)
            )
        ).scalar_one()
        return int(count)

    async def list_person_lists(self, user_id: uuid.UUID) -> PersonListsResult:
        rows = (
            await self._db.execute(
                select(
                    PersonList,
                    func.count(PersonListMembership.person_id),
                )
                .outerjoin(
                    PersonListMembership,
                    PersonListMembership.person_list_id == PersonList.id,
                )
                .where(PersonList.user_id == user_id)
                .group_by(PersonList.id)
                .order_by(PersonList.name)
            )
        ).all()
        return PersonListsResult(
            lists=[
                PersonListItemSummary(person_list_id=pl.id, name=pl.name, member_count=int(n or 0))
                for pl, n in rows
            ]
        )


def _latest_status_in(user_id: uuid.UUID, statuses: frozenset[str]):
    """True when the person's most recent attempt has one of these statuses.

    Expressed as a correlated EXISTS rather than a join so it composes with the aggregate
    subquery above without multiplying rows.
    """
    newer = select(OutreachAttempt.id).where(
        OutreachAttempt.user_id == user_id,
        OutreachAttempt.person_id == Person.id,
    )
    latest = (
        select(OutreachAttempt.status)
        .where(
            OutreachAttempt.user_id == user_id,
            OutreachAttempt.person_id == Person.id,
        )
        .order_by(OutreachAttempt.occurred_at.desc())
        .limit(1)
        .scalar_subquery()
    )
    return and_(newer.exists(), or_(*[latest == s for s in sorted(statuses)]))


def _to_item(attempt: OutreachAttempt, person_name: str | None) -> OutreachAttemptItem:
    return OutreachAttemptItem(
        attempt_id=attempt.id,
        person_id=attempt.person_id,
        person_name=person_name,
        channel=attempt.channel,  # type: ignore[arg-type]
        status=attempt.status,  # type: ignore[arg-type]
        occurred_at=attempt.occurred_at,
        note=attempt.note,
        next_step_at=attempt.next_step_at,
    )
