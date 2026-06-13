"""Expand company/org queries into matchable tokens (domains, email, text)."""

import re

from contactsafe_server.services.email_parse import BROADCAST_LOCAL_PARTS, NO_REPLY_LOCAL_PARTS

_PLACEHOLDER_ORG_NAMES: frozenset[str] = frozenset(
    {
        "self employed",
        "selfemployed",
        "freelance",
        "freelancer",
        "freelancing",
        "independent",
        "independent consultant",
        "retired",
        "unemployed",
        "student",
        "none",
        "n a",
        "na",
        "not applicable",
        "various",
        "myself",
        "personal",
        "home",
        "open to work",
        "looking for opportunities",
        "between jobs",
        "seeking opportunities",
        "available",
        "confidential",
    }
)

# TLDs that often appear as a separate word in company names (e.g. "Sticker VC").
_COMPANY_TLD_SUFFIXES: frozenset[str] = frozenset(
    {"vc", "ai", "io", "co", "tv", "hq", "labs", "capital", "ventures", "partners"}
)

_GENERIC_EMAIL_DOMAINS: frozenset[str] = frozenset(
    {
        "gmail.com",
        "googlemail.com",
        "yahoo.com",
        "hotmail.com",
        "outlook.com",
        "icloud.com",
        "me.com",
        "mac.com",
        "live.com",
        "protonmail.com",
        "fastmail.com",
        "aol.com",
        "comcast.net",
        "att.net",
        "sbcglobal.net",
        "msn.com",
        "ymail.com",
        "mail.com",
    }
)

_KNOWN_DOMAIN_BRANDS: dict[str, str] = {
    "theinformation.com": "The Information",
    "nytimes.com": "The New York Times",
    "wsj.com": "The Wall Street Journal",
    "techcrunch.com": "TechCrunch",
    "bloomberg.com": "Bloomberg",
    "substack.com": "Substack",
    "linkedin.com": "LinkedIn",
    "github.com": "GitHub",
    "stripe.com": "Stripe",
    "openai.com": "OpenAI",
    "anthropic.com": "Anthropic",
    "sequoiacap.com": "Sequoia Capital",
    "a16z.com": "Andreessen Horowitz",
    "ycombinator.com": "Y Combinator",
    "northlight.io": "Northlight",
    "sparkcapital.com": "Spark Capital",
    "bvp.com": "Bessemer Venture Partners",
    "patagonia.com": "Patagonia",
    "wayfair.com": "Wayfair",
    "statefarm.com": "State Farm",
}


def is_generic_personal_domain(domain: str) -> bool:
    """Consumer email providers — not a work org."""
    return domain.lower() in _GENERIC_EMAIL_DOMAINS


def is_automation_domain(domain: str) -> bool:
    """Domains used by bots, notifications, and marketing infrastructure."""
    domain_lower: str = domain.lower()
    if "noreply" in domain_lower or "no-reply" in domain_lower:
        return True
    if domain_lower.endswith(".ccsend.com") or "ccsend.com" in domain_lower:
        return True

    labels: list[str] = [label for label in domain_lower.split(".") if label]
    if labels and labels[0] in {
        "notify",
        "notification",
        "notifications",
        "email",
        "mail",
        "marketing",
        "communication",
        "e",
        "messages",
        "alerts",
    }:
        return True

    automation_markers: tuple[str, ...] = (
        "notify.",
        "notification.",
        "email.",
        "mail.",
        "marketing.",
        "communication.",
    )
    return any(domain_lower.startswith(marker) for marker in automation_markers)


_NON_COMPANY_TLDS: frozenset[str] = frozenset({
    "gov", "edu", "mil", "museum", "int",
})

_GOV_EDU_SUBDOMAIN_SUFFIXES: tuple[str, ...] = (
    ".gov",
    ".edu",
    ".mil",
    ".k12.",
    ".ac.",
    ".gov.",
)


def is_non_company_domain(domain: str) -> bool:
    """Domains that should never produce heuristic Org records
    (.gov, .edu, multi-part subdomains of those, etc.)."""
    domain_lower: str = domain.lower()
    labels: list[str] = [label for label in domain_lower.split(".") if label]
    if not labels:
        return True
    tld: str = labels[-1]
    if tld in _NON_COMPANY_TLDS:
        return True
    if any(domain_lower.endswith(suffix) or f".{suffix.strip('.')}." in f".{domain_lower}" for suffix in _GOV_EDU_SUBDOMAIN_SUFFIXES):
        return True
    return False


def is_automation_or_generic_domain(domain: str) -> bool:
    """Skip org resolution for personal inboxes and automation domains."""
    domain_lower: str = domain.lower()
    return (
        is_generic_personal_domain(domain_lower)
        or is_automation_domain(domain_lower)
        or is_non_company_domain(domain_lower)
    )


def normalize_org_name_key(name: str) -> str:
    """Lowercase org name with punctuation collapsed for alias lookup."""
    lowered: str = name.strip().lower()
    collapsed: str = re.sub(r"[^a-z0-9]+", " ", lowered)
    return " ".join(collapsed.split())


def is_placeholder_org_name(name: str) -> bool:
    """LinkedIn-style status labels that are not real organizations."""
    normalized: str = normalize_org_name_key(name)
    if not normalized or len(normalized) < 2:
        return True
    if normalized in _PLACEHOLDER_ORG_NAMES:
        return True
    return normalized.startswith("stealth")


