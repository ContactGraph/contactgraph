"""Opaque identifiers for second-degree contact matches (no raw person UUIDs)."""

from __future__ import annotations

import hashlib
import hmac
import uuid


def opaque_second_degree_person_ref(
    *,
    person_id: uuid.UUID,
    holder_user_id: uuid.UUID,
    viewer_user_id: uuid.UUID,
    signing_key: str,
) -> str:
    message: bytes = f"{person_id}:{holder_user_id}:{viewer_user_id}".encode()
    digest: bytes = hmac.new(
        signing_key.encode("utf-8"),
        message,
        hashlib.sha256,
    ).digest()
    return digest.hex()[:32]
