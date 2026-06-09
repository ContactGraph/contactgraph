"""Tests for social profile platform normalization."""

from __future__ import annotations

from contactsafe_server.services.contacts_service import normalize_social_platform


def test_normalize_social_platform() -> None:
    assert normalize_social_platform("Twitter") == "twitter"
    assert normalize_social_platform("X / Twitter") == "x__twitter"
    assert normalize_social_platform("  Instagram  ") == "instagram"
    assert normalize_social_platform("LinkedIn") is None
    assert normalize_social_platform("") is None
