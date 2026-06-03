"""Query builders shared across web search enrichment providers."""

_GENERIC_EMAIL_DOMAINS: frozenset[str] = frozenset(
    {
        "gmail.com",
        "googlemail.com",
        "yahoo.com",
        "hotmail.com",
        "outlook.com",
        "icloud.com",
        "me.com",
        "live.com",
        "protonmail.com",
        "fastmail.com",
    }
)


def is_generic_email(email: str) -> bool:
    if "@" not in email:
        return True
    domain: str = email.rsplit("@", 1)[1].lower()
    return domain in _GENERIC_EMAIL_DOMAINS


def build_employer_discovery_query(
    name: str,
    email: str,
    org_hint: str | None,
    *,
    user_location: str | None = None,
    context_hints: list[str] | None = None,
) -> str:
    parts: list[str] = [f'"{name.strip()}"']
    if org_hint and org_hint.strip():
        parts.append(org_hint.strip())
    if context_hints:
        for hint in context_hints[:3]:
            cleaned: str = hint.strip()
            if cleaned:
                parts.append(f'"{cleaned}"')
    if "@" in email:
        domain: str = email.rsplit("@", 1)[1].lower()
        if domain not in _GENERIC_EMAIL_DOMAINS:
            parts.append(domain)
    if user_location and user_location.strip():
        parts.append(user_location.strip())
    return " ".join(parts)


def build_activity_discovery_query(
    name: str,
    org_hint: str | None,
    *,
    user_location: str | None = None,
) -> str:
    parts: list[str] = [f'"{name.strip()}"']
    if org_hint and org_hint.strip():
        parts.append(org_hint.strip())
    if user_location and user_location.strip():
        parts.append(user_location.strip())
    parts.append("twitter OR bluesky OR substack OR github OR blog posts")
    return " ".join(parts)


def build_relational_context_query(user_name: str, contact_name: str) -> str:
    return f'"{user_name.strip()}" "{contact_name.strip()}"'
