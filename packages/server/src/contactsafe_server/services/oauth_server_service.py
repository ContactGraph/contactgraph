import base64
import hashlib
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode, urlparse

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from contactsafe_server.config import Settings
from contactsafe_server.db.models import AuthorizationCode, ConnectSession, OAuthClient, RefreshToken
from contactsafe_server.services.jwt_service import DEFAULT_MCP_SCOPES, JWTService

DEFAULT_GRANT_TYPES: tuple[str, ...] = ("authorization_code", "refresh_token")
DEFAULT_RESPONSE_TYPES: tuple[str, ...] = ("code",)


class DynamicClientRegistrationRequest(BaseModel):
    redirect_uris: list[str] = Field(min_length=1)
    token_endpoint_auth_method: str = "none"
    grant_types: list[str] = Field(default_factory=lambda: list(DEFAULT_GRANT_TYPES))
    response_types: list[str] = Field(default_factory=lambda: list(DEFAULT_RESPONSE_TYPES))
    client_name: str | None = None
    scope: str | None = None


class DynamicClientRegistrationResponse(BaseModel):
    client_id: str
    client_id_issued_at: int
    redirect_uris: list[str]
    token_endpoint_auth_method: str
    grant_types: list[str]
    response_types: list[str]
    client_name: str | None = None


@dataclass(frozen=True, slots=True)
class TokenResponse:
    access_token: str
    token_type: str
    expires_in: int
    refresh_token: str | None
    scope: str


