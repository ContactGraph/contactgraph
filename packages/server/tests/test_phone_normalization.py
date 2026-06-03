"""Tests for phone number normalization."""

from contactsafe_server.services.phone_normalization import normalize_phone


def test_normalize_us_parentheses_format() -> None:
    assert normalize_phone("(415) 713-2682") == "+14157132682"


def test_normalize_e164_format() -> None:
    assert normalize_phone("+14157132682") == "+14157132682"


def test_normalize_spaced_country_code() -> None:
    assert normalize_phone("1 415-730-2685") == "+14157302685"
