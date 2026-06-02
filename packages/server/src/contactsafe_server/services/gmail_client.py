from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, cast

import httpx
from httpx import QueryParams

from contactsafe_server.config import Settings
from contactsafe_server.oauth.google import GoogleOAuthClient, GoogleTokens
from contactsafe_server.services.email_parse import parse_internal_date_ms


@dataclass(frozen=True, slots=True)
class GmailMessageRef:
    id: str
    internal_date_ms: str | None


@dataclass(frozen=True, slots=True)
class GmailMessageListPage:
    refs: list[GmailMessageRef]
    next_page_token: str | None
    result_size_estimate: int | None


@dataclass(frozen=True, slots=True)
class ContactTimeline:
    earliest_date: datetime | None
    latest_date: datetime | None
    estimated_count: int


@dataclass(frozen=True, slots=True)
class GmailMessageMeta:
    id: str
    internal_date_ms: str | None
    from_header: str | None
    to_header: str | None
    cc_header: str | None
    snippet: str | None
    has_list_unsubscribe: bool = False


class GmailClient:
    BASE_URL: str = "https://gmail.googleapis.com/gmail/v1"

    def __init__(self, settings: Settings, google: GoogleOAuthClient) -> None:
        self._settings: Settings = settings
        self._google: GoogleOAuthClient = google

    async def get_valid_access_token(
        self,
        access_token: str,
        refresh_token: str,
        token_expires_at: datetime,
    ) -> tuple[str, GoogleTokens | None]:
        if token_expires_at > datetime.now(tz=UTC):
            return access_token, None
        refreshed: GoogleTokens = await self._google.refresh_access_token(refresh_token)
        return refreshed.access_token, refreshed

    async def list_message_refs(
        self,
        access_token: str,
        *,
        max_results: int,
        page_token: str | None = None,
        query: str | None = None,
    ) -> GmailMessageListPage:
        params: dict[str, str | int] = {"maxResults": max_results}
        if page_token:
            params["pageToken"] = page_token
        if query:
            params["q"] = query
        data: dict[str, Any] = await self._get(
            access_token,
            "/users/me/messages",
            params=params,
        )
        messages_raw: list[dict[str, Any]] = cast(
            list[dict[str, Any]], data.get("messages") or []
        )
        refs: list[GmailMessageRef] = [
            GmailMessageRef(
                id=str(item["id"]),
                internal_date_ms=str(item.get("internalDate")) if item.get("internalDate") else None,
            )
            for item in messages_raw
            if item.get("id")
        ]
        next_page: str | None = str(data["nextPageToken"]) if data.get("nextPageToken") else None
        estimate_raw: object = data.get("resultSizeEstimate")
        result_size_estimate: int | None = (
            int(estimate_raw) if isinstance(estimate_raw, int) else None
        )
        return GmailMessageListPage(
            refs=refs,
            next_page_token=next_page,
            result_size_estimate=result_size_estimate,
        )

    async def get_contact_timeline(
        self,
        access_token: str,
        email: str,
        *,
        max_pages: int = 10,
        page_size: int = 100,
    ) -> ContactTimeline:
        query: str = f'from:{email} OR to:{email}'
        first_page: GmailMessageListPage = await self.list_message_refs(
            access_token,
            max_results=1,
            query=query,
        )
        estimated_count: int = first_page.result_size_estimate or len(first_page.refs)

        latest_date: datetime | None = None
        if first_page.refs:
            latest_meta: GmailMessageMeta = await self.get_message_metadata(
                access_token, first_page.refs[0].id
            )
            latest_date = parse_internal_date_ms(latest_meta.internal_date_ms)

        earliest_date: datetime | None = None
        if not first_page.refs:
            return ContactTimeline(
                earliest_date=None,
                latest_date=None,
                estimated_count=0,
            )

        current_page: GmailMessageListPage = first_page
        pages_fetched: int = 1
        last_refs: list[GmailMessageRef] = first_page.refs

        while current_page.next_page_token is not None and pages_fetched < max_pages:
            current_page = await self.list_message_refs(
                access_token,
                max_results=page_size,
                page_token=current_page.next_page_token,
                query=query,
            )
            pages_fetched += 1
            if current_page.refs:
                last_refs = current_page.refs

        if last_refs:
            earliest_meta: GmailMessageMeta = await self.get_message_metadata(
                access_token, last_refs[-1].id
            )
            earliest_date = parse_internal_date_ms(earliest_meta.internal_date_ms)

        return ContactTimeline(
            earliest_date=earliest_date,
            latest_date=latest_date,
            estimated_count=estimated_count,
        )

    async def get_message_metadata(self, access_token: str, message_id: str) -> GmailMessageMeta:
        params: list[tuple[str, str]] = [
            ("format", "metadata"),
            ("metadataHeaders", "From"),
            ("metadataHeaders", "To"),
            ("metadataHeaders", "Cc"),
            ("metadataHeaders", "Date"),
            ("metadataHeaders", "List-Unsubscribe"),
        ]
        data: dict[str, Any] = await self._get_with_query(
            access_token,
            f"/users/me/messages/{message_id}",
            params=params,
        )
        headers: dict[str, str] = {}
        payload: dict[str, Any] = cast(dict[str, Any], data.get("payload") or {})
        for header in cast(list[dict[str, Any]], payload.get("headers") or []):
            name: str = str(header.get("name", "")).lower()
            value: str = str(header.get("value", ""))
            if name in {"from", "to", "cc", "date", "list-unsubscribe"}:
                headers[name] = value
        snippet_raw: object = data.get("snippet")
        snippet: str | None = str(snippet_raw) if isinstance(snippet_raw, str) and snippet_raw else None
        has_unsub: bool = bool(headers.get("list-unsubscribe", "").strip())
        return GmailMessageMeta(
            id=str(data.get("id", message_id)),
            internal_date_ms=str(data.get("internalDate")) if data.get("internalDate") else None,
            from_header=headers.get("from"),
            to_header=headers.get("to"),
            cc_header=headers.get("cc"),
            snippet=snippet,
            has_list_unsubscribe=has_unsub,
        )

    async def _get(
        self,
        access_token: str,
        path: str,
        *,
        params: dict[str, str | int] | None = None,
    ) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=60.0) as http:
            response = await http.get(
                f"{self.BASE_URL}{path}",
                headers={"Authorization": f"Bearer {access_token}"},
                params=params,
            )
            response.raise_for_status()
            return cast(dict[str, Any], response.json())

    async def _get_with_query(
        self,
        access_token: str,
        path: str,
        *,
        params: list[tuple[str, str]],
    ) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=60.0) as http:
            response = await http.get(
                f"{self.BASE_URL}{path}",
                headers={"Authorization": f"Bearer {access_token}"},
                params=cast(QueryParams, params),
            )
            response.raise_for_status()
            return cast(dict[str, Any], response.json())