def hash_token(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def verify_pkce(code_verifier: str, code_challenge: str, method: str) -> bool:
    if method != "S256":
        return False

    digest: bytes = hashlib.sha256(code_verifier.encode("ascii")).digest()
    computed: str = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return secrets.compare_digest(computed, code_challenge)


def parse_scopes_param(scope: str) -> list[str]:
    scopes: list[str] = [s for s in scope.split() if s]
    return scopes if scopes else list(DEFAULT_MCP_SCOPES)


class OAuthServerService:
    def __init__(
        self,
        db: AsyncSession,
        settings: Settings,
        jwt_service: JWTService,
    ) -> None:
        self._db: AsyncSession = db
        self._settings: Settings = settings
        self._jwt: JWTService = jwt_service

    async def register_client(
        self,
        request: DynamicClientRegistrationRequest,
    ) -> DynamicClientRegistrationResponse:
        if request.token_endpoint_auth_method != "none":
            raise ValueError("Only token_endpoint_auth_method 'none' is supported")
        for uri in request.redirect_uris:
            parsed = urlparse(uri)
            if parsed.scheme not in {"https", "http"}:
                raise ValueError(f"Invalid redirect_uri scheme: {uri}")
            if not parsed.netloc:
                raise ValueError(f"Invalid redirect_uri: {uri}")
            if self._settings.app_env == "production":
                host: str = parsed.hostname or ""
                is_local: bool = host in {"localhost", "127.0.0.1"}
                if parsed.scheme != "https" and not is_local:
                    raise ValueError("Production redirect_uris must use https")

        client_id: str = secrets.token_urlsafe(32)
        client = OAuthClient(
            client_id=client_id,
            client_name=request.client_name,
            redirect_uris=list(request.redirect_uris),
            token_endpoint_auth_method=request.token_endpoint_auth_method,
            grant_types=list(request.grant_types),
            response_types=list(request.response_types),
        )
        self._db.add(client)
        await self._db.flush()
        issued_at: int = int(datetime.now(tz=UTC).timestamp())
        return DynamicClientRegistrationResponse(
            client_id=client.client_id,
            client_id_issued_at=issued_at,
            redirect_uris=list(client.redirect_uris),
            token_endpoint_auth_method=client.token_endpoint_auth_method,
            grant_types=list(client.grant_types),
            response_types=list(client.response_types),
            client_name=client.client_name,
        )

    async def validate_client_redirect(
        self,
        *,
        client_id: str | None,
        redirect_uri: str,
    ) -> None:
        if client_id is None:
            return
        result = await self._db.execute(
            select(OAuthClient).where(OAuthClient.client_id == client_id)
        )
        client: OAuthClient | None = result.scalar_one_or_none()
        if client is None:
            raise ValueError("Unknown client_id")
        if redirect_uri not in client.redirect_uris:
            raise ValueError("redirect_uri not registered for this client")

    async def create_oauth_authorize_session(
        self,
        *,
        redirect_uri: str,
        code_challenge: str,
        code_challenge_method: str,
        client_state: str,
        scopes: list[str],
        client_id: str | None = None,
    ) -> ConnectSession:
        await self.validate_client_redirect(client_id=client_id, redirect_uri=redirect_uri)
        if code_challenge_method != "S256":
            raise ValueError("Only S256 code_challenge_method is supported")
        if not code_challenge:
            raise ValueError("code_challenge is required")

        state: str = secrets.token_urlsafe(32)
        session = ConnectSession(
            state=state,
            status="pending",
            requested_scopes=scopes,
            oauth_redirect_uri=redirect_uri,
            oauth_client_state=client_state,
            code_challenge=code_challenge,
            code_challenge_method=code_challenge_method,
        )
        self._db.add(session)
        await self._db.flush()
        return session

    async def create_authorization_code(
        self,
        session: ConnectSession,
        user_id: uuid.UUID,
        scopes: list[str],
    ) -> str:
        raw_code: str = secrets.token_urlsafe(32)
        expires_at: datetime = datetime.now(tz=UTC) + timedelta(minutes=10)
        auth_code = AuthorizationCode(
            user_id=user_id,
            code_hash=hash_token(raw_code),
            code_challenge=session.code_challenge,
            code_challenge_method=session.code_challenge_method,
            redirect_uri=session.oauth_redirect_uri or "",
            scopes=scopes,
            expires_at=expires_at,
            used=False,
        )
        self._db.add(auth_code)
        await self._db.flush()
        return raw_code

    def build_client_redirect_url(
        self,
        session: ConnectSession,
        *,
        code: str | None = None,
        error: str | None = None,
    ) -> str:
        redirect_uri: str = session.oauth_redirect_uri or ""
        params: dict[str, str] = {}
        if session.oauth_client_state:
            params["state"] = session.oauth_client_state
        if code is not None:
            params["code"] = code
        if error is not None:
            params["error"] = error
        parsed = urlparse(redirect_uri)
        separator: str = "&" if parsed.query else "?"
        return f"{redirect_uri}{separator}{urlencode(params)}" if params else redirect_uri

    async def exchange_authorization_code(
        self,
        *,
        code: str,
        redirect_uri: str,
        code_verifier: str,
    ) -> TokenResponse:
        code_hash: str = hash_token(code)
        result = await self._db.execute(
            select(AuthorizationCode).where(AuthorizationCode.code_hash == code_hash)
        )
        auth_code: AuthorizationCode | None = result.scalar_one_or_none()
        if auth_code is None:
            raise ValueError("Invalid authorization code")
        if auth_code.used:
            raise ValueError("Authorization code already used")
        if auth_code.expires_at < datetime.now(tz=UTC):
            raise ValueError("Authorization code expired")
        if auth_code.redirect_uri != redirect_uri:
            raise ValueError("redirect_uri mismatch")
        if auth_code.code_challenge is None or auth_code.code_challenge_method is None:
            raise ValueError("Authorization code missing PKCE challenge")
        if not verify_pkce(
            code_verifier,
            auth_code.code_challenge,
            auth_code.code_challenge_method,
        ):
            raise ValueError("Invalid code_verifier")

        auth_code.used = True
        return await self._mint_tokens(auth_code.user_id, list(auth_code.scopes))

    async def exchange_refresh_token(self, refresh_token: str) -> TokenResponse:
        token_hash: str = hash_token(refresh_token)
        result = await self._db.execute(
            select(RefreshToken).where(RefreshToken.token_hash == token_hash)
        )
        stored: RefreshToken | None = result.scalar_one_or_none()
        if stored is None or stored.revoked:
            raise ValueError("Invalid refresh token")
        if stored.expires_at < datetime.now(tz=UTC):
            raise ValueError("Refresh token expired")

        try:
            claims: dict[str, object] = self._jwt.decode_token(refresh_token)
        except ValueError as exc:
            raise ValueError("Invalid refresh token") from exc
        if claims.get("typ") != "refresh":
            raise ValueError("Token is not a refresh token")

        user_id_str: str = str(claims.get("sub", ""))
        try:
            user_id: uuid.UUID = uuid.UUID(user_id_str)
        except ValueError as exc:
            raise ValueError("Invalid refresh token subject") from exc
        if user_id != stored.user_id:
            raise ValueError("Refresh token subject mismatch")

        return await self._mint_tokens(user_id, list(stored.scopes), rotate_refresh=False)

    async def _mint_tokens(
        self,
        user_id: uuid.UUID,
        scopes: list[str],
        *,
        rotate_refresh: bool = True,
    ) -> TokenResponse:
        access_token: str = self._jwt.create_access_token(user_id, scopes)
        refresh_token: str | None = None
        if rotate_refresh:
            refresh_token = self._jwt.create_refresh_token(user_id, scopes)
            expires_at: datetime = datetime.now(tz=UTC) + timedelta(
                days=self._settings.jwt_refresh_token_expire_days
            )
            self._db.add(
                RefreshToken(
                    user_id=user_id,
                    token_hash=hash_token(refresh_token),
                    scopes=scopes,
                    expires_at=expires_at,
                    revoked=False,
                )
            )
            await self._db.flush()

        return TokenResponse(
            access_token=access_token,
            token_type="Bearer",
            expires_in=self._settings.jwt_access_token_expire_minutes * 60,
            refresh_token=refresh_token,
            scope=" ".join(scopes),
        )

    async def mint_tokens_for_user(
        self,
        user_id: uuid.UUID,
        scopes: list[str] | None = None,
    ) -> TokenResponse:
        effective_scopes: list[str] = scopes if scopes else list(DEFAULT_MCP_SCOPES)
        return await self._mint_tokens(user_id, effective_scopes)
