from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, NotRequired, TypedDict, cast

import httpx
from authlib.integrations.httpx_client import AsyncOAuth2Client

from contactsafe_server.config import Settings


class GoogleTokenResponse(TypedDict, total=False):
    access_token: str
    refresh_token: str
    expires_in: int
    scope: str
    token_type: str


class GoogleUserInfo(TypedDict, total=False):
    sub: str
    email: str
    name: NotRequired[str | None]
    picture: NotRequired[str | None]
    email_verified: bool


@dataclass(frozen=True, slots=True)
class GoogleTokens:
    access_token: str
    refresh_token: str
    expires_at: datetime
    scopes: list[str]


class GoogleOAuthClient:
    AUTHORIZE_URL: str = "https://accounts.google.com/o/oauth2/v2/auth"
    TOKEN_URL: str = "https://oauth2.googleapis.com/token"
    USERINFO_URL: str = "https://www.googleapis.com/oauth2/v3/userinfo"

    def __init__(self, settings: Settings) -> None:
        self._settings: Settings = settings

    def build_authorization_url(self, state: str) -> str:
        client: AsyncOAuth2Client = self._create_client()
        uri: str
        _state: str
        uri, _state = client.create_authorization_url(  # pyright: ignore[reportUnknownMemberType]
            self.AUTHORIZE_URL,
            scope=" ".join(self._settings.google_scopes),
            state=state,
            access_type="offline",
            prompt="consent",
        )
        return uri

    async def exchange_code(self, code: str) -> GoogleTokens:
        client: AsyncOAuth2Client = self._create_client()
        raw_token: object = await client.fetch_token(  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
            self.TOKEN_URL,
            code=code,
            grant_type="authorization_code",
        )
        token: dict[str, Any] = cast(dict[str, Any], raw_token)
        return self._parse_token_response(token)

    async def refresh_access_token(self, refresh_token: str) -> GoogleTokens:
        client: AsyncOAuth2Client = self._create_client()
        raw_token: object = await client.refresh_token(  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
            self.TOKEN_URL,
            refresh_token=refresh_token,
        )
        token: dict[str, Any] = cast(dict[str, Any], raw_token)
        access_token: str = str(token["access_token"])
        expires_in: int = int(token.get("expires_in", 3600))
        expires_at: datetime = datetime.now(tz=UTC) + timedelta(seconds=expires_in)
        scope_raw: str = str(token.get("scope", ""))
        scopes: list[str] = scope_raw.split() if scope_raw else list(self._settings.google_scopes)
        return GoogleTokens(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_at=expires_at,
            scopes=scopes,
        )

    async def fetch_userinfo(self, access_token: str) -> GoogleUserInfo:
        async with httpx.AsyncClient() as http:
            response = await http.get(
                self.USERINFO_URL,
                headers={"Authorization": f"Bearer {access_token}"},
                timeout=30.0,
            )
            response.raise_for_status()
            data: dict[str, Any] = response.json()
            info: GoogleUserInfo = {
                "sub": str(data.get("sub", "")),
                "email": str(data.get("email", "")),
                "email_verified": bool(data.get("email_verified", False)),
            }
            if data.get("name"):
                info["name"] = str(data["name"])
            if data.get("picture"):
                info["picture"] = str(data["picture"])
            return info

    def _create_client(self) -> AsyncOAuth2Client:
        return AsyncOAuth2Client(
            client_id=self._settings.google_client_id,
            client_secret=self._settings.google_client_secret,
            redirect_uri=self._settings.google_redirect_uri,
        )

    def _parse_token_response(self, token: dict[str, Any]) -> GoogleTokens:
        access_token: str = str(token["access_token"])
        refresh_token: str = str(token.get("refresh_token", ""))
        expires_in: int = int(token.get("expires_in", 3600))
        expires_at: datetime = datetime.now(tz=UTC) + timedelta(seconds=expires_in)
        scope_raw: str = str(token.get("scope", ""))
        scopes: list[str] = scope_raw.split() if scope_raw else list(self._settings.google_scopes)
        if not refresh_token:
            raise ValueError("Google did not return a refresh token; ensure prompt=consent")
        return GoogleTokens(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_at=expires_at,
            scopes=scopes,
        )
