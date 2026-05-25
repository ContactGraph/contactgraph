"""Shared types for web-based person discovery enrichment."""

from dataclasses import dataclass
from typing import Literal

WebSearchProvider = Literal["exa", "tavily", "serper"]
ExaSearchCategory = Literal["people", "personal_site"]


@dataclass(frozen=True, slots=True)
class WebSearchHit:
    title: str
    url: str
    text: str
    highlights: list[str]
    provider: WebSearchProvider = "exa"


# Backward-compatible alias used by existing Exa tests and clients.
ExaSearchHit = WebSearchHit
