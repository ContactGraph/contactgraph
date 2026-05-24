from contactsafe_server.services.contact_classifier import (
    classify_contact,
    compute_tie_strength,
)
from contactsafe_server.services.email_parse import ContactAccumulator


def test_github_bot_is_automated() -> None:
    acc = ContactAccumulator(
        email="ci_activity@noreply.github.com",
        display_name="Ci activity",
        message_count=17,
        outbound_count=17,
        inbound_count=0,
    )
    classification = classify_contact(acc)
    assert classification.is_automated is True
    assert classification.is_human is False
    assert compute_tie_strength(acc, classification) < 0.1


def test_bidirectional_human_contact() -> None:
    acc = ContactAccumulator(
        email="vincent@basebase.com",
        display_name="Vincent Bannister",
        message_count=6,
        outbound_count=3,
        inbound_count=3,
    )
    classification = classify_contact(acc)
    assert classification.is_automated is False
    assert classification.is_human is True
    score: float = compute_tie_strength(acc, classification)
    assert 0.3 < score < 1.0


def test_high_volume_human_does_not_saturate_to_one() -> None:
    acc = ContactAccumulator(
        email="friend@company.com",
        display_name="Friend",
        message_count=50,
        outbound_count=25,
        inbound_count=25,
    )
    classification = classify_contact(acc)
    score: float = compute_tie_strength(acc, classification)
    assert score < 1.0


def test_customer_service_mailbox_capped() -> None:
    acc = ContactAccumulator(
        email="customer_service@company.com",
        display_name="Customer Service",
        message_count=20,
        outbound_count=0,
        inbound_count=20,
    )
    classification = classify_contact(acc)
    assert compute_tie_strength(acc, classification) <= 0.15


def test_newsletter_is_broadcast() -> None:
    acc = ContactAccumulator(
        email="hello@theinformation.com",
        display_name="The Information",
        message_count=25,
        outbound_count=0,
        inbound_count=25,
    )
    classification = classify_contact(acc)
    assert classification.is_broadcast is True
    assert classification.is_human is False


def test_capital_one_is_automated_or_broadcast() -> None:
    acc = ContactAccumulator(
        email="rewards@communication.capitalone.com",
        display_name="Capital One",
        message_count=5,
        outbound_count=0,
        inbound_count=5,
    )
    classification = classify_contact(acc)
    assert classification.is_human is False


def test_outbound_only_contact_is_human() -> None:
    acc = ContactAccumulator(
        email="cynthia@basebase.com",
        display_name="Cynthia Johanson",
        message_count=3,
        outbound_count=3,
        inbound_count=0,
    )
    classification = classify_contact(acc)
    assert classification.is_automated is False
    assert classification.is_broadcast is False
    assert classification.is_human is True


def test_info_mailbox_is_broadcast() -> None:
    acc = ContactAccumulator(
        email="info@wayfair.com",
        display_name="Wayfair",
        message_count=2,
        outbound_count=0,
        inbound_count=2,
    )
    classification = classify_contact(acc)
    assert classification.is_broadcast is True
    assert classification.is_human is False
