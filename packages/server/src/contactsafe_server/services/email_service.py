"""Transactional email delivery via Resend."""

from __future__ import annotations

import logging
from dataclasses import dataclass

import httpx

from contactsafe_server.config import Settings

logger: logging.Logger = logging.getLogger(__name__)

_RESEND_API_URL: str = "https://api.resend.com/emails"


@dataclass(frozen=True, slots=True)
class EmailSendResult:
    sent: bool
    provider_id: str | None
    message: str


class EmailService:
    def __init__(self, settings: Settings) -> None:
        self._settings: Settings = settings

    @property
    def is_configured(self) -> bool:
        return bool(self._settings.resend_api_key)

    async def send_html_email(
        self,
        *,
        to: str,
        subject: str,
        html: str,
        unsubscribe_url: str,
    ) -> EmailSendResult:
        if not self.is_configured:
            logger.info("Email skipped (RESEND_API_KEY unset): to=%s subject=%s", to, subject)
            return EmailSendResult(sent=False, provider_id=None, message="Email delivery disabled.")

        headers: dict[str, str] = {
            "Authorization": f"Bearer {self._settings.resend_api_key}",
            "Content-Type": "application/json",
        }
        payload: dict[str, object] = {
            "from": self._settings.email_from_address,
            "to": [to],
            "subject": subject,
            "html": html,
            "headers": {
                "List-Unsubscribe": f"<{unsubscribe_url}>",
                "List-Unsubscribe-Post": "List-Unsubscribe=One-Click",
            },
        }

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response: httpx.Response = await client.post(
                    _RESEND_API_URL,
                    headers=headers,
                    json=payload,
                )
                response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            body: str = exc.response.text[:500]
            logger.error("Resend API error for %s: %s %s", to, exc.response.status_code, body)
            return EmailSendResult(
                sent=False,
                provider_id=None,
                message=f"Resend API error: {exc.response.status_code}",
            )
        except httpx.HTTPError as exc:
            logger.error("Resend request failed for %s: %s", to, exc)
            return EmailSendResult(sent=False, provider_id=None, message="Resend request failed.")

        provider_id: str | None = None
        try:
            data: dict[str, object] = response.json()
            raw_id: object = data.get("id")
            if isinstance(raw_id, str):
                provider_id = raw_id
        except ValueError:
            pass

        return EmailSendResult(sent=True, provider_id=provider_id, message="OK")
