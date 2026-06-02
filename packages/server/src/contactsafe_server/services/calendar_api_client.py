from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import httpx

from contactsafe_server.oauth.google import GoogleOAuthClient, GoogleTokens


@dataclass(frozen=True, slots=True)
class CalendarEventParticipant:
    email: str
    display_name: str | None = None


@dataclass(frozen=True, slots=True)
class CalendarEventsPage:
    participants: list[CalendarEventParticipant]
    next_sync_token: str | None = None


class CalendarApiClient:
    CALENDAR_EVENTS_URL: str = "https://www.googleapis.com/calendar/v3/calendars/primary/events"

    def __init__(self, google_oauth: GoogleOAuthClient) -> None:
        self._google_oauth: GoogleOAuthClient = google_oauth

    async def get_valid_access_token(
        self,
        access_token: str,
        refresh_token: str,
        expires_at: datetime,
    ) -> tuple[str, GoogleTokens | None]:
        if datetime.now(tz=UTC) < expires_at:
            return access_token, None
        refreshed: GoogleTokens = await self._google_oauth.refresh_access_token(refresh_token)
        return refreshed.access_token, refreshed

    async def list_recent_participants(
        self,
        access_token: str,
        *,
        sync_token: str | None,
        max_results: int,
    ) -> CalendarEventsPage:
        params: dict[str, str | int | bool] = {
            "singleEvents": True,
            "maxResults": max_results,
            "showDeleted": False,
        }
        if sync_token:
            params["syncToken"] = sync_token
        else:
            params["orderBy"] = "updated"
            params["timeMin"] = datetime.now(tz=UTC).replace(month=1, day=1).isoformat()

        async with httpx.AsyncClient(timeout=30.0) as http:
            response = await http.get(
                self.CALENDAR_EVENTS_URL,
                headers={"Authorization": f"Bearer {access_token}"},
                params=params,
            )
            response.raise_for_status()
            payload: dict[str, Any] = response.json()

        participants: list[CalendarEventParticipant] = []
        for event in payload.get("items", []):
            if not isinstance(event, dict):
                continue
            attendees = event.get("attendees", [])
            if not isinstance(attendees, list):
                continue
            for attendee in attendees:
                if not isinstance(attendee, dict):
                    continue
                email: str = str(attendee.get("email", "")).strip().lower()
                if not email:
                    continue
                if attendee.get("self") is True or attendee.get("resource") is True:
                    continue
                display_name_raw = attendee.get("displayName")
                display_name: str | None = (
                    str(display_name_raw) if display_name_raw else None
                )
                participants.append(
                    CalendarEventParticipant(email=email, display_name=display_name)
                )

        return CalendarEventsPage(
            participants=participants,
            next_sync_token=(
                str(payload["nextSyncToken"])
                if isinstance(payload.get("nextSyncToken"), str)
                else None
            ),
        )
