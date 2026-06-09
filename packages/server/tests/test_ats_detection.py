from contactsafe_server.services.ats_detection import detect_ats_from_url


def test_detect_greenhouse_from_careers_url() -> None:
    result = detect_ats_from_url("https://boards.greenhouse.io/stripe/jobs")
    assert result.provider == "greenhouse"
    assert result.board_token == "stripe"


def test_detect_lever_from_careers_url() -> None:
    result = detect_ats_from_url("https://jobs.lever.co/palantir")
    assert result.provider == "lever"
    assert result.board_token == "palantir"


def test_detect_ashby_from_careers_url() -> None:
    result = detect_ats_from_url("https://jobs.ashbyhq.com/openai")
    assert result.provider == "ashby"
    assert result.board_token == "openai"


def test_detect_unknown_careers_url() -> None:
    result = detect_ats_from_url("https://example.com/careers")
    assert result.provider is None
    assert result.board_token is None
