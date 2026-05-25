import pytest

from contactsafe_server.services.person_discovery_service import PersonDiscoveryService
from contactsafe_server.services.web_search_types import WebSearchHit


@pytest.mark.asyncio
async def test_discovery_falls_back_to_tavily(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EXA_API_KEY", "exa-key")
    monkeypatch.setenv("TAVILY_API_KEY", "tavily-key")
    from contactsafe_server.config import get_settings

    get_settings.cache_clear()
    settings = get_settings()
    service = PersonDiscoveryService(settings)

    exa_hits: list[WebSearchHit] = []
    tavily_hits: list[WebSearchHit] = [
        WebSearchHit(
            title="Jane - Partner - Acme",
            url="https://example.com",
            text="Partner at Acme Ventures",
            highlights=[],
            provider="tavily",
        )
    ]

    async def fake_exa_employer(**kwargs: object) -> list[WebSearchHit]:
        return exa_hits

    async def fake_tavily_employer(**kwargs: object) -> list[WebSearchHit]:
        return tavily_hits

    async def fake_activity(**kwargs: object) -> list[WebSearchHit]:
        return []

    monkeypatch.setattr(service._exa, "search_person_context", fake_exa_employer)
    monkeypatch.setattr(service._tavily, "search_person_context", fake_tavily_employer)
    monkeypatch.setattr(service._exa, "search_person_activity", fake_activity)
    monkeypatch.setattr(service._tavily, "search_person_activity", fake_activity)
    monkeypatch.setattr(service._serper, "search_person_context", fake_activity)
    monkeypatch.setattr(service._serper, "search_person_activity", fake_activity)

    result = await service.discover_person(
        name="Jane Doe",
        email="jane@gmail.com",
        org_hint=None,
    )
    assert result.employer_hits == tavily_hits
    assert "tavily" in result.providers_used
