"""Shared hashing helpers for secrets stored at rest."""

from __future__ import annotations

import hashlib


def hash_token(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()
