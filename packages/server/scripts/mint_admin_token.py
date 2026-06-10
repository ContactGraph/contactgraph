#!/usr/bin/env python3
"""Mint a JWT access token with admin scope for a given user.

Usage:
    # By email (looks up user in DB):
    python scripts/mint_admin_token.py shalomormsby@gmail.com
    python scripts/mint_admin_token.py --email shalomormsby@gmail.com

    # By user UUID (no DB needed):
    python scripts/mint_admin_token.py --uuid 550e8400-e29b-41d4-a716-446655440000

Requires the same environment variables as the server (.env or exported).
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import uuid

from contactsafe_server.config import Settings, get_settings
from contactsafe_server.services.jwt_service import JWTService


async def _resolve_user_id_by_email(email: str, settings: Settings) -> uuid.UUID:
    from sqlalchemy import select
    from contactsafe_server.db.connection import get_session_factory, init_db, shutdown_db
    from contactsafe_server.db.models import User

    await init_db(settings)
    factory = get_session_factory(settings)
    async with factory() as db:
        row = (await db.execute(select(User.id).where(User.email == email))).scalar_one_or_none()
    await shutdown_db()

    if row is None:
        print(f"Error: no user found with email '{email}'", file=sys.stderr)
        sys.exit(1)
    return row  # type: ignore[return-value]


def main() -> None:
    parser = argparse.ArgumentParser(description="Mint an admin JWT for a ContactGraph user")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("email", nargs="?", help="User email address (requires DB)")
    group.add_argument("--email", dest="email_flag", help="User email address (requires DB)")
    group.add_argument("--uuid", help="User UUID (no DB lookup needed)")
    args = parser.parse_args()

    settings: Settings = get_settings()
    jwt_service: JWTService = JWTService(settings)

    if args.uuid:
        user_id = uuid.UUID(args.uuid)
    else:
        email: str | None = args.email_flag or args.email
        if email is None:
            parser.error("email address is required")
        user_id = asyncio.run(_resolve_user_id_by_email(email, settings))

    scopes: list[str] = ["contactsafe:read", "contactsafe:write", "contactsafe:admin"]
    token: str = jwt_service.create_access_token(user_id, scopes)

    print(token)


if __name__ == "__main__":
    main()
