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
    seniority_match_score,
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


def test_seniority_match_score_exact() -> None:
    assert seniority_match_score(SENIORITY_DIRECTOR, SENIORITY_DIRECTOR) == 100


def test_seniority_match_score_under_qualified_hurts_more() -> None:
    under: int = seniority_match_score(SENIORITY_DIRECTOR, SENIORITY_MID)
    over: int = seniority_match_score(SENIORITY_MID, SENIORITY_DIRECTOR)
    assert under < over
    assert under == 100 - 22 * (SENIORITY_DIRECTOR - SENIORITY_MID)
    assert over == 100 - 12 * (SENIORITY_DIRECTOR - SENIORITY_MID)


def test_seniority_match_score_neutral_when_unknown() -> None:
    assert seniority_match_score(None, SENIORITY_SENIOR) == 70
    assert seniority_match_score(SENIORITY_SENIOR, None) == 70
    assert seniority_match_score(None, None) == 70


def test_customer_service_and_sales_levels() -> None:
    assert classify_seniority_level("Customer Service Representative") is None
    assert classify_seniority_level("Senior Customer Success Manager") == SENIORITY_SENIOR
    assert (
        classify_seniority_level("Global Head of Sales & Partner Enablement")
        == SENIORITY_VP
    )
