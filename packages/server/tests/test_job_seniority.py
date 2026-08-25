"""Tests for deterministic seniority-level classification."""

from __future__ import annotations

from contactsafe_server.services.job_seniority import (
    SENIORITY_ASSOCIATE,
    SENIORITY_CLEVEL,
    SENIORITY_DIRECTOR,
    SENIORITY_ENTRY,
    SENIORITY_INTERN,
    SENIORITY_MANAGER,
    SENIORITY_MID,
    SENIORITY_SENIOR,
    SENIORITY_STAFF,
    SENIORITY_VP,
    classify_seniority_level,
    extract_target_seniority_range,
    seniority_range_score,
)


def test_director_of_sales_is_director_regardless_of_function() -> None:
    assert (
        classify_seniority_level("Director, Foundry Sales and Business Development")
        == SENIORITY_DIRECTOR
    )
    assert classify_seniority_level("Director of Product") == SENIORITY_DIRECTOR
    assert classify_seniority_level("Director of Software Engineering") == SENIORITY_DIRECTOR


def test_product_manager_is_mid_ic_not_people_manager() -> None:
    assert classify_seniority_level("Product Manager") == SENIORITY_MID
    assert classify_seniority_level("Senior Product Manager") == SENIORITY_SENIOR
    assert classify_seniority_level("Principal Product Manager") == SENIORITY_STAFF
    assert classify_seniority_level("Group Product Manager") == SENIORITY_STAFF
    assert classify_seniority_level("Associate Product Manager") == SENIORITY_ASSOCIATE


def test_true_people_managers() -> None:
    assert classify_seniority_level("Engineering Manager") == SENIORITY_MANAGER
    assert classify_seniority_level("Manager, Memory Sales") == SENIORITY_MANAGER


def test_vp_and_clevel() -> None:
    assert classify_seniority_level("VP of Engineering") == SENIORITY_VP
    assert classify_seniority_level("Head of Sales") == SENIORITY_VP
    assert classify_seniority_level("Chief Product Officer") == SENIORITY_CLEVEL
    assert classify_seniority_level("Founding CTO") == SENIORITY_CLEVEL


def test_senior_staff_entry_intern() -> None:
    assert classify_seniority_level("Senior Software Engineer") == SENIORITY_SENIOR
    assert classify_seniority_level("Staff Engineer") == SENIORITY_STAFF
    assert classify_seniority_level("Junior Analyst") == SENIORITY_ENTRY
    assert classify_seniority_level("Software Engineering Intern") == SENIORITY_INTERN


def test_unknown_returns_none() -> None:
    assert classify_seniority_level(None) is None
    assert classify_seniority_level("") is None
    assert classify_seniority_level("Specialist") is None


def test_seniority_range_score_inside_range_is_perfect() -> None:
    assert seniority_range_score(SENIORITY_STAFF, SENIORITY_STAFF, SENIORITY_STAFF) == 100
    assert seniority_range_score(SENIORITY_STAFF, SENIORITY_SENIOR, SENIORITY_DIRECTOR) == 100
    assert seniority_range_score(SENIORITY_DIRECTOR, SENIORITY_SENIOR, SENIORITY_DIRECTOR) == 100


def test_seniority_range_score_below_target_hurts_far_more_than_above() -> None:
    below: int = seniority_range_score(SENIORITY_SENIOR, SENIORITY_STAFF, SENIORITY_STAFF)
    above: int = seniority_range_score(SENIORITY_MANAGER, SENIORITY_STAFF, SENIORITY_STAFF)
    assert below < above
    assert below == 100 - 45
    assert above == 100 - 18


def test_under_leveled_pm_roles_are_knocked_out() -> None:
    """The complaint that started this: entry/mid PM roles for a Staff target."""
    mid: int = seniority_range_score(SENIORITY_MID, SENIORITY_STAFF, SENIORITY_STAFF)
    associate: int = seniority_range_score(
        SENIORITY_ASSOCIATE, SENIORITY_STAFF, SENIORITY_STAFF,
    )
    entry: int = seniority_range_score(SENIORITY_ENTRY, SENIORITY_STAFF, SENIORITY_STAFF)
    assert mid == 10
    assert associate == 0
    assert entry == 0


def test_stretch_roles_stay_visible() -> None:
    """Director/VP above a Staff target should still be surfaceable."""
    assert seniority_range_score(SENIORITY_DIRECTOR, SENIORITY_STAFF, SENIORITY_STAFF) == 64
    assert seniority_range_score(SENIORITY_VP, SENIORITY_STAFF, SENIORITY_STAFF) == 46


def test_seniority_range_score_neutral_when_unknown() -> None:
    assert seniority_range_score(None, SENIORITY_STAFF, SENIORITY_STAFF) == 85
    assert seniority_range_score(SENIORITY_STAFF, None, None) == 85
    assert seniority_range_score(None, None, None) == 85


def test_extract_target_range_from_preference_text() -> None:
    assert extract_target_seniority_range("Staff Product Manager") == (
        SENIORITY_STAFF,
        SENIORITY_STAFF,
    )
    assert extract_target_seniority_range("Staff / Principal Product Manager") == (
        SENIORITY_STAFF,
        SENIORITY_STAFF,
    )
    assert extract_target_seniority_range("Senior to Staff PM") == (
        SENIORITY_SENIOR,
        SENIORITY_STAFF,
    )
    assert extract_target_seniority_range("Director of Product, Head of Product") == (
        SENIORITY_DIRECTOR,
        SENIORITY_VP,
    )


def test_extract_target_range_returns_none_when_unlevelled() -> None:
    assert extract_target_seniority_range(None) is None
    assert extract_target_seniority_range("") is None
    assert extract_target_seniority_range("fintech, developer tools") is None


def test_customer_service_and_sales_levels() -> None:
    assert classify_seniority_level("Customer Service Representative") is None
    assert classify_seniority_level("Senior Customer Success Manager") == SENIORITY_SENIOR
    assert (
        classify_seniority_level("Global Head of Sales & Partner Enablement")
        == SENIORITY_VP
    )
