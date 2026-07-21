"""Unit tests for job relevance function-mismatch caps and preference fallback."""

from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

from contactsafe_server.db.models import User
from contactsafe_server.services.job_relevance_service import (
    JobRelevanceService,
    _cap_role_score_for_function_mismatch,
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
