import re
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import getaddresses

NO_REPLY_LOCAL_PARTS: frozenset[str] = frozenset(
    {
        "noreply",
        "no-reply",
        "donotreply",
        "do-not-reply",
        "mailer-daemon",
        "postmaster",
        "notifications",
        "notification",
        "bounce",
    }
)


@dataclass(slots=True)
class ParsedContact:
    email: str
    display_name: str
    last_seen_at: datetime | None = None
    message_count: int = 0
    outbound_count: int = 0
    inbound_count: int = 0


@dataclass(slots=True)
class ContactAccumulator:
    email: str
    display_name: str
    last_seen_at: datetime | None = None
    message_count: int = 0
    outbound_count: int = 0
    inbound_count: int = 0

    def observe(
        self,
        *,
        display_name: str,
        seen_at: datetime | None,
        from_user: bool,
    ) -> None:
        self.message_count += 1
        if from_user:
            self.outbound_count += 1
        else:
            self.inbound_count += 1
        if display_name and (not self.display_name or self.display_name == self.email):
            self.display_name = display_name
        if seen_at is not None and (self.last_seen_at is None or seen_at > self.last_seen_at):
            self.last_seen_at = seen_at


def normalize_email(value: str) -> str | None:
    email: str = value.strip().lower()
    if not email or "@" not in email:
        return None
    local, domain = email.rsplit("@", 1)
    if not local or not domain or "." not in domain:
        return None
    if local in NO_REPLY_LOCAL_PARTS or local.startswith("noreply"):
        return None
    return email


def parse_address_header(header_value: str) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = getaddresses([header_value])
    result: list[tuple[str, str]] = []
    for name, addr in pairs:
        normalized: str | None = normalize_email(addr)
        if normalized is None:
            continue
        display: str = name.strip() or normalized
        result.append((display, normalized))
    return result


def org_name_from_email(email: str) -> str | None:
    _name, domain = email.rsplit("@", 1)
    generic_domains: frozenset[str] = frozenset(
        {"gmail.com", "googlemail.com", "yahoo.com", "hotmail.com", "outlook.com", "icloud.com", "me.com"}
    )
    if domain in generic_domains:
        return None
    base: str = domain.split(".")[0]
    if not base or len(base) < 2:
        return None
    return base.replace("-", " ").title()


def is_likely_broadcast_contact(accumulator: ContactAccumulator) -> bool:
    """Newsletter / one-way marketing style contact."""
    if accumulator.outbound_count == 0 and accumulator.inbound_count >= 3:
        return True
    local: str = accumulator.email.split("@", 1)[0]
    if local in NO_REPLY_LOCAL_PARTS or "newsletter" in local or "marketing" in local:
        return True
    return False


def is_human_edge(accumulator: ContactAccumulator) -> bool:
    return accumulator.outbound_count > 0 and accumulator.inbound_count > 0


def _strip_query_fragment(value: str) -> str:
    return value.strip().rstrip("?.!,").strip()


def company_query_from_question(question: str) -> str | None:
    patterns: list[str] = [
        r"\bat\s+([A-Za-z0-9][A-Za-z0-9._&\s-]{1,60})",
        r"\bfrom\s+([A-Za-z0-9][A-Za-z0-9._&\s-]{1,60})",
        r"\bwho\s+(?:works|worked)\s+(?:at|for)\s+([A-Za-z0-9][A-Za-z0-9._&\s-]{1,60})",
    ]
    for pattern in patterns:
        match: re.Match[str] | None = re.search(pattern, question, flags=re.IGNORECASE)
        if match is not None:
            company: str = _strip_query_fragment(match.group(1))
            if company:
                return company
    return None


def name_query_from_question(question: str) -> str | None:
    """Extract a person-name hint from questions like 'who do I know named Chris'."""
    patterns: list[str] = [
        r"\bnamed\s+([A-Za-z][A-Za-z'.-]*(?:\s+[A-Za-z][A-Za-z'.-]*)?)",
        r"\bcalled\s+([A-Za-z][A-Za-z'.-]*(?:\s+[A-Za-z][A-Za-z'.-]*)?)",
        r"\bwho\s+(?:is|do\s+I\s+know)\s+([A-Za-z][A-Za-z'.-]*(?:\s+[A-Za-z][A-Za-z'.-]*)?)",
        r"\bknow\s+(?:someone|anyone|a\s+person)\s+named\s+([A-Za-z][A-Za-z'.-]*(?:\s+[A-Za-z][A-Za-z'.-]*)?)",
    ]
    for pattern in patterns:
        match: re.Match[str] | None = re.search(pattern, question, flags=re.IGNORECASE)
        if match is not None:
            name: str = _strip_query_fragment(match.group(1))
            if name and name.lower() not in {"who", "anyone", "someone"}:
                return name
    return None


def person_matches_name(person_name: str, person_emails: list[str], name_query: str) -> bool:
    tokens: list[str] = [
        token
        for token in name_query.lower().split()
        if len(token) >= 2
    ]
    if not tokens:
        return False
    name_lower: str = person_name.lower()
    email_blob: str = " ".join(person_emails).lower()
    return all(token in name_lower or token in email_blob for token in tokens)


def parse_internal_date_ms(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        millis: int = int(raw)
    except ValueError:
        return None
    return datetime.fromtimestamp(millis / 1000.0, tz=UTC)
