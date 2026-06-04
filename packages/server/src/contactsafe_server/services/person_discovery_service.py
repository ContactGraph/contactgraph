"""Orchestrate web search providers and platform activity for person enrichment."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from contactsafe_server.config import Settings
from contactsafe_server.services.exa_client import ExaClient
from contactsafe_server.services.person_search_query import (
    build_relational_context_query,
    is_generic_email,
)
from contactsafe_server.services.platform_activity import (
    PlatformActivityClient,
    PlatformPost,
    posts_to_activity_blob,
)
from contactsafe_server.services.serper_client import SerperClient
from contactsafe_server.services.tavily_client import TavilyClient
from contactsafe_server.services.web_search_types import WebSearchHit

logger = logging.getLogger(__name__)

_TITLE_CASE_PHRASE_RE: re.Pattern[str] = re.compile(
    r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3})\b"
)


@dataclass(frozen=True, slots=True)
class PersonDiscoveryResult:
    employer_hits: list[WebSearchHit]
    activity_hits: list[WebSearchHit]
    posts: list[PlatformPost]
    providers_used: list[str]


def extract_context_hints_from_hits(
    hits: list[WebSearchHit],
    *,
    user_name: str,
    contact_name: str,
) -> list[str]:
    parts: list[str] = []
    for hit in hits:
        if hit.title:
            parts.append(hit.title)
        parts.extend(hit.highlights)
        if hit.text:
            parts.append(hit.text)
    blob: str = " ".join(parts)
    skip_lower: set[str] = {
        user_name.lower(),
        contact_name.lower(),
        *user_name.lower().split(),
        *contact_name.lower().split(),
    }
    hints: list[str] = []
    for match in _TITLE_CASE_PHRASE_RE.finditer(blob):
        phrase: str = match.group(1).strip()
        if phrase.lower() in skip_lower:
            continue
        if len(phrase) < 4:
            continue
        hints.append(phrase)
    return list(dict.fromkeys(hints))[:5]


class PersonDiscoveryService:
    def __init__(self, settings: Settings) -> None:
        self._settings: Settings = settings
        self._exa: ExaClient = ExaClient(settings)
        self._tavily: TavilyClient = TavilyClient(settings)
        self._serper: SerperClient = SerperClient(settings)
        self._platform: PlatformActivityClient = PlatformActivityClient(settings)

    async def discover_person(
        self,
        *,
        name: str,
        email: str,
        org_hint: str | None,
        user_name: str | None = None,
        user_location: str | None = None,
    ) -> PersonDiscoveryResult:
        providers_used: list[str] = []
        context_hints: list[str] | None = None

        if (
            user_name
            and user_name.strip()
            and is_generic_email(email)
            and not (org_hint and org_hint.strip())
        ):
            relational_hits = await self._search_relational_context(
                user_name=user_name.strip(),
                contact_name=name.strip(),
                providers_used=providers_used,
            )
            extracted: list[str] = extract_context_hints_from_hits(
                relational_hits,
                user_name=user_name.strip(),
                contact_name=name.strip(),
            )
            if extracted:
                context_hints = extracted

        employer_hits: list[WebSearchHit] = await self._search_employer(
            name=name,
            email=email,
            org_hint=org_hint,
            user_location=user_location,
            context_hints=context_hints,
            providers_used=providers_used,
        )
        activity_hits: list[WebSearchHit] = await self._search_activity(
            name=name,
            org_hint=org_hint,
            user_location=user_location,
            providers_used=providers_used,
        )

        social_profiles: dict[str, str] = {}
        from contactsafe_server.services.web_enrichment import extract_social_profiles_from_hits

        for hit in [*employer_hits, *activity_hits]:
            social_profiles.update(extract_social_profiles_from_hits([hit]))

        posts: list[PlatformPost] = []
        if social_profiles and self._settings.platform_activity_enabled:
            try:
                posts = await self._platform.fetch_recent_posts(
                    social_profiles=social_profiles,
                )
            except Exception:
                logger.exception("Platform activity fetch failed for %s", email)

        return PersonDiscoveryResult(
            employer_hits=employer_hits,
            activity_hits=activity_hits,
            posts=posts,
            providers_used=providers_used,
        )

    def activity_blob(self, result: PersonDiscoveryResult) -> str:
        web_blob_parts: list[str] = []
        for hit in result.activity_hits:
            if hit.text:
                web_blob_parts.append(hit.text[:500])
        post_blob: str = posts_to_activity_blob(result.posts)
        return "\n".join(part for part in [post_blob, *web_blob_parts] if part)

    async def _search_relational_context(
        self,
        *,
        user_name: str,
        contact_name: str,
        providers_used: list[str],
    ) -> list[WebSearchHit]:
        query: str = build_relational_context_query(user_name, contact_name)

        if self._settings.exa_api_key:
            try:
                hits = await self._exa.search_raw(query=query, num_results=3)
                if hits:
                    providers_used.append("exa:relational")
                    return hits
            except Exception:
                logger.exception(
                    "Exa relational search failed for %s + %s",
                    user_name,
                    contact_name,
                )

        if self._settings.tavily_api_key:
            try:
                hits = await self._tavily.search_raw(query=query)
                if hits:
                    providers_used.append("tavily:relational")
                    return hits[:3]
            except Exception:
                logger.exception(
                    "Tavily relational search failed for %s + %s",
                    user_name,
                    contact_name,
                )

        if self._settings.serper_api_key:
            try:
                hits = await self._serper.search_raw(query=query)
                if hits:
                    providers_used.append("serper:relational")
                    return hits[:3]
            except Exception:
                logger.exception(
                    "Serper relational search failed for %s + %s",
                    user_name,
                    contact_name,
                )

        return []

    async def search_employer(
        self,
        *,
        name: str,
        email: str,
        org_hint: str | None,
        user_location: str | None = None,
        context_hints: list[str] | None = None,
    ) -> tuple[list[WebSearchHit], str | None]:
        providers_used: list[str] = []
        hits: list[WebSearchHit] = await self._search_employer(
            name=name,
            email=email,
            org_hint=org_hint,
            user_location=user_location,
            context_hints=context_hints,
            providers_used=providers_used,
        )
        provider: str | None = providers_used[0] if providers_used else None
        return hits, provider

    async def search_relational(
        self,
        *,
        user_name: str,
        contact_name: str,
    ) -> list[WebSearchHit]:
        providers_used: list[str] = []
        return await self._search_relational_context(
            user_name=user_name,
            contact_name=contact_name,
            providers_used=providers_used,
        )

    async def search_raw_query(self, query: str) -> tuple[list[WebSearchHit], str | None]:
        providers_used: list[str] = []
        if self._settings.exa_api_key:
            try:
                hits = await self._exa.search_raw(query=query, num_results=3)
                if hits:
                    providers_used.append("exa")
                    return hits, providers_used[0]
            except Exception:
                logger.exception("Exa raw search failed for query: %s", query)

        if self._settings.tavily_api_key:
            try:
                hits = await self._tavily.search_raw(query=query)
                if hits:
                    providers_used.append("tavily")
                    return hits[:3], providers_used[0]
            except Exception:
                logger.exception("Tavily raw search failed for query: %s", query)

        if self._settings.serper_api_key:
            try:
                hits = await self._serper.search_raw(query=query)
                if hits:
                    providers_used.append("serper")
                    return hits[:3], providers_used[0]
            except Exception:
                logger.exception("Serper raw search failed for query: %s", query)

        return [], None

    async def _search_employer(
        self,
        *,
        name: str,
        email: str,
        org_hint: str | None,
        user_location: str | None,
        context_hints: list[str] | None,
        providers_used: list[str],
    ) -> list[WebSearchHit]:
        if self._settings.exa_api_key:
            try:
                hits = await self._exa.search_person_context(
                    name=name,
                    email=email,
                    org_hint=org_hint,
                    category="people",
                    user_location=user_location,
                    context_hints=context_hints,
                )
                if hits:
                    providers_used.append("exa:people")
                    return hits
            except Exception:
                logger.exception("Exa people search failed for %s", email)

        if self._settings.tavily_api_key:
            try:
                hits = await self._tavily.search_person_context(
                    name=name,
                    email=email,
                    org_hint=org_hint,
                    user_location=user_location,
                    context_hints=context_hints,
                )
                if hits:
                    providers_used.append("tavily")
                    return hits
            except Exception:
                logger.exception("Tavily search failed for %s", email)

        if self._settings.serper_api_key:
            try:
                hits = await self._serper.search_person_context(
                    name=name,
                    email=email,
                    org_hint=org_hint,
                    user_location=user_location,
                    context_hints=context_hints,
                )
                if hits:
                    providers_used.append("serper")
                    return hits
            except Exception:
                logger.exception("Serper search failed for %s", email)

        return []

    async def _search_activity(
        self,
        *,
        name: str,
        org_hint: str | None,
        user_location: str | None,
        providers_used: list[str],
    ) -> list[WebSearchHit]:
        if self._settings.exa_api_key:
            try:
                hits = await self._exa.search_person_activity(
                    name=name,
                    org_hint=org_hint,
                    user_location=user_location,
                )
                if hits:
                    providers_used.append("exa:personal_site")
                    return hits
            except Exception:
                logger.exception("Exa personal_site search failed for %s", name)

        if self._settings.tavily_api_key:
            try:
                hits = await self._tavily.search_person_activity(
                    name=name,
                    org_hint=org_hint,
                    user_location=user_location,
                )
                if hits:
                    if "tavily" not in providers_used:
                        providers_used.append("tavily:activity")
                    return hits
            except Exception:
                logger.exception("Tavily activity search failed for %s", name)

        if self._settings.serper_api_key:
            try:
                hits = await self._serper.search_person_activity(
                    name=name,
                    org_hint=org_hint,
                    user_location=user_location,
                )
                if hits:
                    if "serper" not in providers_used:
                        providers_used.append("serper:activity")
                    return hits
            except Exception:
                logger.exception("Serper activity search failed for %s", name)

        return []
