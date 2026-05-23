"""Async client for the Exa Search API."""

from dataclasses import dataclass
from typing import cast

import httpx

from contactsafe_server.config import Settings

_GENERIC_EMAIL_DOMAINS: frozenset[str] = frozenset(
    {
        "gmail.com",
        "googlemail.com",
        "yahoo.com",
        "hotmail.com",
        "outlook.com",
        "icloud.com",
        "me.com",
        "live.com",
        "protonmail.com",
        "fastmail.com",
    }
)


@dataclass(frozen=True, slots=True)
class ExaSearchHit:
    title: str
    url: str
    text: str
    highlights: list[str]


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
    ) -> list[ExaSearchHit]:
        if not self._api_key:
            return []

        query: str = _build_person_query(name, email, org_hint)
        payload: dict[str, object] = {
            "query": query,
            "type": "auto",
            "numResults": self._settings.exa_search_num_results,
            "contents": {
                "text": {"maxCharacters": 2000},
                "highlights": True,
            },
        }

        async with httpx.AsyncClient(timeout=self._timeout) as http:
            response = await http.post(
                f"{self._base_url}/search",
                headers={
                    "x-api-key": self._api_key,
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            response.raise_for_status()
            data: dict[str, object] = cast(dict[str, object], response.json())

        return _parse_results(data)


def _build_person_query(name: str, email: str, org_hint: str | None) -> str:
    parts: list[str] = [f'"{name.strip()}"']
    if org_hint and org_hint.strip():
        parts.append(org_hint.strip())
    if "@" in email:
        domain: str = email.rsplit("@", 1)[1].lower()
        if domain not in _GENERIC_EMAIL_DOMAINS:
            parts.append(domain)
    parts.append("job title role investor venture capital partner")
    return " ".join(parts)


def _parse_results(data: dict[str, object]) -> list[ExaSearchHit]:
    results_raw: object = data.get("results")
    if not isinstance(results_raw, list):
        return []

    hits: list[ExaSearchHit] = []
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
        highlights: list[str] = []
        highlights_raw: object = item.get("highlights")
        if isinstance(highlights_raw, list):
            for hl_raw in cast(list[object], highlights_raw):
                if isinstance(hl_raw, str) and hl_raw.strip():
                    highlights.append(hl_raw.strip())
        if title or text or highlights:
            hits.append(
                ExaSearchHit(title=title, url=url, text=text, highlights=highlights)
            )
    return hits
