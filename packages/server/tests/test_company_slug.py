"""Tests for company slug helpers."""

from contactsafe_server.services.company_slug import (
    company_slug,
    matches_company_slug,
)


def test_company_slug_from_name() -> None:
    assert company_slug("Baylor Genetics") == "baylor-genetics"


def test_matches_company_slug_by_name() -> None:
    assert matches_company_slug("baylor-genetics", "Baylor Genetics", None) is True


def test_matches_company_slug_by_domain() -> None:
    assert matches_company_slug("stripe", "Stripe, Inc.", "stripe.com") is True
