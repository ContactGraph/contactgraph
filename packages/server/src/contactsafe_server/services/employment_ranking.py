"""Rank and normalize employment claims for trustworthy current-employer selection."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Final

from contactsafe_server.db.models import EmploymentClaim, UserPersonObservation

# Default recency window for "current" employment signals (12 months).
DEFAULT_EMPLOYMENT_RECENCY_DAYS: Final[int] = 365

# Base tier by contributor_source_kind (lower = higher priority).
_SOURCE_BASE_TIER: Final[dict[str, int]] = {
    "user_manual": 0,
    "scrapingdog_linkedin": 1,
    "gmail_signature": 1,
    "linkedin_profile_upload": 2,
    "linkedin_connections_upload": 2,
    "exa": 3,
    "tavily": 3,
    "serper": 3,
    "gmail_domain": 5,
    "heuristic": 5,
    "google_contacts": 6,
    "phone_contacts_upload": 6,
}

# Stale signature drops to roughly web tier.
_STALE_SIGNATURE_TIER: Final[int] = 3

_WEB_SOURCE_KINDS: Final[frozenset[str]] = frozenset({"exa", "tavily", "serper"})


@dataclass(frozen=True, slots=True)
class RankedEmploymentClaim:
    claim: EmploymentClaim
    effective_tier: int
    freshness_at: datetime | None
    is_fresh: bool
    is_authoritative_current: bool


def employment_recency_window_days(*, configured_days: int | None = None) -> int:
    if configured_days is not None and configured_days > 0:
        return configured_days
    return DEFAULT_EMPLOYMENT_RECENCY_DAYS


def _utc_now() -> datetime:
    return datetime.now(tz=UTC)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _base_tier(source_kind: str) -> int:
    if source_kind in _WEB_SOURCE_KINDS:
        return _SOURCE_BASE_TIER["exa"]
    return _SOURCE_BASE_TIER.get(source_kind, 5)


def _freshness_anchor(
    claim: EmploymentClaim,
    *,
    last_genuine_interaction_at: datetime | None,
) -> datetime | None:
    source_kind: str = claim.contributor_source_kind
    if source_kind == "gmail_signature":
        return last_genuine_interaction_at or claim.observed_at
    if source_kind in {"linkedin_profile_upload", "linkedin_connections_upload"}:
        return claim.observed_at
    if source_kind in _WEB_SOURCE_KINDS:
        return claim.observed_at
    if source_kind in {"google_contacts", "phone_contacts_upload", "heuristic", "gmail_domain"}:
        return claim.observed_at
    return claim.observed_at


def _is_fresh(
    freshness_at: datetime | None,
    *,
    recency_days: int,
    today: date,
) -> bool:
    if freshness_at is None:
        return False
    cutoff: datetime = datetime.combine(
        today - timedelta(days=recency_days),
        datetime.min.time(),
        tzinfo=UTC,
    )
    return _as_utc(freshness_at) >= cutoff


def _effective_tier(
    claim: EmploymentClaim,
    *,
    is_fresh: bool,
) -> int:
    source_kind: str = claim.contributor_source_kind
    base: int = _base_tier(source_kind)
    if source_kind == "gmail_signature" and not is_fresh:
        return _STALE_SIGNATURE_TIER
    return base


def _date_implies_current(claim: EmploymentClaim, *, today: date) -> bool:
    if claim.ended_at is not None and claim.ended_at < today:
        return False
    if claim.started_at is not None and claim.ended_at is None:
        return True
    return claim.is_current


def _date_implies_not_current(claim: EmploymentClaim, *, today: date) -> bool:
    return claim.ended_at is not None and claim.ended_at < today


def rank_employment_claims(
    claims: list[EmploymentClaim],
    *,
    last_genuine_interaction_at: datetime | None = None,
    recency_days: int = DEFAULT_EMPLOYMENT_RECENCY_DAYS,
    today: date | None = None,
) -> list[RankedEmploymentClaim]:
    """Rank claims for current-employer selection (best first)."""
    effective_today: date = today or _utc_now().date()
    ranked: list[RankedEmploymentClaim] = []
    for claim in claims:
        freshness: datetime | None = _freshness_anchor(
            claim,
            last_genuine_interaction_at=last_genuine_interaction_at,
        )
        fresh: bool = _is_fresh(freshness, recency_days=recency_days, today=effective_today)
        tier: int = _effective_tier(claim, is_fresh=fresh)
        implies_current: bool = _date_implies_current(claim, today=effective_today)
        authoritative: bool = (
            implies_current
            and not _date_implies_not_current(claim, today=effective_today)
            and (fresh or tier >= 4)
        )
        ranked.append(
            RankedEmploymentClaim(
                claim=claim,
                effective_tier=tier,
                freshness_at=freshness,
                is_fresh=fresh,
                is_authoritative_current=authoritative,
            )
        )

    ranked.sort(
        key=lambda item: (
            0 if item.is_authoritative_current else 1,
            item.effective_tier,
            -(item.freshness_at.timestamp() if item.freshness_at else 0.0),
            -item.claim.confidence,
        ),
    )
    return ranked


def select_current_employment(
    claims: list[EmploymentClaim],
    *,
    last_genuine_interaction_at: datetime | None = None,
    recency_days: int = DEFAULT_EMPLOYMENT_RECENCY_DAYS,
    today: date | None = None,
) -> RankedEmploymentClaim | None:
    ranked: list[RankedEmploymentClaim] = rank_employment_claims(
        claims,
        last_genuine_interaction_at=last_genuine_interaction_at,
        recency_days=recency_days,
        today=today,
    )
    for item in ranked:
        if item.is_authoritative_current:
            return item
    return None


def normalize_employment_claims(
    claims: list[EmploymentClaim],
    *,
    last_genuine_interaction_at: datetime | None = None,
    recency_days: int = DEFAULT_EMPLOYMENT_RECENCY_DAYS,
    today: date | None = None,
) -> EmploymentClaim | None:
    """Reconcile is_current/ended_at and return the winning current claim, if any."""
    effective_today: date = today or _utc_now().date()
    winner: RankedEmploymentClaim | None = select_current_employment(
        claims,
        last_genuine_interaction_at=last_genuine_interaction_at,
        recency_days=recency_days,
        today=effective_today,
    )

    winner_org_id: object | None = winner.claim.org_id if winner is not None else None

    for claim in claims:
        if _date_implies_not_current(claim, today=effective_today):
            claim.is_current = False
            continue

        if winner is None:
            if claim.is_current:
                freshness: datetime | None = _freshness_anchor(
                    claim,
                    last_genuine_interaction_at=last_genuine_interaction_at,
                )
                fresh: bool = _is_fresh(
                    freshness,
                    recency_days=recency_days,
                    today=effective_today,
                )
                tier: int = _effective_tier(claim, is_fresh=fresh)
                if not fresh and tier <= 3:
                    claim.is_current = False
                    if claim.ended_at is None:
                        claim.ended_at = effective_today
            continue

        if claim.org_id == winner_org_id:
            claim.is_current = True
            if claim.ended_at is not None and claim.ended_at >= effective_today:
                claim.ended_at = None
            continue

        if claim.is_current:
            claim.is_current = False
            if claim.ended_at is None:
                claim.ended_at = effective_today

    return winner.claim if winner is not None else None
