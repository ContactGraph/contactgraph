#!/usr/bin/env python3
"""Reclassify contacts using List-Unsubscribe header detection.

For each contact currently marked is_human=True with outbound_count=0,
re-fetch a sample of their recent messages and check for the
List-Unsubscribe header. Contacts where the header is present get
flipped to is_broadcast=True, is_human=False.

Usage:
  uv run python packages/server/scripts/reclassify_broadcasts.py --dry-run
  uv run python packages/server/scripts/reclassify_broadcasts.py --limit 200
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

os.environ.setdefault("APP_ENV", "development")

from contactsafe_server.config import get_settings  # noqa: E402
from contactsafe_server.db.models import (  # noqa: E402
    OAuthCredential,
    Person,
    PersonAlias,
    Source,
    User,
    UserPersonObservation,
)
from contactsafe_server.oauth.google import GoogleOAuthClient  # noqa: E402
from contactsafe_server.services.crypto import TokenEncryptor  # noqa: E402
from contactsafe_server.services.gmail_client import GmailClient, GmailMessageMeta  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger: logging.Logger = logging.getLogger(__name__)

SAMPLE_MESSAGES: int = 5


async def main(limit: int, dry_run: bool) -> None:
    settings = get_settings()
    encryptor = TokenEncryptor(settings.token_encryption_key)
    google = GoogleOAuthClient(settings)
    gmail = GmailClient(settings, google)

    engine = create_async_engine(str(settings.database_url), pool_pre_ping=True)
    session_factory: async_sessionmaker[AsyncSession] = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as session:
        # Find contacts marked human with no outbound — likely newsletters
        stmt = (
            select(UserPersonObservation, Person)
            .join(Person, Person.id == UserPersonObservation.person_id)
            .where(
                UserPersonObservation.is_human.is_(True),
                UserPersonObservation.outbound_count == 0,
                UserPersonObservation.inbound_count >= 2,
            )
            .order_by(UserPersonObservation.inbound_count.desc())
            .limit(limit)
        )
        result = await session.execute(stmt)
        candidates: list[tuple[UserPersonObservation, Person]] = list(result.all())

    logger.info("Found %d candidates (is_human=True, outbound=0, inbound>=2)", len(candidates))
    if not candidates:
        await engine.dispose()
        return

    # Get credentials for the first user (single-user system for now)
    async with session_factory() as session:
        cred_stmt = select(OAuthCredential).where(OAuthCredential.provider == "google").limit(1)
        cred_result = await session.execute(cred_stmt)
        cred: OAuthCredential | None = cred_result.scalar_one_or_none()

    if cred is None:
        logger.error("No OAuth credentials found — cannot access Gmail")
        await engine.dispose()
        return

    access_token: str = encryptor.decrypt(cred.access_token_encrypted)
    refresh_token: str = encryptor.decrypt(cred.refresh_token_encrypted)
    access_token, refreshed = await gmail.get_valid_access_token(
        access_token, refresh_token, cred.token_expires_at
    )
    if refreshed is not None:
        access_token = refreshed.access_token

    reclassified: int = 0
    checked: int = 0

    for obs, person in candidates:
        email: str = person.primary_email or ""
        if not email:
            continue

        checked += 1
        has_unsub: bool = False

        try:
            refs, _ = await gmail.list_message_refs(
                access_token,
                max_results=SAMPLE_MESSAGES,
                query=f"from:{email}",
            )
            for ref in refs:
                meta: GmailMessageMeta = await gmail.get_message_metadata(access_token, ref.id)
                if meta.has_list_unsubscribe:
                    has_unsub = True
                    break
        except Exception:
            logger.warning("  Failed to check messages for %s, skipping", email)
            continue

        if has_unsub:
            if dry_run:
                logger.info("  [DRY RUN] %s (%s) → broadcast", person.canonical_name, email)
            else:
                async with session_factory() as session:
                    await session.execute(
                        update(UserPersonObservation)
                        .where(
                            UserPersonObservation.user_id == obs.user_id,
                            UserPersonObservation.person_id == obs.person_id,
                        )
                        .values(is_human=False, is_broadcast=True)
                    )
                    await session.commit()
                logger.info("  Reclassified: %s (%s) → broadcast", person.canonical_name, email)
            reclassified += 1

        if checked % 25 == 0:
            logger.info("  Progress: %d checked, %d reclassified", checked, reclassified)

    logger.info("Done: %d checked, %d reclassified as broadcast", checked, reclassified)
    await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Reclassify broadcasts via List-Unsubscribe")
    parser.add_argument("--limit", type=int, default=500)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    asyncio.run(main(limit=args.limit, dry_run=args.dry_run))