def org_name_from_domain(domain: str) -> str | None:
    """Infer a display org name from a work email domain."""
    domain_lower: str = domain.strip().lower()
    if not domain_lower or "." not in domain_lower:
        return None
    if (
        domain_lower in _GENERIC_EMAIL_DOMAINS
        or is_automation_domain(domain_lower)
        or is_non_company_domain(domain_lower)
    ):
        return None

    known_brand: str | None = _KNOWN_DOMAIN_BRANDS.get(domain_lower)
    if known_brand is not None:
        return known_brand

    labels: list[str] = [label for label in domain_lower.split(".") if label]
    if len(labels) < 2:
        return None

    tld: str = labels[-1].lower()
    sld: str = labels[-2].lower()
    if tld in _COMPANY_TLD_SUFFIXES and len(labels) >= 2:
        brand: str = _label_to_words(sld)
        suffix: str = tld.upper() if len(tld) <= 3 else tld.title()
        return f"{brand} {suffix}".strip()

    brand_only: str = _label_to_words(sld)
    if not brand_only or len(brand_only) < 2:
        return None
    return brand_only


def org_name_from_email(email: str) -> str | None:
    """Infer a display org name from a work email domain."""
    normalized: str | None = _normalize_email_for_org(email)
    if normalized is None:
        return None
    local, domain = normalized.rsplit("@", 1)
    local_lower: str = local.lower()
    if local_lower in NO_REPLY_LOCAL_PARTS or local_lower in BROADCAST_LOCAL_PARTS:
        return None
    if domain in _GENERIC_EMAIL_DOMAINS or is_automation_domain(domain) or is_non_company_domain(domain):
        return None

    known_brand: str | None = _KNOWN_DOMAIN_BRANDS.get(domain)
    if known_brand is not None:
        return known_brand

    labels: list[str] = [label for label in domain.split(".") if label]
    if len(labels) < 2:
        return None

    tld: str = labels[-1].lower()
    sld: str = labels[-2].lower()
    if tld in _COMPANY_TLD_SUFFIXES and len(labels) >= 2:
        brand: str = _label_to_words(sld)
        suffix: str = tld.upper() if len(tld) <= 3 else tld.title()
        return f"{brand} {suffix}".strip()

    brand_only: str = _label_to_words(sld)
    if not brand_only or len(brand_only) < 2:
        return None
    return brand_only


def expand_org_search_terms(org_query: str) -> list[str]:
    """Turn a user org query into multiple lowercase match tokens."""
    raw: str = org_query.strip()
    if not raw:
        return []

    terms: set[str] = set()
    lowered: str = raw.lower()
    terms.add(lowered)

    # Alphanumeric slug: "Sticker VC" -> "stickervc"
    slug: str = re.sub(r"[^a-z0-9]+", "", lowered)
    if len(slug) >= 2:
        terms.add(slug)

    # Domain-ish forms: sticker.vc, sticker-vc
    domain_slug: str = re.sub(r"[^a-z0-9]+", ".", lowered).strip(".")
    if domain_slug and "." in domain_slug:
        terms.add(domain_slug)
    hyphen_slug: str = re.sub(r"[^a-z0-9]+", "-", lowered).strip("-")
    if hyphen_slug and "-" in hyphen_slug:
        terms.add(hyphen_slug)

    # Significant words (skip noise like "the", "inc", "llc")
    stop: frozenset[str] = frozenset(
        {"the", "and", "inc", "llc", "ltd", "corp", "co", "company", "group"}
    )
    words: list[str] = [w for w in re.split(r"[^a-z0-9]+", lowered) if w and w not in stop]
    for word in words:
        if len(word) >= 2:
            terms.add(word)
    if len(words) >= 2:
        terms.add("".join(words))

    # If query ends with a known company TLD token, also match email domains like brand.vc
    if words and words[-1] in _COMPANY_TLD_SUFFIXES and len(words) >= 2:
        brand_part: str = "".join(words[:-1])
        tld_part: str = words[-1]
        if brand_part:
            terms.add(f"{brand_part}.{tld_part}")

    return sorted(terms, key=len, reverse=True)


def email_matches_org_terms(email: str, terms: list[str]) -> bool:
    normalized: str | None = _normalize_email_for_org(email)
    if normalized is None or not terms:
        return False
    local, domain = normalized.rsplit("@", 1)
    haystacks: list[str] = [
        normalized,
        domain,
        local,
        domain.replace(".", ""),
        domain.replace(".", " "),
    ]
    domain_labels: list[str] = [label for label in domain.split(".") if label]
    if len(domain_labels) >= 2:
        haystacks.append(domain_labels[-2])
        if domain_labels[-1] in _COMPANY_TLD_SUFFIXES:
            haystacks.append(f"{domain_labels[-2]}.{domain_labels[-1]}")
            haystacks.append(f"{domain_labels[-2]} {domain_labels[-1]}")

    for term in terms:
        t: str = term.lower()
        for hay in haystacks:
            h: str = hay.lower()
            if t == h or t in h or h in t:
                return True
    return False


def _normalize_email_for_org(email: str) -> str | None:
    normalized: str = email.strip().lower()
    if not normalized or "@" not in normalized:
        return None
    local, domain = normalized.rsplit("@", 1)
    if not local or not domain or "." not in domain:
        return None
    return normalized


def _label_to_words(label: str) -> str:
    spaced: str = label.replace("-", " ").replace("_", " ")
    return " ".join(part.capitalize() for part in spaced.split() if part)
