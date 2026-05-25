"""Smoke tests for web search hint extraction (formerly exa-only)."""

from contactsafe_server.services.web_search_types import WebSearchHit
from contactsafe_server.services.web_enrichment import (
    extract_hints_from_web_hits,
)


def test_extract_category_from_hit() -> None:
    hit = WebSearchHit(
        title="Jane Doe - Partner at Horizon Capital",
        url="https://linkedin.com/in/janedoe",
        text="Jane Doe is a Partner and Investor at Horizon Capital",
        highlights=["Partner at Horizon Capital"],
    )
    hints = extract_hints_from_web_hits(
        hits=[hit],
        email="jane@horizoncapital.com",
        display_name="Jane Doe",
        org_hint=None,
    )
    assert "vc" in hints.categories
    assert hints.current_role is not None
