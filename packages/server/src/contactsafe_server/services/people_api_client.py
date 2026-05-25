from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, cast

import httpx

from contactsafe_server.config import Settings
from contactsafe_server.oauth.google import GoogleOAuthClient, GoogleTokens


@dataclass(frozen=True, slots=True)
class GoogleContact:
    resource_name: str
    display_name: str | None
    emails: list[str]
    phone_numbers: list[str]
    org_name: str | None
    org_title: str | None
    photo_url: str | None
    is_deleted: bool = False


@dataclass(frozen=True, slots=True)
class ContactsPage:
    contacts: list[GoogleContact]
    next_page_token: str | None
    next_sync_token: str | None


class PeopleApiClient:
    BASE_URL: str = "https://people.googleapis.com/v1"
    PERSON_FIELDS: str = "names,emailAddresses,phoneNumbers,organizations,photos,metadata"

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

    async def list_connections(
        self,
        access_token: str,
        *,
        page_size: int = 100,
        page_token: str | None = None,
        sync_token: str | None = None,
        request_sync_token: bool = True,
    ) -> ContactsPage:
        params: dict[str, str | int | bool] = {
            "pageSize": min(page_size, 1000),
            "personFields": self.PERSON_FIELDS,
            "requestSyncToken": request_sync_token,
        }
        if sync_token is not None:
            params["syncToken"] = sync_token
        if page_token is not None:
            params["pageToken"] = page_token

        async with httpx.AsyncClient(timeout=60.0) as http:
            response: httpx.Response = await http.get(
                f"{self.BASE_URL}/people/me/connections",
                headers={"Authorization": f"Bearer {access_token}"},
                params=params,
            )
            response.raise_for_status()
            data: dict[str, Any] = cast(dict[str, Any], response.json())

        raw_connections: list[dict[str, Any]] = cast(
            list[dict[str, Any]], data.get("connections") or [],
        )
        contacts: list[GoogleContact] = [
            self._parse_contact(c) for c in raw_connections
        ]

        next_page: str | None = (
            str(data["nextPageToken"]) if data.get("nextPageToken") else None
        )
        next_sync: str | None = (
            str(data["nextSyncToken"]) if data.get("nextSyncToken") else None
        )
        return ContactsPage(
            contacts=contacts,
            next_page_token=next_page,
            next_sync_token=next_sync,
        )

    @staticmethod
    def _parse_contact(raw: dict[str, Any]) -> GoogleContact:
        resource_name: str = str(raw.get("resourceName", ""))

        metadata: dict[str, Any] = cast(dict[str, Any], raw.get("metadata") or {})
        is_deleted: bool = bool(metadata.get("deleted", False))

        names: list[dict[str, Any]] = cast(
            list[dict[str, Any]], raw.get("names") or [],
        )
        display_name: str | None = None
        if names:
            display_name = str(names[0].get("displayName", "")) or None

        email_entries: list[dict[str, Any]] = cast(
            list[dict[str, Any]], raw.get("emailAddresses") or [],
        )
        emails: list[str] = [
            str(e["value"]).strip().lower()
            for e in email_entries
            if e.get("value")
        ]

        phone_entries: list[dict[str, Any]] = cast(
            list[dict[str, Any]], raw.get("phoneNumbers") or [],
        )
        phone_numbers: list[str] = [
            str(p["value"]).strip()
            for p in phone_entries
            if p.get("value")
        ]

        orgs: list[dict[str, Any]] = cast(
            list[dict[str, Any]], raw.get("organizations") or [],
        )
        org_name: str | None = None
        org_title: str | None = None
        if orgs:
            org_name = str(orgs[0].get("name", "")) or None
            org_title = str(orgs[0].get("title", "")) or None

        photos: list[dict[str, Any]] = cast(
            list[dict[str, Any]], raw.get("photos") or [],
        )
        photo_url: str | None = None
        if photos:
            url_raw: str = str(photos[0].get("url", ""))
            if url_raw and not photos[0].get("default"):
                photo_url = url_raw

        return GoogleContact(
            resource_name=resource_name,
            display_name=display_name,
            emails=emails,
            phone_numbers=phone_numbers,
            org_name=org_name,
            org_title=org_title,
            photo_url=photo_url,
            is_deleted=is_deleted,
        )
