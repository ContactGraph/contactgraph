import pytest

from contactsafe_server.services.exa_client import ExaClient, _parse_results
from contactsafe_server.services.person_search_query import (
    build_activity_discovery_query,
    build_employer_discovery_query,
)
from contactsafe_server.services.platform_activity import (
    PlatformPost,
    _extract_bluesky_handle,
    _extract_github_login,
    posts_to_activity_blob,
)
from contactsafe_server.services.signature_enrichment import parse_signature_from_snippets
from contactsafe_server.services.web_enrichment import extract_hints_from_web_hits
from contactsafe_server.services.web_search_types import WebSearchHit


def test_build_employer_discovery_query_includes_domain() -> None:
    query: str = build_employer_discovery_query("Jane Doe", "jane@acmeventures.com", "Acme Ventures")
    assert "Jane Doe" in query
    assert "acmeventures.com" in query
    assert "investor" not in query


def test_build_employer_discovery_query_includes_location_and_context() -> None:
    query: str = build_employer_discovery_query(
        "Jane Doe",
        "jane@gmail.com",
        None,
        user_location="San Francisco, CA",
        context_hints=["Lincoln Elementary"],
    )
    assert "San Francisco" in query
    assert "Lincoln Elementary" in query


def test_build_activity_discovery_query() -> None:
    query: str = build_activity_discovery_query("Jane Doe", "Acme Ventures", user_location="Boston")
    assert "bluesky" in query
    assert "Boston" in query


def test_exa_parse_results_with_provider() -> None:
    data: dict[str, object] = {
        "results": [
            {
                "title": "Jane Doe - General Partner - Acme Ventures",
                "url": "https://linkedin.com/in/janedoe",
                "text": "Jane Doe is a General Partner at Acme Ventures.",
                "highlights": ["venture capital investor"],
                "summary": "Jane Doe is a venture capital investor at Acme Ventures.",
            }
        ]
    }
    hits = _parse_results(data)
    assert len(hits) == 1
    assert hits[0].provider == "exa"
    assert hits[0].summary == "Jane Doe is a venture capital investor at Acme Ventures."


def test_tavily_parse_results() -> None:
    data: dict[str, object] = {
        "results": [
            {
                "title": "Jane at Acme",
                "url": "https://example.com/jane",
                "content": "Partner at Acme Ventures",
            }
        ]
    }
    from contactsafe_server.services.tavily_client import _parse_results as tavily_parse

    hits = tavily_parse(data)
    assert hits[0].provider == "tavily"
    assert "Acme" in hits[0].text


def test_serper_parse_results() -> None:
    data: dict[str, object] = {
        "organic": [
            {
                "title": "Jane Doe | GitHub",
                "link": "https://github.com/janedoe",
                "snippet": "Engineer at Acme",
            }
        ]
    }
    from contactsafe_server.services.serper_client import _parse_results as serper_parse

    hits = serper_parse(data)
    assert hits[0].provider == "serper"
    assert hits[0].url.endswith("/janedoe")


def test_extract_social_profiles_from_hits() -> None:
    hits: list[WebSearchHit] = [
        WebSearchHit(
            title="Jane on GitHub",
            url="https://github.com/janedoe",
            text="",
            highlights=[],
            provider="serper",
        ),
        WebSearchHit(
            title="Jane on Bluesky",
            url="https://bsky.app/profile/jane.bsky.social",
            text="",
            highlights=[],
            provider="serper",
        ),
    ]
    hints = extract_hints_from_web_hits(
        hits=hits,
        email="jane@gmail.com",
        display_name="Jane Doe",
        org_hint=None,
    )
    assert hints.social_profiles["github"].endswith("/janedoe")
    assert "bluesky" in hints.social_profiles


def test_signature_parse_role_and_org() -> None:
    hints = parse_signature_from_snippets(
        ["Thanks!\nAlex Kim\nFounder at Launchpad Labs"],
        display_name="Alex Kim",
    )
    assert hints.current_role == "Founder"
    assert hints.org_name == "Launchpad Labs"


def test_platform_handle_extraction() -> None:
    assert _extract_github_login("https://github.com/octocat") == "octocat"
    assert _extract_bluesky_handle("https://bsky.app/profile/alice.bsky.social") == "alice.bsky.social"


def test_posts_to_activity_blob() -> None:
    blob: str = posts_to_activity_blob(
        [
            PlatformPost(platform="bluesky", text="Shipping v2 today", url="https://bsky.app"),
            PlatformPost(platform="github", text="PushEvent: org/repo", url="https://github.com/x"),
        ]
    )
    assert "bluesky" in blob
    assert "github" in blob


@pytest.mark.asyncio
async def test_exa_client_includes_category(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EXA_API_KEY", "test-key")
    from contactsafe_server.config import get_settings

    get_settings.cache_clear()
    settings = get_settings()
    client = ExaClient(settings)

    captured: dict[str, object] = {}

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {"results": []}

    class FakeHttp:
        async def __aenter__(self) -> "FakeHttp":
            return self

        async def __aexit__(self, *args: object) -> None:
            return None

        async def post(self, url: str, *, headers: dict[str, str], json: dict[str, object]) -> FakeResponse:
            captured["url"] = url
            captured["payload"] = json
            return FakeResponse()

    import contactsafe_server.services.exa_client as exa_module

    monkeypatch.setattr(exa_module.httpx, "AsyncClient", lambda **kwargs: FakeHttp())

    await client.search_person_context(
        name="Jane Doe",
        email="jane@acme.com",
        org_hint="Acme",
        category="people",
    )
    payload = captured["payload"]
    assert isinstance(payload, dict)
    assert payload.get("category") == "people"
