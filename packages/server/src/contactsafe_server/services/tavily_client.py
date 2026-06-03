"""Async client for the Tavily Search API."""

from typing import cast

import httpx

from contactsafe_server.config import Settings
from contactsafe_server.services.person_search_query import (
    build_activity_discovery_query,
    build_employer_discovery_query,
)
from contactsafe_server.services.web_search_types import WebSearchHit


class TavilyClient:
    def __init__(self, settings: Settings) -> None:
        self._settings: Settings = settings
        self._api_key: str | None = settings.tavily_api_key
        self._base_url: str = settings.tavily_base_url.rstrip("/")
        self._timeout: float = settings.tavily_request_timeout_seconds

    async def search_person_context(
        self,
        *,
        name: str,
        email: str,
        org_hint: str | None,
        user_location: str | None = None,
        context_hints: list[str] | None = None,
    ) -> list[WebSearchHit]:
        query: str = build_employer_discovery_query(
            name,
            email,
            org_hint,
            user_location=user_location,
            context_hints=context_hints,
        )
        return await self._search(query=query)

    async def search_person_activity(
        self,
        *,
        name: str,
        org_hint: str | None,
        user_location: str | None = None,
    ) -> list[WebSearchHit]:
        query: str = build_activity_discovery_query(
            name,
            org_hint,
            user_location=user_location,
        )
        return await self._search(query=query)

    async def search_raw(self, *, query: str) -> list[WebSearchHit]:
        return await self._search(query=query)

    async def _search(self, *, query: str) -> list[WebSearchHit]:
        if not self._api_key:
            return []

        payload: dict[str, object] = {
            "api_key": self._api_key,
            "query": query,
            "search_depth": self._settings.tavily_search_depth,
            "max_results": self._settings.tavily_search_num_results,
            "include_answer": False,
            "include_raw_content": False,
        }

        async with httpx.AsyncClient(timeout=self._timeout) as http:
            response = await http.post(
                f"{self._base_url}/search",
                headers={"Content-Type": "application/json"},
                json=payload,
            )
            response.raise_for_status()
            data: dict[str, object] = cast(dict[str, object], response.json())

        return _parse_results(data)


def _parse_results(data: dict[str, object]) -> list[WebSearchHit]:
    results_raw: object = data.get("results")
    if not isinstance(results_raw, list):
        return []

    hits: list[WebSearchHit] = []
    for item_raw in cast(list[object], results_raw):
        if not isinstance(item_raw, dict):
            continue
        item: dict[str, object] = cast(dict[str, object], item_raw)
        title_raw: object = item.get("title")
        url_raw: object = item.get("url")
        content_raw: object = item.get("content")
        title: str = title_raw.strip() if isinstance(title_raw, str) else ""
        url: str = url_raw.strip() if isinstance(url_raw, str) else ""
        text: str = content_raw[:2000] if isinstance(content_raw, str) else ""
        if title or text:
            hits.append(
                WebSearchHit(
                    title=title,
                    url=url,
                    text=text,
                    highlights=[text[:500]] if text else [],
                    provider="tavily",
                )
            )
    return hits
