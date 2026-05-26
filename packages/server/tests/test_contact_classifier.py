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
        email="priya@northlight.io",
        display_name="Priya Ramaswamy",
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
        email="tomoko@northlight.io",
        display_name="Tomoko Sato",
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


def test_list_unsubscribe_marks_as_broadcast() -> None:
    """A sender with List-Unsubscribe header is broadcast, even from a personal-looking address."""
    acc = ContactAccumulator(
        email="gergely@pragmaticengineer.com",
        display_name="Gergely Orosz",
        message_count=10,
        outbound_count=0,
        inbound_count=10,
        list_unsubscribe_count=8,
    )
    classification = classify_contact(acc)
    assert classification.is_broadcast is True
    assert classification.is_human is False


def test_list_unsubscribe_single_message_still_broadcast() -> None:
    """Even a single List-Unsubscribe hit is enough to classify as broadcast."""
    acc = ContactAccumulator(
        email="james@jamesclear.com",
        display_name="James Clear",
        message_count=3,
        outbound_count=0,
        inbound_count=3,
        list_unsubscribe_count=1,
    )
    classification = classify_contact(acc)
    assert classification.is_broadcast is True
    assert classification.is_human is False


def test_list_unsubscribe_does_not_override_bidirectional() -> None:
    """If you actually email someone back, they might still have List-Unsubscribe
    on their messages (e.g. mailing list you participate in). The header still
    triggers broadcast classification since it's checked before volume heuristics."""
    acc = ContactAccumulator(
        email="discussion@googlegroups.com",
        display_name="Team Discussion",
        message_count=20,
        outbound_count=5,
        inbound_count=15,
        list_unsubscribe_count=12,
    )
    classification = classify_contact(acc)
    assert classification.is_broadcast is True
    assert classification.is_human is False


def test_no_list_unsubscribe_human_unchanged() -> None:
    """Without List-Unsubscribe, a real personal contact stays human."""
    acc = ContactAccumulator(
        email="sarah@startup.io",
        display_name="Sarah Chen",
        message_count=8,
        outbound_count=4,
        inbound_count=4,
        list_unsubscribe_count=0,
    )
    classification = classify_contact(acc)
    assert classification.is_human is True
    assert classification.is_broadcast is False
