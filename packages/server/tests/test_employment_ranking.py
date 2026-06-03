"""Tests for employment claim ranking and normalization."""

from datetime import UTC, date, datetime, timedelta

from contactsafe_server.db.models import EmploymentClaim
from contactsafe_server.services.employment_ranking import (
    normalize_employment_claims,
    rank_employment_claims,
    select_current_employment,
)


def _claim(
    *,
    source_kind: str,
    org_id: object = "org-a",
    confidence: float = 0.8,
    is_current: bool = True,
    observed_at: datetime | None = None,
    ended_at: date | None = None,
    started_at: date | None = None,
) -> EmploymentClaim:
    return EmploymentClaim(
        person_id="00000000-0000-0000-0000-000000000001",
        org_id=org_id,
        role_title="Role",
        is_current=is_current,
        started_at=started_at,
        ended_at=ended_at,
        contributor_source_kind=source_kind,
        confidence=confidence,
        observed_at=observed_at or datetime.now(tz=UTC),
    )


def test_linkedin_beats_heuristic() -> None:
    claims: list[EmploymentClaim] = [
        _claim(source_kind="heuristic", org_id="org-h", confidence=0.9),
        _claim(source_kind="linkedin_profile_upload", org_id="org-li", confidence=0.9),
    ]
    winner = select_current_employment(claims)
    assert winner is not None
    assert winner.claim.org_id == "org-li"


def test_stale_signature_loses_to_fresh_linkedin() -> None:
    old: datetime = datetime.now(tz=UTC) - timedelta(days=800)
    recent: datetime = datetime.now(tz=UTC) - timedelta(days=30)
    claims: list[EmploymentClaim] = [
        _claim(source_kind="gmail_signature", org_id="org-old", observed_at=old),
        _claim(
            source_kind="linkedin_connections_upload",
            org_id="org-li",
            observed_at=recent,
        ),
    ]
    winner = select_current_employment(
        claims,
        last_genuine_interaction_at=old,
    )
    assert winner is not None
    assert winner.claim.org_id == "org-li"


def test_fresh_signature_beats_linkedin() -> None:
    recent: datetime = datetime.now(tz=UTC) - timedelta(days=10)
    claims: list[EmploymentClaim] = [
        _claim(source_kind="gmail_signature", org_id="org-sig", observed_at=recent),
        _claim(
            source_kind="linkedin_connections_upload",
            org_id="org-li",
            observed_at=recent,
        ),
    ]
    winner = select_current_employment(
        claims,
        last_genuine_interaction_at=recent,
    )
    assert winner is not None
    assert winner.claim.org_id == "org-sig"


def test_normalize_demotes_losing_current_claims() -> None:
    today: date = date(2026, 6, 3)
    recent: datetime = datetime(2026, 5, 1, tzinfo=UTC)
    claims: list[EmploymentClaim] = [
        _claim(source_kind="heuristic", org_id="org-a", observed_at=recent),
        _claim(source_kind="exa", org_id="org-b", observed_at=recent),
    ]
    winner = normalize_employment_claims(claims, today=today)
    assert winner is not None
    assert winner.org_id == "org-b"
    assert claims[0].is_current is False
    assert claims[0].ended_at == today
    assert claims[1].is_current is True


def test_ended_at_in_past_not_current() -> None:
    today: date = date(2026, 6, 3)
    claims: list[EmploymentClaim] = [
        _claim(
            source_kind="linkedin_profile_upload",
            org_id="org-past",
            ended_at=date(2024, 1, 1),
        ),
    ]
    ranked = rank_employment_claims(claims, today=today)
    assert ranked[0].is_authoritative_current is False
    winner = select_current_employment(claims, today=today)
    assert winner is None
