"""Normalize email addresses for alias lookup and deduplication.

Gmail (and Google Workspace) ignores dots in the local part:
``s.h.a.l.o.m@gmail.com`` is the same mailbox as ``shalom@gmail.com``.
"""

from __future__ import annotations

import re

_GMAIL_DOMAINS: frozenset[str] = frozenset({"gmail.com", "googlemail.com"})

_PLUS_SUFFIX_RE: re.Pattern[str] = re.compile(r"\+.*$")


def normalize_gmail(email: str) -> str:
    """Return a canonical form of a Gmail/Googlemail address.

    * Strips dots from the local part (Gmail ignores them).
    * Strips ``+tag`` suffixes (Gmail ignores everything after ``+``).
    * Lowercases the whole address.
    * Non-Gmail addresses are returned lowered but otherwise unchanged.
    """
    lowered: str = email.strip().lower()
    parts: list[str] = lowered.split("@", maxsplit=1)
    if len(parts) != 2:
        return lowered

    local: str = parts[0]
    domain: str = parts[1]

    if domain not in _GMAIL_DOMAINS:
        return lowered

    local = _PLUS_SUFFIX_RE.sub("", local)
    local = local.replace(".", "")
    return f"{local}@gmail.com"
