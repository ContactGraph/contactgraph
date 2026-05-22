from contactsafe_server.services.pitch_detection import (
    is_pitch_outreach_snippet,
    message_from_user,
)


def test_message_from_user() -> None:
    assert message_from_user("Me <founder@startup.com>", "founder@startup.com")
    assert not message_from_user("VC <vc@fund.com>", "founder@startup.com")


def test_pitch_snippet_detected() -> None:
    assert is_pitch_outreach_snippet(
        "Would love 15 minutes to share our startup and send you our deck."
    )


def test_pitch_snippet_negative() -> None:
    assert not is_pitch_outreach_snippet("Thanks for lunch yesterday, see you soon!")
