from dataclasses import dataclass
from typing import Any, cast

import httpx


@dataclass(frozen=True, slots=True)
class CalendarAttendee:
    email: str
    display_name: str | None
    is_self: bool


@dataclass(frozen=True, slots=True)
class CalendarEvent:
    id: str
    summary: str | None
    attendees: list[CalendarAttendee]


class CalendarClient:
    BASE_URL: str = "https://www.googleapis.com/calendar/v3"

    async def list_events(
        self,
        access_token: str,
        *,
        max_results: int,
        page_token: str | None = None,
    ) -> tuple[list[CalendarEvent], str | None]:
        params: dict[str, str | int | bool] = {
            "maxResults": max_results,
            "singleEvents": True,
            "orderBy": "updated",
        }
        if page_token:
            params["pageToken"] = page_token

        data: dict[str, Any] = await self._get(
            access_token,
            "/calendars/primary/events",
            params=params,
        )
        raw_events: list[dict[str, Any]] = cast(list[dict[str, Any]], data.get("items") or [])
        events: list[CalendarEvent] = []
        for item in raw_events:
            event_id: str = str(item.get("id", "")).strip()
            if not event_id:
                continue
            raw_attendees: list[dict[str, Any]] = cast(
                list[dict[str, Any]], item.get("attendees") or []
            )
            attendees: list[CalendarAttendee] = []
            for raw_attendee in raw_attendees:
                email: str = str(raw_attendee.get("email", "")).strip().lower()
                if not email:
                    continue
                attendees.append(
                    CalendarAttendee(
                        email=email,
                        display_name=(
                            str(raw_attendee.get("displayName"))
                            if raw_attendee.get("displayName")
                            else None
                        ),
                        is_self=bool(raw_attendee.get("self", False)),
                    )
                )
            events.append(
                CalendarEvent(
                    id=event_id,
                    summary=str(item.get("summary")) if item.get("summary") else None,
                    attendees=attendees,
                )
            )
        next_page: str | None = str(data["nextPageToken"]) if data.get("nextPageToken") else None
        return events, next_page

    async def _get(
        self,
        access_token: str,
        path: str,
        *,
        params: dict[str, str | int | bool] | None = None,
    ) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=60.0) as http:
            response = await http.get(
                f"{self.BASE_URL}{path}",
                headers={"Authorization": f"Bearer {access_token}"},
                params=params,
            )
            response.raise_for_status()
            return cast(dict[str, Any], response.json())
