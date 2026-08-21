#!/usr/bin/env python3
"""Backfill Layer-2 and Layer-3 ATS detection for orgs with no board token.

Layer-1 detection only recognises an ATS when the org's ``careers_url`` is
itself an ATS host, so orgs behind a vanity careers domain were left tokenless
and fell back to the aggregator feed. This script retries the backlog with:

* Layer 2 — fetch the careers page and look through it (fixes mercury.com/jobs).
* Layer 3 — probe candidate board tokens against the ATS APIs, for careers sites
  that render listings client-side and never name their ATS in the HTML. This is
  what HubSpot needs: hubspot.com/careers mentions no ATS at all, and their real
  Greenhouse board is ``hubspotjobs``. Pass --no-probe to skip it.

Every candidate costs outbound HTTP requests to third-party sites, so this is
deliberately rate-limited and resumable. Detection never raises — orgs that
cannot be resolved are left as they are and can be retried later.

Usage (from the repo root, with SCRIPT=packages/server/scripts/backfill_ats_detection.py):
  # see what would change, no writes
  uv run --package contactsafe-server python $SCRIPT --limit 50 --dry-run

  # real run, conservative concurrency
  uv run --package contactsafe-server python $SCRIPT --concurrency 4
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

os.environ.setdefault("APP_ENV", "development")

from contactsafe_server.config import get_settings  # noqa: E402
from contactsafe_server.db.connection import get_engine  # noqa: E402
from contactsafe_server.db.models import Org  # noqa: E402
from contactsafe_server.services.ats_detection import (  # noqa: E402
    AtsDetectionResult,
    detect_ats_by_probe,
    detect_ats_from_page,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger: logging.Logger = logging.getLogger(__name__)


def _candidate_query():
    """Orgs with a careers URL but no ATS token yet."""
    return (
        select(Org)
        .where(
            Org.careers_url.is_not(None),
            Org.careers_url != "",
            or_(Org.ats_board_token.is_(None), Org.ats_board_token == ""),
        )
        .order_by(Org.id)
    )


async def _detect_one(
    org_id: str,
    canonical_name: str | None,
    careers_url: str | None,
    semaphore: asyncio.Semaphore,
    delay_seconds: float,
    use_probe: bool,
) -> tuple[str, AtsDetectionResult]:
    async with semaphore:
        result = AtsDetectionResult(provider=None, board_token=None)
        if careers_url:
            result = await detect_ats_from_page(careers_url)
        # Layer 3 only where reading the page found nothing — client-rendered
        # careers sites (HubSpot) never name their ATS in the HTML.
        if result.provider is None and use_probe:
            result = await detect_ats_by_probe(canonical_name, careers_url)
        # Space out requests so a burst of same-host pages stays polite.
        if delay_seconds > 0:
            await asyncio.sleep(delay_seconds)
        return org_id, result


async def backfill(
    *,
    batch_size: int,
    limit: int | None,
    dry_run: bool,
    concurrency: int,
    delay_seconds: float,
    use_probe: bool,
) -> None:
    get_settings()
    engine = get_engine()
    Session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    semaphore = asyncio.Semaphore(concurrency)

    async with Session() as db:
        pending: int = int(
            (
                await db.execute(
                    select(func.count()).select_from(_candidate_query().subquery()),
                )
            ).scalar_one(),
        )
    logger.info(
        "candidates=%d limit=%s concurrency=%d probe=%s dry_run=%s",
        pending,
        limit,
        concurrency,
        use_probe,
        dry_run,
    )

    processed: int = 0
    detected: int = 0
    offset: int = 0
    by_provider: dict[str, int] = {}

    while True:
        if limit is not None and processed >= limit:
            break
        take: int = batch_size
        if limit is not None:
            take = min(take, limit - processed)

        async with Session() as db:
            batch: list[Org] = list(
                (await db.execute(_candidate_query().offset(offset).limit(take)))
                .scalars()
                .all(),
            )
            if not batch:
                break

            results = await asyncio.gather(
                *(
                    _detect_one(
                        str(org.id),
                        org.canonical_name,
                        org.careers_url,
                        semaphore,
                        delay_seconds,
                        use_probe,
                    )
                    for org in batch
                ),
            )
            resolved: dict[str, AtsDetectionResult] = dict(results)

            batch_detected: int = 0
            for org in batch:
                result: AtsDetectionResult | None = resolved.get(str(org.id))
                if result is None or result.provider is None:
                    continue
                logger.info(
                    "detected org=%s url=%s -> %s/%s",
                    org.canonical_name or org.id,
                    org.careers_url,
                    result.provider,
                    result.board_token,
                )
                by_provider[result.provider] = by_provider.get(result.provider, 0) + 1
                batch_detected += 1
                if not dry_run:
                    org.ats_provider = result.provider
                    org.ats_board_token = result.board_token

            if not dry_run:
                await db.commit()

            processed += len(batch)
            detected += batch_detected
            logger.info(
                "processed=%d/%d detected=%d (this batch %d/%d)",
                processed,
                pending,
                detected,
                batch_detected,
                len(batch),
            )

            # Detected rows leave the candidate set once written, so only skip
            # past the ones we could not resolve. On a dry run nothing is
            # written, so the whole batch must be skipped instead.
            offset += len(batch) if dry_run else len(batch) - batch_detected
            if len(batch) < take:
                break

    logger.info(
        "done processed=%d detected=%d dry_run=%s by_provider=%s",
        processed,
        detected,
        dry_run,
        by_provider or "{}",
    )
    await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch-size", type=int, default=50)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--concurrency",
        type=int,
        default=4,
        help="Simultaneous careers-page fetches (default 4)",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=0.25,
        help="Seconds to pause after each fetch (default 0.25)",
    )
    parser.add_argument(
        "--no-probe",
        action="store_true",
        help="Skip Layer-3 token probing (page detection only)",
    )
    args = parser.parse_args()
    asyncio.run(
        backfill(
            batch_size=args.batch_size,
            limit=args.limit,
            dry_run=args.dry_run,
            concurrency=args.concurrency,
            delay_seconds=args.delay,
            use_probe=not args.no_probe,
        ),
    )


if __name__ == "__main__":
    main()
