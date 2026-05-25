"""Typed helpers for writing claims with idempotent upserts.

Each helper uses INSERT ... ON CONFLICT DO UPDATE so that re-syncing the same
source just bumps ``observed_at`` and updates confidence/evidence — never
creates duplicate rows.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from contactsafe_server.db.models import (
    EmploymentClaim,
    OrgAttributeClaim,
    PersonAttributeClaim,
    RelationshipClaim,
)


async def record_employment(
    session: AsyncSession,
    *,
    person_id: uuid.UUID,
    org_id: uuid.UUID,
    role_title: str | None = None,
    is_current: bool = True,
    contributor_user_id: uuid.UUID | None = None,
    contributor_source_kind: str,
    contributor_source_id: uuid.UUID | None = None,
    confidence: float = 0.7,
    evidence: dict[str, object] | None = None,
) -> None:
    stmt = pg_insert(EmploymentClaim).values(
        person_id=person_id,
        org_id=org_id,
        role_title=role_title,
        is_current=is_current,
        contributor_user_id=contributor_user_id,
        contributor_source_kind=contributor_source_kind,
        contributor_source_id=contributor_source_id,
        confidence=confidence,
        evidence=evidence,
        observed_at=func.now(),
    )
    stmt = stmt.on_conflict_do_update(
        constraint="uq_employment_claim",
        set_={
            "role_title": stmt.excluded.role_title,
            "is_current": stmt.excluded.is_current,
            "observed_at": stmt.excluded.observed_at,
            "confidence": func.greatest(EmploymentClaim.confidence, stmt.excluded.confidence),
            "evidence": stmt.excluded.evidence,
        },
    )
    await session.execute(stmt)


async def record_relationship(
    session: AsyncSession,
    *,
    person_a_id: uuid.UUID,
    person_b_id: uuid.UUID,
    kind: str = "co_thread",
    observed_count: int = 1,
    contributor_user_id: uuid.UUID | None = None,
    contributor_source_kind: str = "gmail",
    last_seen_together_at: datetime | None = None,
    evidence: dict[str, object] | None = None,
) -> None:
    a_id: uuid.UUID = min(person_a_id, person_b_id)
    b_id: uuid.UUID = max(person_a_id, person_b_id)

    stmt = pg_insert(RelationshipClaim).values(
        person_a_id=a_id,
        person_b_id=b_id,
        kind=kind,
        observed_count=observed_count,
        contributor_user_id=contributor_user_id,
        contributor_source_kind=contributor_source_kind,
        last_seen_together_at=last_seen_together_at,
        observed_at=func.now(),
        evidence=evidence,
    )
    stmt = stmt.on_conflict_do_update(
        constraint="uq_relationship_claim",
        set_={
            "observed_count": RelationshipClaim.observed_count + stmt.excluded.observed_count,
            "observed_at": stmt.excluded.observed_at,
            "last_seen_together_at": func.greatest(
                RelationshipClaim.last_seen_together_at,
                stmt.excluded.last_seen_together_at,
            ),
            "evidence": stmt.excluded.evidence,
        },
    )
    await session.execute(stmt)


async def record_person_attribute(
    session: AsyncSession,
    *,
    person_id: uuid.UUID,
    kind: str,
    value: str,
    contributor_user_id: uuid.UUID | None = None,
    contributor_source_kind: str,
    contributor_source_id: uuid.UUID | None = None,
    confidence: float = 0.7,
    evidence: dict[str, object] | None = None,
) -> None:
    stmt = pg_insert(PersonAttributeClaim).values(
        person_id=person_id,
        kind=kind,
        value=value,
        contributor_user_id=contributor_user_id,
        contributor_source_kind=contributor_source_kind,
        contributor_source_id=contributor_source_id,
        confidence=confidence,
        evidence=evidence,
        observed_at=func.now(),
    )
    stmt = stmt.on_conflict_do_update(
        constraint="uq_person_attr_claim",
        set_={
            "observed_at": stmt.excluded.observed_at,
            "confidence": func.greatest(PersonAttributeClaim.confidence, stmt.excluded.confidence),
            "evidence": stmt.excluded.evidence,
        },
    )
    await session.execute(stmt)


async def record_org_attribute(
    session: AsyncSession,
    *,
    org_id: uuid.UUID,
    kind: str,
    value: str,
    contributor_user_id: uuid.UUID | None = None,
    contributor_source_kind: str,
    contributor_source_id: uuid.UUID | None = None,
    confidence: float = 0.7,
    evidence: dict[str, object] | None = None,
) -> None:
    stmt = pg_insert(OrgAttributeClaim).values(
        org_id=org_id,
        kind=kind,
        value=value,
        contributor_user_id=contributor_user_id,
        contributor_source_kind=contributor_source_kind,
        contributor_source_id=contributor_source_id,
        confidence=confidence,
        evidence=evidence,
        observed_at=func.now(),
    )
    stmt = stmt.on_conflict_do_update(
        constraint="uq_org_attr_claim",
        set_={
            "observed_at": stmt.excluded.observed_at,
            "confidence": func.greatest(OrgAttributeClaim.confidence, stmt.excluded.confidence),
            "evidence": stmt.excluded.evidence,
        },
    )
    await session.execute(stmt)
