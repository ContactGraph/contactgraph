#!/usr/bin/env python3
"""Backfill mechanical seniority_level + geocode on org_jobs.

Usage:
  uv run --package contactsafe-server python packages/server/scripts/backfill_job_attributes.py
  uv run --package contactsafe-server python packages/server/scripts/backfill_job_attributes.py --limit 500 --dry-run
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

os.environ.setdefault("APP_ENV", "development")

from contactsafe_server.config import get_settings  # noqa: E402
from contactsafe_server.db.connection import get_engine  # noqa: E402
from contactsafe_server.db.models import OrgJob  # noqa: E402
from contactsafe_server.services.job_attributes import apply_job_attributes  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger: logging.Logger = logging.getLogger(__name__)


async def backfill(
    *,
    batch_size: int,
    limit: int | None,
    dry_run: bool,
    only_missing: bool,
) -> None:
    get_settings()
    engine = get_engine()
    Session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    processed: int = 0
    offset: int = 0
    while True:
        if limit is not None and processed >= limit:
            break
        take: int = batch_size
        if limit is not None:
            take = min(take, limit - processed)

        async with Session() as db:
            query = select(OrgJob).order_by(OrgJob.created_at.desc()).offset(offset).limit(take)
            if only_missing:
                query = (
                    select(OrgJob)
                    .where(
                        (OrgJob.seniority_level.is_(None))
                        | (OrgJob.location_normalized.is_(None)),
                    )
                    .order_by(OrgJob.created_at.desc())
                    .limit(take)
                )
            jobs: list[OrgJob] = list((await db.execute(query)).scalars().all())
            if not jobs:
                break

            for job in jobs:
                apply_job_attributes(job)
            if not dry_run:
                await db.commit()
            processed += len(jobs)
            logger.info(
                "processed=%d batch=%d dry_run=%s sample=%s level=%s geo=%s",
                processed,
                len(jobs),
                dry_run,
                jobs[0].title[:60],
                jobs[0].seniority_level,
                jobs[0].location_normalized,
            )
            if only_missing:
                # No offset advance — missing rows disappear after update.
                continue
            offset += len(jobs)
            if len(jobs) < take:
                break

    async with Session() as db:
        total: int = int(
            (await db.execute(select(func.count()).select_from(OrgJob))).scalar_one(),
        )
        with_level: int = int(
            (
                await db.execute(
                    select(func.count()).select_from(OrgJob).where(
                        OrgJob.seniority_level.is_not(None),
                    ),
                )
            ).scalar_one(),
        )
        with_geo: int = int(
            (
                await db.execute(
                    select(func.count()).select_from(OrgJob).where(
                        OrgJob.location_lat.is_not(None),
                    ),
                )
            ).scalar_one(),
        )
        logger.info(
            "done processed=%d total_jobs=%d with_seniority=%d with_geocode=%d",
            processed,
            total,
            with_level,
            with_geo,
        )

    await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch-size", type=int, default=200)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--all",
        action="store_true",
        help="Recompute all jobs (default: only rows missing attributes)",
    )
    args = parser.parse_args()
    asyncio.run(
        backfill(
            batch_size=args.batch_size,
            limit=args.limit,
            dry_run=args.dry_run,
            only_missing=not args.all,
        ),
    )


if __name__ == "__main__":
    main()
