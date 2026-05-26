#!/usr/bin/env python3
"""Backfill descriptive_tags on persons that have empty tags.

Runs the LLM enrichment prompt in batches to populate Person.descriptive_tags
for contacts that were ingested before the open-vocabulary tagging system.

Usage:
  uv run python scripts/backfill_descriptive_tags.py
  uv run python scripts/backfill_descriptive_tags.py --batch-size 30 --limit 500 --dry-run
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
from typing import cast

import httpx
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

os.environ.setdefault("APP_ENV", "development")

from contactsafe_server.config import get_settings  # noqa: E402
from contactsafe_server.db.models import Person, PersonAttributeClaim  # noqa: E402
from contactsafe_server.services.claim_writer import record_person_attribute  # noqa: E402
from contactsafe_server.services.person_profile_recompute import PersonProfileRecompute  # noqa: E402
from contactsafe_server.services.openai_json import content_from_chat_completion, parse_json_object  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger: logging.Logger = logging.getLogger(__name__)

BACKFILL_PROMPT: str = (
    "For each contact, produce descriptive_tags: 3–8 lowercase tags describing what "
    "this person does, their industry, and professional identity. Be broad and generous — "
    "over-tagging is better than under-tagging. "
    "Examples: investor, angel, vc, venture-capital, founder, teacher, professor, "
    "artist, journalist, nonprofit, healthcare, real-estate, government, engineer, "
    "designer, product-manager, recruiter, lawyer, consultant, scientist, musician, "
    "author, podcaster, executive, sales, marketing, data-science, devops, "
    "finance, banking, crypto, climate-tech, biotech, edtech.\n\n"
    "If there is not enough information to infer meaningful tags, return an empty list.\n\n"
    'Return JSON: {"contacts": [{"person_id": "...", "descriptive_tags": []}]}'
)


async def _fetch_tags_from_llm(
    people: list[Person],
    settings: "get_settings",
) -> dict[str, list[str]]:
    """Call LLM to get descriptive tags for a batch of people."""
    payload_people: list[dict[str, str]] = []
    for person in people:
        payload_people.append({
            "person_id": str(person.id),
            "name": person.canonical_name,
            "email": person.primary_email or "",
            "org": person.current_org_name or "",
            "role": person.current_role or "",
            "bio": (person.bio_summary or "")[:300],
        })

    async with httpx.AsyncClient(timeout=60.0) as http:
        response = await http.post(
            f"{settings.openai_base_url.rstrip('/')}/chat/completions",
            headers={
                "Authorization": f"Bearer {settings.openai_api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": settings.openai_enrichment_model,
                "temperature": 0,
                "response_format": {"type": "json_object"},
                "messages": [
                    {"role": "system", "content": BACKFILL_PROMPT},
                    {"role": "user", "content": json.dumps({"contacts": payload_people})},
                ],
            },
        )
        response.raise_for_status()
        data: dict[str, object] = parse_json_object(
            content_from_chat_completion(cast(dict[str, object], response.json()))
        )

    results: dict[str, list[str]] = {}
    contacts_raw: object = data.get("contacts")
    if not isinstance(contacts_raw, list):
        return results

    for item_raw in cast(list[object], contacts_raw):
        if not isinstance(item_raw, dict):
            continue
        item: dict[str, object] = cast(dict[str, object], item_raw)
        pid: object = item.get("person_id")
        tags: object = item.get("descriptive_tags")
        if isinstance(pid, str) and isinstance(tags, list):
            results[pid] = [str(t).lower().strip() for t in tags if isinstance(t, (str, int))]

    return results


async def main(batch_size: int, limit: int, dry_run: bool) -> None:
    settings = get_settings()
    if not settings.openai_api_key:
        logger.error("OPENAI_API_KEY not set — cannot run backfill")
        return

    engine = create_async_engine(str(settings.database_url), pool_pre_ping=True)
    session_factory: async_sessionmaker[AsyncSession] = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as session:
        empty_array: list[str] = []
        count_result = await session.execute(
            select(func.count(Person.id)).where(Person.descriptive_tags == empty_array)
        )
        total: int = count_result.scalar() or 0
        logger.info("Found %d persons with empty descriptive_tags (limit=%d)", total, limit)

        stmt = (
            select(Person)
            .where(Person.descriptive_tags == empty_array)
            .order_by(Person.updated_at.desc())
            .limit(limit)
        )
        result = await session.execute(stmt)
        people: list[Person] = list(result.scalars().all())

    processed: int = 0
    tagged: int = 0

    for i in range(0, len(people), batch_size):
        batch: list[Person] = people[i : i + batch_size]
        logger.info("Processing batch %d–%d of %d", i + 1, i + len(batch), len(people))

        try:
            tag_map: dict[str, list[str]] = await _fetch_tags_from_llm(batch, settings)
        except Exception:
            logger.exception("LLM call failed for batch starting at %d", i)
            continue

        if dry_run:
            for pid, tags in tag_map.items():
                if tags:
                    person_match: Person | None = next((p for p in batch if str(p.id) == pid), None)
                    name: str = person_match.canonical_name if person_match else pid
                    logger.info("  [DRY RUN] %s → %s", name, tags)
                    tagged += 1
            processed += len(batch)
            continue

        async with session_factory() as session:
            for person in batch:
                tags: list[str] = tag_map.get(str(person.id), [])
                if not tags:
                    continue
                for tag in tags:
                    await record_person_attribute(
                        session,
                        person_id=person.id,
                        kind="descriptive_tag",
                        value=tag,
                        contributor_user_id=None,
                        contributor_source_kind="llm_backfill",
                        confidence=0.6,
                    )
                tagged += 1

            recomputer = PersonProfileRecompute(session)
            person_ids = [p.id for p in batch if tag_map.get(str(p.id))]
            if person_ids:
                await recomputer.recompute_persons(person_ids)
            await session.commit()

        processed += len(batch)
        logger.info("  Batch done: %d/%d tagged so far", tagged, processed)

    logger.info("Backfill complete: %d processed, %d tagged", processed, tagged)
    await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Backfill descriptive_tags via LLM")
    parser.add_argument("--batch-size", type=int, default=50)
    parser.add_argument("--limit", type=int, default=1000)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    asyncio.run(main(batch_size=args.batch_size, limit=args.limit, dry_run=args.dry_run))
