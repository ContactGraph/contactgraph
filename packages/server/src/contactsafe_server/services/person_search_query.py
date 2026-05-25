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


def build_employer_discovery_query(
    name: str,
    email: str,
    org_hint: str | None,
) -> str:
    parts: list[str] = [f'"{name.strip()}"']
    if org_hint and org_hint.strip():
        parts.append(org_hint.strip())
    if "@" in email:
        domain: str = email.rsplit("@", 1)[1].lower()
        if domain not in _GENERIC_EMAIL_DOMAINS:
            parts.append(domain)
    parts.append("job title role investor venture capital partner")
    return " ".join(parts)


def build_activity_discovery_query(name: str, org_hint: str | None) -> str:
    parts: list[str] = [f'"{name.strip()}"']
    if org_hint and org_hint.strip():
        parts.append(org_hint.strip())
    parts.append("twitter OR bluesky OR substack OR github OR blog posts")
    return " ".join(parts)
