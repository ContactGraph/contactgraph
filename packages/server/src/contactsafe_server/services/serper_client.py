"""Async client for the Serper Google SERP API."""

from typing import cast

import httpx

from contactsafe_server.config import Settings
from contactsafe_server.services.person_search_query import (
    build_activity_discovery_query,
    build_employer_discovery_query,
)
from contactsafe_server.services.web_search_types import WebSearchHit


class SerperClient:
    def __init__(self, settings: Settings) -> None:
        self._settings: Settings = settings
        self._api_key: str | None = settings.serper_api_key
        self._base_url: str = settings.serper_base_url.rstrip("/")
        self._timeout: float = settings.serper_request_timeout_seconds

    async def search_person_context(
        self,
        *,
        name: str,
        email: str,
        org_hint: str | None,
    ) -> list[WebSearchHit]:
        query: str = build_employer_discovery_query(name, email, org_hint)
        return await self._search(query=query)

    async def search_person_activity(
        self,
        *,
        name: str,
        org_hint: str | None,
    ) -> list[WebSearchHit]:
        query: str = build_activity_discovery_query(name, org_hint)
        return await self._search(query=query)

    async def _search(self, *, query: str) -> list[WebSearchHit]:
        if not self._api_key:
            return []

        payload: dict[str, object] = {
            "q": query,
            "num": self._settings.serper_search_num_results,
        }

        async with httpx.AsyncClient(timeout=self._timeout) as http:
            response = await http.post(
                f"{self._base_url}/search",
                headers={
                    "X-API-KEY": self._api_key,
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            response.raise_for_status()
            data: dict[str, object] = cast(dict[str, object], response.json())

        return _parse_results(data)


def _parse_results(data: dict[str, object]) -> list[WebSearchHit]:
    organic_raw: object = data.get("organic")
    if not isinstance(organic_raw, list):
        return []

    hits: list[WebSearchHit] = []
    for item_raw in cast(list[object], organic_raw):
        if not isinstance(item_raw, dict):
            continue
        item: dict[str, object] = cast(dict[str, object], item_raw)
        title_raw: object = item.get("title")
        link_raw: object = item.get("link")
        snippet_raw: object = item.get("snippet")
        title: str = title_raw.strip() if isinstance(title_raw, str) else ""
        url: str = link_raw.strip() if isinstance(link_raw, str) else ""
        text: str = snippet_raw[:2000] if isinstance(snippet_raw, str) else ""
        if title or text:
            hits.append(
                WebSearchHit(
                    title=title,
                    url=url,
                    text=text,
                    highlights=[text] if text else [],
                    provider="serper",
                )
            )
    return hits
