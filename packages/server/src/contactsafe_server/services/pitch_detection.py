"""Detect fundraising / pitch outreach in Gmail snippets (outbound from the user)."""

import re

from contactsafe_server.services.email_parse import parse_address_header

_PITCH_SNIPPET_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"\bpitch\b",
        r"\bfundraising\b",
        r"\braising\s+(?:a\s+)?(?:seed|series|round)\b",
        r"\bseed\s+round\b",
        r"\bseries\s+[a-c]\b",
        r"\b(?:our|my)\s+startup\b",
        r"\bshare\s+(?:our|my)\s+(?:deck|pitch)\b",
        r"\bsend\s+(?:you\s+)?(?:our|my)\s+deck\b",
        r"\binvestor(?:s)?\b",
        r"\bventure\s+capital\b",
        r"\bintro(?:duction)?\s+call\b",
        r"\b(?:quick|brief|short)\s+(?:call|chat|meeting)\b.*\b(?:startup|company|idea)\b",
        r"\b(?:would|love)\s+(?:to|love)\s+(?:share|tell\s+you\s+about)\b",
        r"\btaking\s+meetings\b",
        r"\bcatching\s+up\s+about\b.*\b(?:fund|round|company)\b",
    )
)


def message_from_user(from_header: str | None, user_email: str) -> bool:
    user_lower: str = user_email.strip().lower()
    for _name, email in parse_address_header(from_header or ""):
        if email == user_lower:
            return True
    return False


def is_pitch_outreach_snippet(snippet: str) -> bool:
    """True when a short message preview looks like the user pitching or fundraising."""
    text: str = snippet.strip()
    if len(text) < 12:
        return False
    return any(pattern.search(text) for pattern in _PITCH_SNIPPET_PATTERNS)
