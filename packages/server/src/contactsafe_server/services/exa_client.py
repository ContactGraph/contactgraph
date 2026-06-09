"""Async client for the Exa Search API."""

from typing import cast

import httpx

from contactsafe_server.config import Settings
from contactsafe_server.services.person_search_query import (
    build_activity_discovery_query,
    build_employer_discovery_query,
)
from contactsafe_server.services.web_search_types import ExaSearchCategory, WebSearchHit


class ExaClient:
    def __init__(self, settings: Settings) -> None:
        self._settings: Settings = settings
        self._api_key: str | None = settings.exa_api_key
        self._base_url: str = settings.exa_base_url.rstrip("/")
        self._timeout: float = settings.exa_request_timeout_seconds

    async def search_person_context(
        self,
        *,
        name: str,
        email: str,
        org_hint: str | None,
        category: ExaSearchCategory | None = "people",
        user_location: str | None = None,
        context_hints: list[str] | None = None,
    ) -> list[WebSearchHit]:
        if not self._api_key:
            return []

        query: str = build_employer_discovery_query(
            name,
            email,
            org_hint,
            user_location=user_location,
            context_hints=context_hints,
        )
        return await self._search(
            query=query,
            category=category,
            num_results=self._settings.exa_search_num_results,
        )

    async def search_person_activity(
        self,
        *,
        name: str,
        org_hint: str | None,
        user_location: str | None = None,
    ) -> list[WebSearchHit]:
        if not self._api_key:
            return []

        query: str = build_activity_discovery_query(
            name,
            org_hint,
            user_location=user_location,
        )
        return await self._search(
            query=query,
            category="personal_site",
            num_results=self._settings.exa_activity_search_num_results,
        )

    async def search_raw(
        self,
        *,
        query: str,
        num_results: int = 3,
    ) -> list[WebSearchHit]:
        if not self._api_key:
            return []
        return await self._search(
            query=query,
            category=None,
            num_results=num_results,
        )

    async def search_company_enrichment(
        self,
        *,
        query: str,
        summary_query: str,
        summary_schema: dict[str, object] | None = None,
        num_results: int = 5,
    ) -> list[WebSearchHit]:
        if not self._api_key:
            return []
        summary_config: dict[str, object] = {"query": summary_query}
        if summary_schema is not None:
            summary_config["schema"] = summary_schema
        return await self._search(
            query=query,
            category="company",
            num_results=num_results,
            contents={
                "text": {"maxCharacters": 2000},
                "highlights": True,
                "summary": summary_config,
            },
        )

    async def _search(
        self,
        *,
        query: str,
        category: ExaSearchCategory | None,
        num_results: int,
        contents: dict[str, object] | None = None,
    ) -> list[WebSearchHit]:
        payload: dict[str, object] = {
            "query": query,
            "type": "auto",
            "numResults": num_results,
            "contents": contents
            or {
                "text": {"maxCharacters": 2000},
                "highlights": True,
            },
        }
        if category is not None:
            payload["category"] = category

        async with httpx.AsyncClient(timeout=self._timeout) as http:
            response = await http.post(
                f"{self._base_url}/search",
                headers={
                    "x-api-key": self._api_key or "",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            response.raise_for_status()
            data: dict[str, object] = cast(dict[str, object], response.json())

        return _parse_results(data)


def _build_person_query(name: str, email: str, org_hint: str | None) -> str:
    """Backward-compatible query builder for tests."""
    return build_employer_discovery_query(name, email, org_hint)


def _parse_results(data: dict[str, object]) -> list[WebSearchHit]:
    results_raw: object = data.get("results")
    if not isinstance(results_raw, list):
        return []

    hits: list[WebSearchHit] = []
    items: list[object] = cast(list[object], results_raw)
    for item_raw in items:
        if not isinstance(item_raw, dict):
            continue
        item: dict[str, object] = cast(dict[str, object], item_raw)
        title_raw: object = item.get("title")
        url_raw: object = item.get("url")
        title: str = title_raw.strip() if isinstance(title_raw, str) else ""
        url: str = url_raw.strip() if isinstance(url_raw, str) else ""
        text_raw: object = item.get("text")
        text: str = text_raw[:2000] if isinstance(text_raw, str) else ""
        summary_raw: object = item.get("summary")
        summary: str = summary_raw.strip() if isinstance(summary_raw, str) else ""
        employee_count: int | None = _parse_employee_count(item)
        highlights: list[str] = []
        highlights_raw: object = item.get("highlights")
        if isinstance(highlights_raw, list):
            for hl_raw in cast(list[object], highlights_raw):
                if isinstance(hl_raw, str) and hl_raw.strip():
                    highlights.append(hl_raw.strip())
        if title or text or summary or highlights:
            hits.append(
                WebSearchHit(
                    title=title,
                    url=url,
                    text=text,
                    highlights=highlights,
                    summary=summary,
                    employee_count=employee_count,
                    provider="exa",
                )
            )
    return hits


def _parse_employee_count(item: dict[str, object]) -> int | None:
    entities_raw: object = item.get("entities")
    if not isinstance(entities_raw, list):
        return None
    for entity_raw in cast(list[object], entities_raw):
        if not isinstance(entity_raw, dict):
            continue
        entity: dict[str, object] = cast(dict[str, object], entity_raw)
        entity_type_raw: object = entity.get("type")
        if entity_type_raw != "company":
            continue
        properties_raw: object = entity.get("properties")
        if not isinstance(properties_raw, dict):
            continue
        properties: dict[str, object] = cast(dict[str, object], properties_raw)
        workforce_raw: object = properties.get("workforce")
        if not isinstance(workforce_raw, dict):
            continue
        workforce: dict[str, object] = cast(dict[str, object], workforce_raw)
        total_raw: object = workforce.get("total")
        if isinstance(total_raw, int) and total_raw > 0:
            return total_raw
        if isinstance(total_raw, float) and total_raw > 0:
            return int(total_raw)
    return None
