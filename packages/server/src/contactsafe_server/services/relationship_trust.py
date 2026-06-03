"""Trust weights for person-person relationship edges."""

from __future__ import annotations

from typing import Final

from contactsafe_server.db.models import RelationshipClaim, UserPersonObservation

# Source quality ranking (higher = more trusted).
RELATIONSHIP_KIND_TRUST: Final[dict[str, float]] = {
    "phone_contact": 1.0,
    "email_outbound": 0.85,
    "co_thread": 0.75,
    "google_contact": 0.35,
    "linkedin_connection": 0.15,
    "google_calendar": 0.5,
}

# Minimum trust for "high-trust connection" (North Star #1).
HIGH_TRUST_THRESHOLD: Final[float] = 0.7

# Map observation relationship_types to canonical edge kinds.
OBSERVATION_KIND_MAP: Final[dict[str, str]] = {
    "phone_contacts_upload": "phone_contact",
    "linkedin_connections_upload": "linkedin_connection",
    "google_contact": "google_contact",
    "contact": "google_contact",
    "gmail": "co_thread",
}


def canonical_relationship_kind(*, observation_types: list[str], claim_kind: str | None) -> str:
    if claim_kind and claim_kind in RELATIONSHIP_KIND_TRUST:
        return claim_kind
    for obs_type in observation_types:
        mapped: str | None = OBSERVATION_KIND_MAP.get(obs_type)
        if mapped is not None:
            return mapped
    return claim_kind or "google_contact"


def trust_weight_for_kind(kind: str) -> float:
    return RELATIONSHIP_KIND_TRUST.get(kind, 0.2)


def compute_trust_score(
    *,
    observation: UserPersonObservation,
    relationship_kind: str | None = None,
) -> float:
    """Combine edge kind weight with interaction signals.

    Phone contacts are inherently high-trust (user deliberately saved them).
    Email contacts with outbound activity are strong evidence of a real
    relationship.  The formula blends the source-kind base weight with
    interaction evidence so that contacts with real email history score
    well even without a RelationshipClaim row.
    """
    kind: str = canonical_relationship_kind(
        observation_types=list(observation.relationship_types or []),
        claim_kind=relationship_kind,
    )
    base: float = trust_weight_for_kind(kind)

    interaction_boost: float = 0.0
    outbound: int = observation.outbound_count or 0
    if outbound > 0:
        interaction_boost += min(0.25, 0.10 + outbound * 0.01)
    if observation.last_genuine_interaction_at is not None:
        interaction_boost += 0.15
    thread_count: int = observation.thread_count or 0
    if thread_count >= 3:
        interaction_boost += 0.05

    tie: float = min(1.0, observation.tie_strength_score or 0.0)
    combined: float = min(1.0, base * 0.5 + tie * 0.2 + interaction_boost + 0.15)
    return combined


def is_high_trust_connection(
    *,
    observation: UserPersonObservation,
    relationship_kind: str | None = None,
) -> bool:
    return compute_trust_score(
        observation=observation,
        relationship_kind=relationship_kind,
    ) >= HIGH_TRUST_THRESHOLD


def best_relationship_kind(claims: list[RelationshipClaim]) -> str | None:
    if not claims:
        return None
    best: RelationshipClaim = max(
        claims,
        key=lambda claim: trust_weight_for_kind(claim.kind),
    )
    return best.kind
