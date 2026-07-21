"""Unit tests for job relevance caps and conjunctive match scoring."""

from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

from contactsafe_server.db.models import User
from contactsafe_server.services.job_relevance_service import (
    DEFAULT_SCORING_WEIGHTS,
    JobRelevanceService,
    _cap_role_score_for_function_mismatch,
    compute_match_score,
    resolve_scoring_weights,
    stage_match_factor,
)


def _job(title: str, department: str | None = None) -> SimpleNamespace:
    return SimpleNamespace(title=title, department=department)


def test_cap_product_designer_for_pm_preference() -> None:
    score, reason = _cap_role_score_for_function_mismatch(
        "Looking for product manager roles",
        _job("Senior Product Designer"),  # type: ignore[arg-type]
        85,
        "Shares product keyword",
    )
    assert score == 15
    assert reason is not None
    assert "design" in reason.lower()


def test_cap_product_analyst_for_pm_preference() -> None:
    score, reason = _cap_role_score_for_function_mismatch(
        "PM roles in B2B SaaS",
        _job("Product Analyst"),  # type: ignore[arg-type]
        78,
        None,
    )
    assert score == 20
    assert reason is not None
    assert "analytics" in reason.lower()


def test_cap_paralegal_for_pm_preference() -> None:
    score, reason = _cap_role_score_for_function_mismatch(
        "product management",
        _job("Paralegal"),  # type: ignore[arg-type]
        60,
        None,
    )
    assert score == 10
    assert reason is not None
    assert "legal" in reason.lower()


def test_cap_leaves_true_pm_title_alone() -> None:
    score, reason = _cap_role_score_for_function_mismatch(
        "product manager",
        _job("Senior Product Manager"),  # type: ignore[arg-type]
        92,
        "Good match",
    )
    assert score == 92
    assert reason == "Good match"


def test_cap_noop_without_pm_preference() -> None:
    score, reason = _cap_role_score_for_function_mismatch(
        "backend engineer roles",
        _job("Product Designer"),  # type: ignore[arg-type]
        80,
        "ok",
    )
    assert score == 80
    assert reason == "ok"


def test_effective_role_text_prefers_explicit() -> None:
    user = User(
        id=uuid4(),
        email="a@example.com",
        job_preferences_text="  Senior PM  ",
        job_suggested_roles="Staff engineer roles",
    )
    assert JobRelevanceService._effective_role_text(user) == "Senior PM"


def test_effective_role_text_falls_back_to_suggested() -> None:
    user = User(
        id=uuid4(),
        email="a@example.com",
        job_preferences_text=None,
        job_suggested_roles="  Senior product manager roles  ",
    )
    assert (
        JobRelevanceService._effective_role_text(user)
        == "Senior product manager roles"
    )


def test_effective_role_text_none_when_empty() -> None:
    user = User(id=uuid4(), email="a@example.com")
    assert JobRelevanceService._effective_role_text(user) is None


def test_resolve_scoring_weights_defaults() -> None:
    assert resolve_scoring_weights(None) == DEFAULT_SCORING_WEIGHTS


def test_resolve_scoring_weights_merges_and_clamps() -> None:
    resolved = resolve_scoring_weights({"role": 0.5, "location": 2.0, "seniority": -1})
    assert resolved["role"] == 0.5
    assert resolved["location"] == 1.0
    assert resolved["seniority"] == 0.0
    assert resolved["qualification"] == DEFAULT_SCORING_WEIGHTS["qualification"]


def test_compute_match_score_hard_gate() -> None:
    score, note = compute_match_score(
        role_score=100,
        qualification_score=100,
        seniority_score=100,
        location_score=0,
        weights={**DEFAULT_SCORING_WEIGHTS, "location": 1.0},
        stage_factor=1.0,
    )
    assert score == 0
    assert note is not None
    assert "location" in note


def test_compute_match_score_weight_zero_ignores_dimension() -> None:
    score, _note = compute_match_score(
        role_score=100,
        qualification_score=100,
        seniority_score=100,
        location_score=0,
        weights={**DEFAULT_SCORING_WEIGHTS, "location": 0.0},
        stage_factor=1.0,
    )
    assert score == 100


def test_compute_match_score_partial_knockout() -> None:
    score, _note = compute_match_score(
        role_score=100,
        qualification_score=100,
        seniority_score=100,
        location_score=0,
        weights={**DEFAULT_SCORING_WEIGHTS, "location": 0.5},
        stage_factor=1.0,
    )
    assert score == 50


def test_compute_match_score_all_high_in_expected_band() -> None:
    score, note = compute_match_score(
        role_score=90,
        qualification_score=90,
        seniority_score=90,
        location_score=90,
        weights=DEFAULT_SCORING_WEIGHTS,
        stage_factor=1.0,
    )
    assert 55 <= score <= 90
    assert note is None or "Limited by" in note


def test_stage_match_factor_neutral_without_preference() -> None:
    assert (
        stage_match_factor(
            org_funding_stage="series_b",
            preferred_funding_stages=None,
            weight=0.7,
        )
        == 1.0
    )


def test_stage_match_factor_neutral_when_unknown() -> None:
    assert (
        stage_match_factor(
            org_funding_stage=None,
            preferred_funding_stages=["series_a"],
            weight=0.7,
        )
        == 1.0
    )
    assert (
        stage_match_factor(
            org_funding_stage="unknown",
            preferred_funding_stages=["series_a"],
            weight=1.0,
        )
        == 1.0
    )


def test_stage_match_factor_penalizes_mismatch() -> None:
    factor = stage_match_factor(
        org_funding_stage="public",
        preferred_funding_stages=["series_a", "series_b"],
        weight=0.7,
    )
    assert abs(factor - 0.3) < 1e-9


def test_stage_match_factor_matches_preferred() -> None:
    assert (
        stage_match_factor(
            org_funding_stage="series_b",
            preferred_funding_stages=["series_a", "series_b"],
            weight=0.7,
        )
        == 1.0
    )


def test_compute_match_score_with_stage_mismatch() -> None:
    score_match, _ = compute_match_score(
        role_score=100,
        qualification_score=100,
        seniority_score=100,
        location_score=100,
        weights=DEFAULT_SCORING_WEIGHTS,
        stage_factor=1.0,
    )
    score_miss, note = compute_match_score(
        role_score=100,
        qualification_score=100,
        seniority_score=100,
        location_score=100,
        weights=DEFAULT_SCORING_WEIGHTS,
        stage_factor=stage_match_factor(
            org_funding_stage="public",
            preferred_funding_stages=["seed"],
            weight=DEFAULT_SCORING_WEIGHTS["funding_stage"],
        ),
    )
    assert score_match == 100
    assert score_miss == 30
    assert note is not None
    assert "funding stage" in note
