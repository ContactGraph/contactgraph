"""Poll-secret helpers for connect-session token dispensing."""

from __future__ import annotations

import secrets

from contactsafe_server.db.models import ConnectSession
from contactsafe_server.services.token_hash import hash_token


def assign_poll_secret(session: ConnectSession) -> str:
    """Store a hash on the session and return the one-time plaintext secret."""
    raw_secret: str = secrets.token_urlsafe(32)
    session.poll_secret_hash = hash_token(raw_secret)
    return raw_secret


def verify_poll_secret(session: ConnectSession, poll_secret: str) -> bool:
    expected_hash: str | None = session.poll_secret_hash
    if expected_hash is None or not poll_secret.strip():
        return False
    return hash_token(poll_secret.strip()) == expected_hash
