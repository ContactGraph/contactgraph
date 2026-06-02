"""Rebuild per-user org observations from current employment claims."""

import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from contactsafe_server.db.models import (
    EmploymentClaim,
    UserOrgObservation,
    UserPersonObservation,
)


async def rebuild_user_org_observations(db: AsyncSession, user_id: uuid.UUID) -> None:
    result = await db.execute(
        select(
            EmploymentClaim.org_id,
            EmploymentClaim.person_id,
            UserPersonObservation.email_count,
            UserPersonObservation.last_observed_at,
            UserPersonObservation.tie_strength_score,
        )
        .join(
            UserPersonObservation,
            (UserPersonObservation.person_id == EmploymentClaim.person_id)
            & (UserPersonObservation.user_id == user_id),
        )
        .where(EmploymentClaim.is_current.is_(True))
    )
    rows = result.all()

    by_org: dict[uuid.UUID, dict[str, object]] = {}
    for org_id, person_id, email_count, last_at, tie in rows:
        bucket = by_org.setdefault(org_id, {
            "person_ids": set(),
            "email_count": 0,
            "tie": 0.0,
            "last_at": None,
        })
        pid_set: set[uuid.UUID] = bucket["person_ids"]  # type: ignore[assignment]
        pid_set.add(person_id)
        bucket["email_count"] = int(bucket["email_count"]) + email_count  # type: ignore[arg-type]
        bucket["tie"] = max(float(bucket["tie"]), tie)  # type: ignore[arg-type]
        prev: datetime | None = bucket["last_at"]  # type: ignore[assignment]
        if last_at is not None and (prev is None or last_at > prev):
            bucket["last_at"] = last_at

    for org_id, bucket in by_org.items():
        pid_set = bucket["person_ids"]  # type: ignore[assignment]
        stmt = pg_insert(UserOrgObservation).values(
            user_id=user_id,
            org_id=org_id,
            associated_person_ids=sorted(pid_set),
            total_email_count=int(bucket["email_count"]),  # type: ignore[arg-type]
            last_interaction_at=bucket["last_at"],  # type: ignore[arg-type]
            tie_strength_score=float(bucket["tie"]),  # type: ignore[arg-type]
            relationship_types=["contact"],
        )
        stmt = stmt.on_conflict_do_update(
            constraint="pk_user_org_obs",
            set_={
                "associated_person_ids": stmt.excluded.associated_person_ids,
                "total_email_count": stmt.excluded.total_email_count,
                "last_interaction_at": stmt.excluded.last_interaction_at,
                "tie_strength_score": stmt.excluded.tie_strength_score,
                "updated_at": stmt.excluded.updated_at,
            },
        )
        await db.execute(stmt)
    await db.flush()
