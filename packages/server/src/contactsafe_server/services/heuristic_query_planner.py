import re

from contactsafe_core.query_plan import QueryIntent, QueryPlan, QuerySortBy
from contactsafe_server.services.email_parse import (
    company_query_from_question,
    name_query_from_question,
    name_tokens_from_proper_nouns,
)


def plan_from_heuristics(question: str) -> QueryPlan:
    """Rule-based QueryPlan when LLM is unavailable or as fallback."""
    q_lower: str = question.lower()
    plan = QueryPlan(exclude_broadcast=True, sort_by=QuerySortBy.TIE_STRENGTH, limit=25)

    if _is_lookup_email_intent(q_lower):
        plan.intent = QueryIntent.LOOKUP_CONTACT
        plan.limit = 5

    if _is_semantic_intent(q_lower):
        plan.intent = QueryIntent.SEMANTIC_SEARCH
        plan.semantic_query = question.strip()

    name_hint: str | None = name_query_from_question(question)
    if name_hint is None:
        name_hint = _name_from_lookup_email_pattern(question)
    if name_hint is not None:
        plan.name_tokens = _tokenize_name(name_hint)
    elif not plan.name_tokens:
        plan.name_tokens = name_tokens_from_proper_nouns(question)

    company: str | None = company_query_from_question(question)
    if company is not None:
        plan.org_names.append(company)

    for org in _extract_org_phrases(question):
        if org not in plan.org_names:
            plan.org_names.append(org)

    if _mentions_vcs(q_lower):
        plan.categories_any.extend(["vc", "investor"])
        plan.categories_any = _dedupe(plan.categories_any)

    for role in _extract_role_keywords(q_lower):
        plan.role_keywords.append(role)

    if plan.intent == QueryIntent.LOOKUP_CONTACT and plan.name_tokens and plan.org_names:
        plan.limit = 1

    if not _has_any_filter(plan):
        plan.intent = QueryIntent.LIST_PEOPLE
        plan.limit = 25

    return plan


def _is_lookup_email_intent(q_lower: str) -> bool:
    return bool(
        re.search(
            r"\b(email|e-mail|address)\b.*\bfor\b|\bwhat(?:'s| is) the email\b",
            q_lower,
        )
    )


def _is_semantic_intent(q_lower: str) -> bool:
    return bool(
        re.search(
            r"\b(talked|discussed|conversation|about hiring|about pricing|topic)\b",
            q_lower,
        )
    )


def _mentions_vcs(q_lower: str) -> bool:
    return bool(re.search(r"\b(vcs?|venture capital|investors?)\b", q_lower))


def _extract_role_keywords(q_lower: str) -> list[str]:
    found: list[str] = []
    role_patterns: list[tuple[str, str]] = [
        (r"\brevops\b", "revops"),
        (r"\brevenue operations\b", "revenue operations"),
        (r"\bsales\b", "sales"),
        (r"\bengineer(?:ing)?\b", "engineering"),
        (r"\bproduct manager\b", "product manager"),
        (r"\bfounder\b", "founder"),
    ]
    for pattern, keyword in role_patterns:
        if re.search(pattern, q_lower):
            found.append(keyword)
    return _dedupe(found)


def _extract_org_phrases(question: str) -> list[str]:
    patterns: list[str] = [
        r"\bat\s+([A-Za-z0-9][A-Za-z0-9._&\s'-]{1,60})",
        r"\bfrom\s+([A-Za-z0-9][A-Za-z0-9._&\s'-]{1,60})",
        r"\bwho\s+(?:works|worked)\s+(?:at|for)\s+([A-Za-z0-9][A-Za-z0-9._&\s'-]{1,60})",
    ]
    orgs: list[str] = []
    for pattern in patterns:
        match = re.search(pattern, question, flags=re.IGNORECASE)
        if match is not None:
            org = match.group(1).strip().rstrip("?.!,")
            if org and org.lower() not in {"who", "anyone"}:
                orgs.append(org)
    return orgs


def _name_from_lookup_email_pattern(question: str) -> str | None:
    match = re.search(
        r"\b(?:email|e-mail|address)\s+for\s+([A-Za-z][A-Za-z'.-]*(?:\s+[A-Za-z][A-Za-z'.-]*)?)",
        question,
        flags=re.IGNORECASE,
    )
    if match is None:
        match = re.search(
            r"\bfor\s+([A-Za-z][A-Za-z'.-]*)\s+at\s+",
            question,
            flags=re.IGNORECASE,
        )
    if match is None:
        return None
    name: str = match.group(1).strip().rstrip("?.!,")
    return name if name else None


def _tokenize_name(name_hint: str) -> list[str]:
    return [t for t in name_hint.lower().split() if len(t) >= 2]


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        key = value.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(value)
    return out


def _has_any_filter(plan: QueryPlan) -> bool:
    return bool(
        plan.name_tokens
        or plan.org_names
        or plan.categories_any
        or plan.role_keywords
        or plan.relationship_types_any
        or plan.semantic_query
    )
