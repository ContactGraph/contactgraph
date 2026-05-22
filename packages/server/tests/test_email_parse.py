from contactsafe_server.services.email_parse import (
    company_query_from_question,
    normalize_email,
    parse_address_header,
)
from contactsafe_server.utils import parse_session_id


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


def test_parse_session_id_json_wrapper() -> None:
    import uuid

    sid = uuid.UUID("f2116602-d39b-4372-83e8-389f4c23bb73")
    assert parse_session_id('{"session_id": "f2116602-d39b-4372-83e8-389f4c23bb73"}') == sid
    assert parse_session_id("f2116602-d39b-4372-83e8-389f4c23bb73") == sid
