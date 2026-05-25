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

BROADCAST_LOCAL_PARTS: frozenset[str] = frozenset(
    {
        "info",
        "team",
        "hello",
        "support",
        "contact",
        "outreach",
        "webmaster",
        "editor",
        "admin",
        "news",
        "updates",
        "invitations",
        "members",
        "community",
        "events",
    }
)

_INVALID_PERSON_NAMES: frozenset[str] = frozenset(
    {
        "customer_service",
        "subscribed",
        "push",
        "ci activity",
        "unsubscribe",
        "subscribe",
        "billing",
        "support",
        "automated",
        "system",
        "admin",
        "root",
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
    pitch_outbound_count: int = 0
    inbound_snippets: list[str] | None = None

    def observe(
        self,
        *,
        display_name: str,
        seen_at: datetime | None,
        from_user: bool,
        snippet: str | None = None,
    ) -> None:
        self.message_count += 1
        if from_user:
            self.outbound_count += 1
        else:
            self.inbound_count += 1
            if snippet and snippet.strip():
                if self.inbound_snippets is None:
                    self.inbound_snippets = []
                if snippet.strip() not in self.inbound_snippets:
                    self.inbound_snippets.append(snippet.strip())
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


_DOMAIN_EQUIVALENTS: dict[str, str] = {
    "me.com": "icloud.com",
    "mac.com": "icloud.com",
    "googlemail.com": "gmail.com",
}


def canonical_email_domain(domain: str) -> str:
    lowered: str = domain.strip().lower()
    return _DOMAIN_EQUIVALENTS.get(lowered, lowered)


def email_lookup_variants(email: str) -> list[str]:
    """Return equivalent email addresses for entity resolution lookups."""
    normalized: str | None = normalize_email(email)
    if normalized is None:
        return []
    local, domain = normalized.rsplit("@", 1)
    canonical_domain: str = canonical_email_domain(domain)
    variants: set[str] = {normalized}
    if canonical_domain != domain:
        variants.add(f"{local}@{canonical_domain}")
    for alias_domain, canonical in _DOMAIN_EQUIVALENTS.items():
        if canonical == canonical_domain and alias_domain != domain:
            variants.add(f"{local}@{alias_domain}")
    return sorted(variants)


def email_local_part(email: str) -> str:
    normalized: str | None = normalize_email(email)
    if normalized is None:
        return email.split("@", 1)[0].lower()
    return normalized.rsplit("@", 1)[0]


def is_likely_self_contact(
    contact_email: str,
    *,
    user_emails: set[str],
    user_local_parts: set[str],
) -> bool:
    normalized: str | None = normalize_email(contact_email)
    if normalized is None:
        return False
    if normalized in user_emails:
        return True
    local, domain = normalized.rsplit("@", 1)
    if local in user_local_parts and domain not in {"gmail.com", "googlemail.com", "yahoo.com", "hotmail.com", "outlook.com"}:
        return True
    return False


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
    from contactsafe_server.services.org_search import org_name_from_email as _infer

    return _infer(email)


def is_likely_broadcast_contact(accumulator: ContactAccumulator) -> bool:
    """Newsletter / one-way marketing style contact."""
    if accumulator.outbound_count == 0 and accumulator.inbound_count >= 3:
        return True
    local: str = accumulator.email.split("@", 1)[0].lower()
    if local in NO_REPLY_LOCAL_PARTS or local in BROADCAST_LOCAL_PARTS:
        return True
    if "newsletter" in local or "marketing" in local:
        return True
    return False


def is_valid_person_name(name: str) -> bool:
    lowered: str = name.strip().lower()
    if not lowered or len(lowered) < 2:
        return False
    if lowered in _INVALID_PERSON_NAMES:
        return False
    if "_" in lowered and " " not in lowered:
        return False
    return True


def sanitize_display_name(name: str, email: str) -> str:
    cleaned: str = name.strip()
    if is_valid_person_name(cleaned):
        return cleaned
    return email


def is_human_edge(accumulator: ContactAccumulator) -> bool:
    if accumulator.outbound_count > 0 and accumulator.inbound_count > 0:
        return True
    if accumulator.outbound_count >= 2:
        return True
    if accumulator.inbound_count >= 1 and accumulator.message_count <= 5:
        return True
    return False


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


_NAME_STOP_WORDS: frozenset[str] = frozenset(
    {
        "who",
        "what",
        "where",
        "when",
        "find",
        "show",
        "list",
        "tell",
        "give",
        "know",
        "email",
        "address",
        "contact",
        "contacts",
        "people",
        "person",
        "someone",
        "anyone",
        "investors",
        "investor",
        "founders",
        "founder",
        "engineers",
        "engineer",
    }
)


def name_tokens_from_proper_nouns(question: str) -> list[str]:
    """Extract likely person-name tokens from capitalized words in a question."""
    if re.search(r"\b(vcs?|investors?|founders?|engineers?)\b", question, flags=re.IGNORECASE):
        return []
    matches: list[str] = re.findall(
        r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2})\b",
        question,
    )
    if not matches:
        return []
    candidate: str = max(matches, key=len)
    tokens: list[str] = [
        token.lower()
        for token in candidate.split()
        if len(token) >= 2 and token.lower() not in _NAME_STOP_WORDS
    ]
    return tokens


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
