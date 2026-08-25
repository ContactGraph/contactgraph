import pytest
from contactsafe_server.services.ats_detection import (
    FetchedPage,
    candidate_board_tokens,
    detect_ats_by_probe,
    detect_ats_from_page,
    detect_ats_from_url,
)


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


# --- Layer 2: detect_ats_from_page (looking through vanity careers domains) ---


def _fake_fetcher(final_url: str, body: str):
    async def fetch(_url: str) -> FetchedPage:
        return FetchedPage(final_url=final_url, body=body)

    return fetch


@pytest.mark.asyncio
async def test_page_detects_greenhouse_from_body_links() -> None:
    # Mercury-style: careers page stays on the vanity domain but links out to the
    # real Greenhouse board in its body.
    body = """
    <a href="https://job-boards.greenhouse.io/mercury/jobs/5867562004">Staff PM</a>
    <a href="https://job-boards.greenhouse.io/mercury/jobs/5922062004">Senior PM</a>
    """
    result = await detect_ats_from_page(
        "https://mercury.com/jobs",
        fetch=_fake_fetcher("https://mercury.com/jobs", body),
    )
    assert result.provider == "greenhouse"
    assert result.board_token == "mercury"


@pytest.mark.asyncio
async def test_page_detects_greenhouse_from_embed_script() -> None:
    body = (
        '<script src="https://boards.greenhouse.io/embed/job_board/js?for=airbnb">'
        "</script>"
    )
    result = await detect_ats_from_page(
        "https://careers.airbnb.com",
        fetch=_fake_fetcher("https://careers.airbnb.com", body),
    )
    assert result.provider == "greenhouse"
    assert result.board_token == "airbnb"


@pytest.mark.asyncio
async def test_page_detects_ats_from_redirect() -> None:
    # Vanity domain that redirects onto the ATS host: detect from the final URL,
    # even if the body has no useful links.
    result = await detect_ats_from_page(
        "https://careers.palantir.com",
        fetch=_fake_fetcher("https://jobs.lever.co/palantir", "<html></html>"),
    )
    assert result.provider == "lever"
    assert result.board_token == "palantir"


@pytest.mark.asyncio
async def test_page_ignores_greenhouse_embed_scaffolding_slug() -> None:
    # The literal "/embed/job_board" path must not be mistaken for a board token;
    # the real token comes from ?for=.
    body = (
        '<iframe src="https://boards.greenhouse.io/embed/job_board?for=notion">'
        "</iframe>"
    )
    result = await detect_ats_from_page(
        "https://notion.so/careers",
        fetch=_fake_fetcher("https://notion.so/careers", body),
    )
    assert result.provider == "greenhouse"
    assert result.board_token == "notion"


@pytest.mark.asyncio
async def test_page_returns_empty_when_no_ats_present() -> None:
    result = await detect_ats_from_page(
        "https://example.com/careers",
        fetch=_fake_fetcher("https://example.com/careers", "<html>no ats here</html>"),
    )
    assert result.provider is None
    assert result.board_token is None


@pytest.mark.asyncio
async def test_page_swallows_fetch_errors() -> None:
    async def boom(_url: str) -> FetchedPage:
        raise RuntimeError("network down")

    result = await detect_ats_from_page("https://mercury.com/jobs", fetch=boom)
    assert result.provider is None
    assert result.board_token is None


# --- Layer 3: detect_ats_by_probe (client-rendered careers sites) ---


def test_candidate_tokens_from_domain_and_name() -> None:
    tokens = candidate_board_tokens("HubSpot", "https://www.hubspot.com/careers")
    assert tokens[0] == "hubspot"
    assert "hubspotjobs" in tokens


def test_candidate_tokens_strip_corporate_noise() -> None:
    tokens = candidate_board_tokens("Acme Technologies, Inc.", None)
    assert "acme" in tokens


def test_candidate_tokens_ignore_generic_subdomains() -> None:
    # jobs.example.com must not yield the token "jobs".
    tokens = candidate_board_tokens(None, "https://jobs.example.com")
    assert "jobs" not in tokens


def test_candidate_tokens_empty_without_inputs() -> None:
    assert candidate_board_tokens(None, None) == []


def _probe_returning(counts: dict[str, int]):
    """Probe stub keyed by the token embedded in the requested URL."""

    async def probe(_provider: str, url: str) -> int:
        for token, count in counts.items():
            if f"/{token}/" in url or url.endswith(f"/{token}") or f"/{token}?" in url:
                return count
        return 0

    return probe


@pytest.mark.asyncio
async def test_probe_skips_empty_board_and_finds_real_one() -> None:
    """HubSpot's "hubspot" board answers 200 with zero jobs; the real one is
    "hubspotjobs". Existence alone must not win."""
    result = await detect_ats_by_probe(
        "HubSpot",
        "https://www.hubspot.com/careers",
        probe=_probe_returning({"hubspot": 0, "hubspotjobs": 155}),
    )
    assert result.provider == "greenhouse"
    assert result.board_token == "hubspotjobs"


@pytest.mark.asyncio
async def test_probe_returns_empty_when_nothing_matches() -> None:
    result = await detect_ats_by_probe(
        "Nonesuch",
        "https://nonesuch.example/careers",
        probe=_probe_returning({}),
    )
    assert result.provider is None
    assert result.board_token is None


@pytest.mark.asyncio
async def test_probe_swallows_errors() -> None:
    async def boom(_provider: str, _url: str) -> int:
        raise RuntimeError("network down")

    result = await detect_ats_by_probe("HubSpot", "https://hubspot.com/careers", probe=boom)
    assert result.provider is None
    assert result.board_token is None


@pytest.mark.asyncio
async def test_probe_respects_call_cap() -> None:
    calls: list[str] = []

    async def counting(_provider: str, url: str) -> int:
        calls.append(url)
        return 0

    await detect_ats_by_probe("HubSpot", "https://www.hubspot.com/careers", probe=counting)
    assert len(calls) <= 12
