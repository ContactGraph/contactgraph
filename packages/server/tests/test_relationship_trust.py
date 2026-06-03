"""Tests for relationship trust scoring."""

from datetime import UTC, datetime

from contactsafe_server.db.models import UserPersonObservation
from contactsafe_server.services.relationship_trust import (
    HIGH_TRUST_THRESHOLD,
    compute_trust_score,
    is_high_trust_connection,
    trust_weight_for_kind,
)


def _obs(
    *,
    relationship_types: list[str],
    outbound_count: int = 0,
    tie_strength: float = 0.3,
) -> UserPersonObservation:
    return UserPersonObservation(
        user_id="00000000-0000-0000-0000-000000000001",
        person_id="00000000-0000-0000-0000-000000000002",
        relationship_types=relationship_types,
        outbound_count=outbound_count,
        tie_strength_score=tie_strength,
        last_genuine_interaction_at=datetime.now(tz=UTC),
    )


def test_phone_contact_is_high_trust() -> None:
    obs = _obs(relationship_types=["phone_contacts_upload"], tie_strength=0.5)
    assert is_high_trust_connection(observation=obs, relationship_kind="phone_contact")


def test_linkedin_connection_is_low_trust() -> None:
    obs = _obs(relationship_types=["linkedin_connections_upload"], tie_strength=0.1)
    score = compute_trust_score(observation=obs, relationship_kind="linkedin_connection")
    assert score < HIGH_TRUST_THRESHOLD


def test_outbound_email_boosts_trust() -> None:
    base = compute_trust_score(
        observation=_obs(relationship_types=["gmail"], outbound_count=0),
        relationship_kind="co_thread",
    )
    boosted = compute_trust_score(
        observation=_obs(relationship_types=["gmail"], outbound_count=5),
        relationship_kind="co_thread",
    )
    assert boosted > base


def test_kind_weights_ordering() -> None:
    assert trust_weight_for_kind("phone_contact") > trust_weight_for_kind("co_thread")
    assert trust_weight_for_kind("co_thread") > trust_weight_for_kind("linkedin_connection")
