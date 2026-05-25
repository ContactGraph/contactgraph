"""Per-(person, source) freshness gate for enrichment.

Prevents re-querying web search providers for contacts that were enriched
recently (within the configurable TTL).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from contactsafe_server.db.models import EnrichmentAttempt


class EnrichmentAttemptTracker:
    def __init__(self, session: AsyncSession, *, ttl_days: int = 30) -> None:
        self._session: AsyncSession = session
        self._ttl: timedelta = timedelta(days=ttl_days)

    async def should_attempt(
        self,
        *,
        person_id: uuid.UUID,
        source_kind: str,
    ) -> bool:
        """Return True if enrichment should be attempted (no recent attempt)."""
        stmt = (
            select(EnrichmentAttempt.last_attempted_at)
            .where(
                EnrichmentAttempt.person_id == person_id,
                EnrichmentAttempt.source_kind == source_kind,
            )
            .limit(1)
        )
        result = await self._session.execute(stmt)
        row: datetime | None = result.scalar_one_or_none()
        if row is None:
            return True
        cutoff: datetime = datetime.now(timezone.utc) - self._ttl
        return row < cutoff

    async def record_attempt(
        self,
        *,
        person_id: uuid.UUID,
        source_kind: str,
        user_id: uuid.UUID | None = None,
        succeeded: bool = True,
        result_count: int = 0,
        error: str | None = None,
    ) -> None:
        """Upsert an enrichment attempt row."""
        stmt = pg_insert(EnrichmentAttempt).values(
            person_id=person_id,
            source_kind=source_kind,
            contributor_user_id=user_id,
            last_attempted_at=func.now(),
            succeeded=succeeded,
            result_count=result_count,
            error=error,
        )
        stmt = stmt.on_conflict_do_update(
            constraint="uq_enrichment_attempt",
            set_={
                "last_attempted_at": stmt.excluded.last_attempted_at,
                "succeeded": stmt.excluded.succeeded,
                "result_count": stmt.excluded.result_count,
                "error": stmt.excluded.error,
                "contributor_user_id": stmt.excluded.contributor_user_id,
            },
        )
        await self._session.execute(stmt)
