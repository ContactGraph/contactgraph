"""Default strategy pipeline and confidence scoring for per-contact enrichment."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from contactsafe_server.db.models import Person, PersonAlias, UserPersonObservation
from contactsafe_server.services.org_search import is_automation_or_generic_domain

DEFAULT_ENRICHMENT_STRATEGIES: tuple[str, ...] = (
    "heuristic",
    "signature",
    "scrapingdog_linkedin",
    "web_employer",
    "web_relational",
    "user_companies",
    "email_derived",
    "linkedin_search",
    "mutual_connections",
    "llm_synthesis",
)

STRONG_TIE_ENRICHMENT_STRATEGIES: tuple[str, ...] = ("scrapingdog_linkedin",)


@dataclass(frozen=True, slots=True)
class EnrichmentConfidence:
    score: float
    has_linkedin: bool
    has_current_employer: bool
    has_role: bool
    has_verified_email: bool
    has_bio: bool


def compute_enrichment_confidence(
    person: Person,
    *,
    linkedin_url: str | None = None,
) -> EnrichmentConfidence:
    has_linkedin: bool = bool(
        linkedin_url
        or (person.social_profiles or {}).get("linkedin")
    )
    has_current_employer: bool = bool(person.current_org_name)
    has_role: bool = bool(person.current_role)
    email: str = person.primary_email or ""
    has_verified_email: bool = bool(
        email
        and "@" in email
        and not is_automation_or_generic_domain(email.rsplit("@", 1)[1].lower())
    )
    has_bio: bool = bool(person.bio_summary)

    score: float = 0.0
    if has_linkedin:
        score += 0.3
    if has_current_employer:
        score += 0.3
    if has_role:
        score += 0.2
    if has_verified_email:
        score += 0.1
    if has_bio:
        score += 0.1

    return EnrichmentConfidence(
        score=min(score, 1.0),
        has_linkedin=has_linkedin,
        has_current_employer=has_current_employer,
        has_role=has_role,
        has_verified_email=has_verified_email,
        has_bio=has_bio,
    )


def email_domain_is_fresh(
    obs: UserPersonObservation | None,
    *,
    freshness_days: int,
) -> bool:
    if obs is None or obs.last_observed_at is None:
        return False
    cutoff: datetime = datetime.now(tz=timezone.utc) - timedelta(days=freshness_days)
    last_seen: datetime = obs.last_observed_at
    if last_seen.tzinfo is None:
        last_seen = last_seen.replace(tzinfo=timezone.utc)
    return last_seen >= cutoff


def compute_enqueue_priority(
    obs: UserPersonObservation | None,
    *,
    manual_boost: int = 0,
) -> int:
    priority: int = manual_boost
    if obs is None:
        return priority
    priority += int(obs.tie_strength_score * 1000)
    if obs.is_human:
        priority += 100
    if obs.last_observed_at is not None:
        cutoff: datetime = datetime.now(tz=timezone.utc) - timedelta(days=30)
        last_seen: datetime = obs.last_observed_at
        if last_seen.tzinfo is None:
            last_seen = last_seen.replace(tzinfo=timezone.utc)
        if last_seen >= cutoff:
            priority += 50
    return priority
