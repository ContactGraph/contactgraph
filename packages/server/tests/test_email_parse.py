from contactsafe_server.services.email_parse import (
    company_query_from_question,
    is_valid_person_name,
    name_query_from_question,
    normalize_email,
    parse_address_header,
    person_matches_name,
    sanitize_display_name,
)
from contactsafe_server.utils import parse_connect_session_id


def test_normalize_email_filters_noreply() -> None:
    assert normalize_email("noreply@stripe.com") is None
    assert normalize_email("Alice@Stripe.COM") == "alice@stripe.com"


def test_parse_address_header() -> None:
    pairs = parse_address_header("Alice Smith <alice@example.com>, Bob <bob@corp.com>")
    emails = {email for _, email in pairs}
    assert emails == {"alice@example.com", "bob@corp.com"}


def test_company_query_from_question() -> None:
    assert company_query_from_question("Who do I know at Stripe?") == "Stripe"
    assert company_query_from_question("hello world") is None


def test_name_query_from_question() -> None:
    assert name_query_from_question("Who do I know named Chris?") == "Chris"
    assert name_query_from_question("who is Christopher Lee") == "Christopher Lee"


def test_name_tokens_from_proper_nouns() -> None:
    from contactsafe_server.services.email_parse import name_tokens_from_proper_nouns

    assert name_tokens_from_proper_nouns("Cynthia Johanson") == ["cynthia", "johanson"]
    assert name_tokens_from_proper_nouns("What VCs do I know?") == []


def test_email_lookup_variants_merges_apple_domains() -> None:
    from contactsafe_server.services.email_parse import email_lookup_variants

    variants = email_lookup_variants("pmnorwood@mac.com")
    assert "pmnorwood@mac.com" in variants
    assert "pmnorwood@icloud.com" in variants


def test_is_likely_self_contact_matches_owned_addresses() -> None:
    from contactsafe_server.services.email_parse import is_likely_self_contact

    assert is_likely_self_contact(
        "teg@basebase.com",
        user_emails={"teg@gmail.com"},
        user_local_parts={"teg"},
    )


def test_person_matches_name() -> None:
    assert person_matches_name("Chris Pappas", ["teampappas@e.chrispappas.org"], "Chris")
    assert not person_matches_name("Sam Harris", ["team@news.samharris.org"], "Chris")


def test_parse_connect_session_id_json_wrapper() -> None:
    import uuid

    sid = uuid.UUID("f2116602-d39b-4372-83e8-389f4c23bb73")
    assert (
        parse_connect_session_id('{"connect_session_id": "f2116602-d39b-4372-83e8-389f4c23bb73"}')
        == sid
    )
    assert parse_connect_session_id("f2116602-d39b-4372-83e8-389f4c23bb73") == sid


def test_is_valid_person_name_rejects_header_artifacts() -> None:
    assert is_valid_person_name("Customer_Service") is False
    assert is_valid_person_name("Subscribed") is False
    assert is_valid_person_name("Ci activity") is False
    assert is_valid_person_name("Reed Grenager") is True


def test_sanitize_display_name_falls_back_to_email() -> None:
    assert sanitize_display_name("Push", "push@noreply.github.com") == "push@noreply.github.com"
    assert sanitize_display_name("Jane Doe", "jane@example.com") == "Jane Doe"
