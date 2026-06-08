#!/usr/bin/env python3
"""Match strong-tie contacts and scrape their LinkedIn profiles via ScrapingDog.

Usage:
  uv run python scripts/scrape_strong_ties.py --user-id <UUID>
  uv run python scripts/scrape_strong_ties.py --user-id <UUID> --run-workers
  uv run python scripts/scrape_strong_ties.py --user-id <UUID> --export close-colleagues.csv
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import uuid
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

_REPO_ROOT: Path = Path(__file__).resolve().parents[3]
os.chdir(_REPO_ROOT)
os.environ.setdefault("APP_ENV", "development")

from contactsafe_core.enums import EnrichmentQueueStatus  # noqa: E402
from contactsafe_server.config import Settings, get_settings  # noqa: E402
from contactsafe_server.db.models import EnrichmentQueueItem, User  # noqa: E402
from contactsafe_server.services.close_colleague_export import (  # noqa: E402
    export_close_colleagues_to_file,
)
from contactsafe_server.services.contact_enrichment_worker import (  # noqa: E402
    ContactEnrichmentWorker,
)
from contactsafe_server.services.enrichment_queue_service import (  # noqa: E402
    EnrichmentQueueService,
)
from contactsafe_server.services.person_profile_recompute import PersonProfileRecompute  # noqa: E402
from contactsafe_server.services.strong_tie_matcher import (  # noqa: E402
    StrongTieMatch,
    count_strong_ties,
    find_strong_ties,
)
from contactsafe_server.services.user_org_observation_service import (  # noqa: E402
    rebuild_user_org_observations,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger: logging.Logger = logging.getLogger(__name__)


async def _resolve_user_id(session: AsyncSession, user_id: uuid.UUID | None, email: str | None) -> uuid.UUID:
    if user_id is not None:
        user: User | None = await session.get(User, user_id)
        if user is None:
            raise ValueError(f"User not found: {user_id}")
        return user.id

    if email is None:
        raise ValueError("Provide --user-id or --user-email")

    result = await session.execute(select(User).where(User.email == email.strip().lower()))
    resolved: User | None = result.scalar_one_or_none()
    if resolved is None:
        raise ValueError(f"User not found for email: {email}")
    return resolved.id


async def _run_workers(
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
    *,
    user_id: uuid.UUID,
    max_items: int,
) -> int:
    processed: int = 0
    queue_service: EnrichmentQueueService

    enriched_person_ids: list[uuid.UUID] = []

    while processed < max_items:
        async with session_factory() as session:
            queue_service = EnrichmentQueueService(session, settings)
            item: EnrichmentQueueItem | None = await queue_service.claim_next_item()
            if item is None:
                break
            if item.trigger_user_id != user_id:
                item.status = EnrichmentQueueStatus.PENDING.value
                await session.commit()
                continue

            worker = ContactEnrichmentWorker(session, settings)
            try:
                await worker.enrich_one(item, skip_org_rebuild=True)
                enriched_person_ids.append(item.person_id)
            except Exception:
                logger.exception("Unrecoverable error on person %s, skipping", item.person_id)
            processed += 1
            logger.info("Processed %d/%d queue items", processed, max_items)

    if enriched_person_ids:
        logger.info("Running post-scrape recompute for %d persons...", len(enriched_person_ids))
        async with session_factory() as session:
            recompute = PersonProfileRecompute(session)
            await recompute.recompute_persons(enriched_person_ids)
            await session.commit()
        try:
            logger.info("Running org-observation rebuild for user %s...", user_id)
            async with session_factory() as session:
                await rebuild_user_org_observations(session, user_id)
                await session.commit()
        except Exception:
            logger.warning(
                "Org-observation rebuild timed out or failed; scrape data is persisted, skipping",
                exc_info=True,
            )

    return processed


async def main(
    *,
    user_id: uuid.UUID | None,
    user_email: str | None,
    limit: int | None,
    skip_enriched: bool,
    dry_run: bool,
    run_workers: bool,
    export_path: str | None,
    max_workers: int,
) -> None:
    settings: Settings = get_settings()
    if not settings.scrapingdog_api_key and run_workers and not dry_run:
        logger.error("SCRAPINGDOG_API_KEY is required when --run-workers is set")
        return

    engine = create_async_engine(
        str(settings.database_url),
        connect_args=settings.database_connect_args,
        pool_pre_ping=True,
    )
    session_factory: async_sessionmaker[AsyncSession] = async_sessionmaker(
        engine,
        expire_on_commit=False,
    )

    async with session_factory() as session:
        resolved_user_id: uuid.UUID = await _resolve_user_id(session, user_id, user_email)
        total: int = await count_strong_ties(
            session,
            resolved_user_id,
            skip_already_scraped=skip_enriched,
        )
        matches: list[StrongTieMatch] = await find_strong_ties(
            session,
            resolved_user_id,
            skip_already_scraped=skip_enriched,
            limit=limit,
        )

    logger.info(
        "Found %d strong-tie matches for user %s (showing %d)",
        total,
        resolved_user_id,
        len(matches),
    )
    for match in matches[:10]:
        logger.info(
            "  %s | %s | tie=%.2f | slug=%s",
            match.canonical_name,
            match.linkedin_url,
            match.tie_strength_score,
            match.linkedin_slug,
        )
    if len(matches) > 10:
        logger.info("  ... and %d more", len(matches) - 10)

    if dry_run:
        logger.info("Dry run complete; no queue items created")
    else:
        async with session_factory() as session:
            queue_service = EnrichmentQueueService(session, settings)
            enqueued: int = await queue_service.enqueue_strong_tie_scrapes(
                user_id=resolved_user_id,
                person_ids=[match.person_id for match in matches],
            )
            await session.commit()
            logger.info("Enqueued %d strong-tie scrape jobs", enqueued)

        if run_workers:
            processed: int = await _run_workers(
                session_factory,
                settings,
                user_id=resolved_user_id,
                max_items=max_workers if max_workers > 0 else len(matches),
            )
            logger.info("Worker loop processed %d queue items", processed)

    if export_path is not None:
        async with session_factory() as session:
            exported: int = await export_close_colleagues_to_file(
                session,
                resolved_user_id,
                export_path,
            )
            logger.info("Exported %d close colleagues to %s", exported, export_path)

    await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Match strong-tie contacts and scrape LinkedIn profiles via ScrapingDog",
    )
    parser.add_argument("--user-id", type=uuid.UUID, default=None)
    parser.add_argument("--user-email", type=str, default=None)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument(
        "--include-already-scraped",
        action="store_true",
        help="Include contacts that already have ScrapingDog employment claims",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--run-workers",
        action="store_true",
        help="Process the enrichment queue inline after enqueueing",
    )
    parser.add_argument(
        "--max-workers",
        type=int,
        default=0,
        help="Max queue items to process when --run-workers is set (0 = all matches)",
    )
    parser.add_argument(
        "--export",
        dest="export_path",
        type=str,
        default=None,
        help="Write close-colleague CSV to this path",
    )
    args = parser.parse_args()
    asyncio.run(
        main(
            user_id=args.user_id,
            user_email=args.user_email,
            limit=args.limit,
            skip_enriched=not args.include_already_scraped,
            dry_run=args.dry_run,
            run_workers=args.run_workers,
            export_path=args.export_path,
            max_workers=args.max_workers,
        )
    )
