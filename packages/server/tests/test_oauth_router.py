"""Tests for the OAuth router endpoints."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient

from contactsafe_core.enums import SessionStatus
from contactsafe_server.db.models import ConnectSession, Source, User


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_session(
    *,
    status: str = SessionStatus.PENDING.value,
    user_id: uuid.UUID | None = None,
    state: str = "test-state-xyz",
    oauth_redirect_uri: str | None = None,
    oauth_client_state: str | None = None,
    requested_scopes: list[str] | None = None,
    code_challenge: str | None = "challenge123",
    code_challenge_method: str | None = "S256",
) -> ConnectSession:
    session = ConnectSession(
        id=uuid.uuid4(),
        state=state,
        status=status,
        user_id=user_id,
        oauth_redirect_uri=oauth_redirect_uri,
        oauth_client_state=oauth_client_state,
        requested_scopes=requested_scopes or ["contactsafe:read"],
        code_challenge=code_challenge,
        code_challenge_method=code_challenge_method,
    )
    return session


def _make_user(email: str = "test@example.com") -> User:
    user = User(id=uuid.uuid4(), email=email)
    return user


def _make_source(user_id: uuid.UUID) -> Source:
    source = MagicMock(spec=Source)
    source.id = uuid.uuid4()
    source.user_id = user_id
    return source


@dataclass
class FakeTokenResponse:
    access_token: str = "access-tok-123"
    token_type: str = "bearer"
    expires_in: int = 3600
    refresh_token: str | None = "refresh-tok-456"
    scope: str = "contactsafe:read contactsafe:write"
    resource: str | None = None


# ---------------------------------------------------------------------------
# GET /oauth/authorize (PKCE)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_authorize_pkce_redirects_to_google(client: AsyncClient) -> None:
    """GET /oauth/authorize should create a session and redirect."""
    fake_session: ConnectSession = _make_session()
    google_url: str = "https://accounts.google.com/o/oauth2/v2/auth?state=abc"

    with (
        patch(
            "contactsafe_server.oauth.router._build_oauth_server_service"
        ) as mock_server_svc,
        patch(
            "contactsafe_server.oauth.router._build_oauth_service"
        ) as mock_oauth_svc,
    ):
        mock_server_svc.return_value.create_oauth_authorize_session = AsyncMock(
            return_value=fake_session
        )
        mock_oauth_svc.return_value.build_google_authorization_url = MagicMock(
            return_value=google_url
        )

        resp = await client.get(
            "/oauth/authorize",
            params={
                "redirect_uri": "http://localhost:3000/callback",
                "code_challenge": "challenge123",
                "state": "client-state",
                "code_challenge_method": "S256",
                "scope": "contactsafe:read",
            },
            follow_redirects=False,
        )

    assert resp.status_code == 302
    assert resp.headers["location"] == google_url


@pytest.mark.asyncio
async def test_authorize_pkce_missing_params(client: AsyncClient) -> None:
    """GET /oauth/authorize without required params returns 422."""
    resp = await client.get("/oauth/authorize", params={"redirect_uri": "http://x"})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_authorize_pkce_value_error(client: AsyncClient) -> None:
    """GET /oauth/authorize returns 400 when service raises ValueError."""
    with patch(
        "contactsafe_server.oauth.router._build_oauth_server_service"
    ) as mock_server_svc:
        mock_server_svc.return_value.create_oauth_authorize_session = AsyncMock(
            side_effect=ValueError("invalid redirect_uri")
        )

        resp = await client.get(
            "/oauth/authorize",
            params={
                "redirect_uri": "http://evil.com/x",
                "code_challenge": "abc",
                "state": "s",
            },
            follow_redirects=False,
        )

    assert resp.status_code == 400
    assert "invalid redirect_uri" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# POST /oauth/token
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_token_authorization_code_success(client: AsyncClient) -> None:
    """POST /oauth/token with grant_type=authorization_code returns tokens."""
    fake_token = FakeTokenResponse()

    with patch(
        "contactsafe_server.oauth.router._build_oauth_server_service"
    ) as mock_server_svc:
        mock_server_svc.return_value.exchange_authorization_code = AsyncMock(
            return_value=fake_token
        )

        resp = await client.post(
            "/oauth/token",
            data={
                "grant_type": "authorization_code",
                "code": "auth-code-value",
                "redirect_uri": "http://localhost:3000/callback",
                "code_verifier": "verifier-abc",
            },
        )

    assert resp.status_code == 200
    body: dict[str, Any] = resp.json()
    assert body["access_token"] == "access-tok-123"
    assert body["token_type"] == "bearer"
    assert body["expires_in"] == 3600
    assert body["refresh_token"] == "refresh-tok-456"
    assert body["scope"] == "contactsafe:read contactsafe:write"


@pytest.mark.asyncio
async def test_token_authorization_code_no_refresh(client: AsyncClient) -> None:
    """POST /oauth/token omits refresh_token when None."""
    fake_token = FakeTokenResponse(refresh_token=None)

    with patch(
        "contactsafe_server.oauth.router._build_oauth_server_service"
    ) as mock_server_svc:
        mock_server_svc.return_value.exchange_authorization_code = AsyncMock(
            return_value=fake_token
        )

        resp = await client.post(
            "/oauth/token",
            data={
                "grant_type": "authorization_code",
                "code": "code",
                "redirect_uri": "http://x/cb",
                "code_verifier": "v",
            },
        )

    assert resp.status_code == 200
    assert "refresh_token" not in resp.json()


@pytest.mark.asyncio
async def test_token_authorization_code_with_resource(client: AsyncClient) -> None:
    """POST /oauth/token includes resource field when set."""
    fake_token = FakeTokenResponse(resource="https://api.example.com")

    with patch(
        "contactsafe_server.oauth.router._build_oauth_server_service"
    ) as mock_server_svc:
        mock_server_svc.return_value.exchange_authorization_code = AsyncMock(
            return_value=fake_token
        )

        resp = await client.post(
            "/oauth/token",
            data={
                "grant_type": "authorization_code",
                "code": "c",
                "redirect_uri": "http://x/cb",
                "code_verifier": "v",
            },
        )

    assert resp.status_code == 200
    assert resp.json()["resource"] == "https://api.example.com"


@pytest.mark.asyncio
async def test_token_authorization_code_missing_params(client: AsyncClient) -> None:
    """POST /oauth/token with grant_type=authorization_code but missing code."""
    resp = await client.post(
        "/oauth/token",
        data={
            "grant_type": "authorization_code",
            "redirect_uri": "http://x/cb",
            "code_verifier": "v",
        },
    )
    assert resp.status_code == 400
    assert "code" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_token_authorization_code_missing_verifier(client: AsyncClient) -> None:
    """POST /oauth/token with grant_type=authorization_code but missing verifier."""
    resp = await client.post(
        "/oauth/token",
        data={
            "grant_type": "authorization_code",
            "code": "abc",
            "redirect_uri": "http://x/cb",
        },
    )
    assert resp.status_code == 400
    assert "code_verifier" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_token_refresh_success(client: AsyncClient) -> None:
    """POST /oauth/token with grant_type=refresh_token returns tokens."""
    fake_token = FakeTokenResponse(refresh_token="new-rt")

    with patch(
        "contactsafe_server.oauth.router._build_oauth_server_service"
    ) as mock_server_svc:
        mock_server_svc.return_value.exchange_refresh_token = AsyncMock(
            return_value=fake_token
        )

        resp = await client.post(
            "/oauth/token",
            data={
                "grant_type": "refresh_token",
                "refresh_token": "old-rt",
            },
        )

    assert resp.status_code == 200
    body: dict[str, Any] = resp.json()
    assert body["access_token"] == "access-tok-123"
    assert body["refresh_token"] == "new-rt"


@pytest.mark.asyncio
async def test_token_refresh_missing_token(client: AsyncClient) -> None:
    """POST /oauth/token with refresh_token grant but no token returns 400."""
    resp = await client.post(
        "/oauth/token",
        data={"grant_type": "refresh_token"},
    )
    assert resp.status_code == 400
    assert "refresh_token" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_token_unsupported_grant(client: AsyncClient) -> None:
    """POST /oauth/token with unsupported grant_type returns 400."""
    resp = await client.post(
        "/oauth/token",
        data={"grant_type": "client_credentials"},
    )
    assert resp.status_code == 400
    assert "Unsupported" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_token_exchange_value_error(client: AsyncClient) -> None:
    """POST /oauth/token returns 400 on service ValueError."""
    with patch(
        "contactsafe_server.oauth.router._build_oauth_server_service"
    ) as mock_server_svc:
        mock_server_svc.return_value.exchange_authorization_code = AsyncMock(
            side_effect=ValueError("code expired")
        )

        resp = await client.post(
            "/oauth/token",
            data={
                "grant_type": "authorization_code",
                "code": "expired-code",
                "redirect_uri": "http://x/cb",
                "code_verifier": "v",
            },
        )

    assert resp.status_code == 400
    assert "code expired" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# POST /oauth/register
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_register_client_success(client: AsyncClient) -> None:
    """POST /oauth/register returns 201 with client_id."""
    fake_reg: dict[str, Any] = {
        "client_id": "dyn-client-id-abc",
        "client_id_issued_at": 1700000000,
        "redirect_uris": ["http://localhost:3000/callback"],
        "token_endpoint_auth_method": "none",
        "grant_types": ["authorization_code"],
        "response_types": ["code"],
    }
    mock_response = MagicMock()
    mock_response.model_dump.return_value = fake_reg

    with patch(
        "contactsafe_server.oauth.router._build_oauth_server_service"
    ) as mock_server_svc:
        mock_server_svc.return_value.register_client = AsyncMock(
            return_value=mock_response
        )

        resp = await client.post(
            "/oauth/register",
            json={
                "redirect_uris": ["http://localhost:3000/callback"],
                "token_endpoint_auth_method": "none",
                "grant_types": ["authorization_code"],
                "response_types": ["code"],
            },
        )

    assert resp.status_code == 201
    body: dict[str, Any] = resp.json()
    assert body["client_id"] == "dyn-client-id-abc"


@pytest.mark.asyncio
async def test_register_client_value_error(client: AsyncClient) -> None:
    """POST /oauth/register returns 400 on ValueError."""
    with patch(
        "contactsafe_server.oauth.router._build_oauth_server_service"
    ) as mock_server_svc:
        mock_server_svc.return_value.register_client = AsyncMock(
            side_effect=ValueError("bad auth method")
        )

        resp = await client.post(
            "/oauth/register",
            json={
                "redirect_uris": ["http://localhost:3000/callback"],
                "token_endpoint_auth_method": "client_secret_basic",
            },
        )

    assert resp.status_code == 400
    assert "bad auth method" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_register_client_validation_error(client: AsyncClient) -> None:
    """POST /oauth/register with invalid body returns 422."""
    resp = await client.post("/oauth/register", json={})
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# GET /oauth/start/{session_id}
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_start_page_not_found(client: AsyncClient) -> None:
    """GET /oauth/start/{id} for unknown session returns 404."""
    with patch(
        "contactsafe_server.oauth.router._build_oauth_service"
    ) as mock_oauth_svc:
        mock_oauth_svc.return_value.get_session_by_id = AsyncMock(return_value=None)

        resp = await client.get(f"/oauth/start/{uuid.uuid4()}")

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_start_page_pending_session(client: AsyncClient) -> None:
    """GET /oauth/start/{id} for pending session returns start template."""
    session: ConnectSession = _make_session(status=SessionStatus.PENDING.value)

    with patch(
        "contactsafe_server.oauth.router._build_oauth_service"
    ) as mock_oauth_svc:
        mock_oauth_svc.return_value.get_session_by_id = AsyncMock(return_value=session)

        resp = await client.get(f"/oauth/start/{session.id}")

    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    assert f"/oauth/authorize/{session.id}" in resp.text


@pytest.mark.asyncio
async def test_start_page_connected_session(client: AsyncClient) -> None:
    """GET /oauth/start/{id} for connected session returns connected template."""
    session: ConnectSession = _make_session(status=SessionStatus.CONNECTED.value)

    with patch(
        "contactsafe_server.oauth.router._build_oauth_service"
    ) as mock_oauth_svc:
        mock_oauth_svc.return_value.get_session_by_id = AsyncMock(return_value=session)

        resp = await client.get(f"/oauth/start/{session.id}")

    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]


# ---------------------------------------------------------------------------
# GET /oauth/authorize/{session_id}
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_authorize_session_not_found(client: AsyncClient) -> None:
    """GET /oauth/authorize/{id} for unknown session returns 404."""
    with patch(
        "contactsafe_server.oauth.router._build_oauth_service"
    ) as mock_oauth_svc:
        mock_oauth_svc.return_value.get_session_by_id = AsyncMock(return_value=None)

        resp = await client.get(
            f"/oauth/authorize/{uuid.uuid4()}", follow_redirects=False
        )

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_authorize_session_connected_redirects_to_complete(
    client: AsyncClient,
) -> None:
    """GET /oauth/authorize/{id} for connected session redirects to complete."""
    session: ConnectSession = _make_session(status=SessionStatus.CONNECTED.value)

    with patch(
        "contactsafe_server.oauth.router._build_oauth_service"
    ) as mock_oauth_svc:
        mock_oauth_svc.return_value.get_session_by_id = AsyncMock(return_value=session)

        resp = await client.get(
            f"/oauth/authorize/{session.id}", follow_redirects=False
        )

    assert resp.status_code == 302
    assert f"/oauth/complete/{session.id}" in resp.headers["location"]


@pytest.mark.asyncio
async def test_authorize_session_pending_redirects_to_google(
    client: AsyncClient,
) -> None:
    """GET /oauth/authorize/{id} for pending session redirects to Google."""
    session: ConnectSession = _make_session(status=SessionStatus.PENDING.value)
    google_url: str = "https://accounts.google.com/auth?state=xyz"

    with patch(
        "contactsafe_server.oauth.router._build_oauth_service"
    ) as mock_oauth_svc:
        mock_oauth_svc.return_value.get_session_by_id = AsyncMock(return_value=session)
        mock_oauth_svc.return_value.build_google_authorization_url = MagicMock(
            return_value=google_url
        )

        resp = await client.get(
            f"/oauth/authorize/{session.id}", follow_redirects=False
        )

    assert resp.status_code == 302
    assert resp.headers["location"] == google_url


# ---------------------------------------------------------------------------
# GET /oauth/callback
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_callback_error_param(client: AsyncClient) -> None:
    """GET /oauth/callback with error param returns error HTML."""
    resp = await client.get("/oauth/callback", params={"error": "access_denied"})
    assert resp.status_code == 400
    assert "access_denied" in resp.text


@pytest.mark.asyncio
async def test_callback_missing_code(client: AsyncClient) -> None:
    """GET /oauth/callback with missing code returns 400."""
    resp = await client.get("/oauth/callback", params={"state": "s"})
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_callback_missing_state(client: AsyncClient) -> None:
    """GET /oauth/callback with missing state returns 400."""
    resp = await client.get("/oauth/callback", params={"code": "c"})
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_callback_invalid_state(client: AsyncClient) -> None:
    """GET /oauth/callback with unknown state returns 400."""
    with patch(
        "contactsafe_server.oauth.router._build_oauth_service"
    ) as mock_oauth_svc:
        mock_oauth_svc.return_value.get_session_by_state = AsyncMock(return_value=None)

        resp = await client.get(
            "/oauth/callback", params={"code": "c", "state": "bad-state"}
        )

    assert resp.status_code == 400
    assert "Invalid OAuth state" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_callback_success_no_redirect(client: AsyncClient) -> None:
    """GET /oauth/callback success with no redirect_uri returns complete HTML."""
    session: ConnectSession = _make_session(oauth_redirect_uri=None)
    user: User = _make_user()
    source: Source = _make_source(user.id)

    with (
        patch(
            "contactsafe_server.oauth.router._build_oauth_service"
        ) as mock_oauth_svc,
        patch(
            "contactsafe_server.oauth.router.build_source_service"
        ) as mock_source_svc,
    ):
        mock_oauth_svc.return_value.get_session_by_state = AsyncMock(
            return_value=session
        )
        mock_oauth_svc.return_value.complete_oauth = AsyncMock(
            return_value=(user, source)
        )
        mock_source_svc.return_value.request_sync = AsyncMock(return_value=None)

        resp = await client.get(
            "/oauth/callback", params={"code": "google-code", "state": session.state}
        )

    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    assert user.email in resp.text


@pytest.mark.asyncio
async def test_callback_success_with_redirect(client: AsyncClient) -> None:
    """GET /oauth/callback success with redirect_uri redirects with auth code."""
    session: ConnectSession = _make_session(
        oauth_redirect_uri="http://localhost:3000/callback",
        oauth_client_state="client-state-abc",
        requested_scopes=["contactsafe:read"],
    )
    user: User = _make_user()
    source: Source = _make_source(user.id)
    redirect_url: str = (
        "http://localhost:3000/callback?code=auth-code&state=client-state-abc"
    )

    with (
        patch(
            "contactsafe_server.oauth.router._build_oauth_service"
        ) as mock_oauth_svc,
        patch(
            "contactsafe_server.oauth.router._build_oauth_server_service"
        ) as mock_server_svc,
        patch(
            "contactsafe_server.oauth.router.build_source_service"
        ) as mock_source_svc,
    ):
        mock_oauth_svc.return_value.get_session_by_state = AsyncMock(
            return_value=session
        )
        mock_oauth_svc.return_value.complete_oauth = AsyncMock(
            return_value=(user, source)
        )
        mock_source_svc.return_value.request_sync = AsyncMock(return_value=None)
        mock_server_svc.return_value.create_authorization_code = AsyncMock(
            return_value="auth-code"
        )
        mock_server_svc.return_value.build_client_redirect_url = MagicMock(
            return_value=redirect_url
        )

        resp = await client.get(
            "/oauth/callback",
            params={"code": "google-code", "state": session.state},
            follow_redirects=False,
        )

    assert resp.status_code == 302
    assert resp.headers["location"] == redirect_url


@pytest.mark.asyncio
async def test_callback_oauth_failure_with_redirect(client: AsyncClient) -> None:
    """GET /oauth/callback failure with redirect_uri sends error redirect."""
    session: ConnectSession = _make_session(
        oauth_redirect_uri="http://localhost:3000/callback",
        oauth_client_state="cs",
    )
    error_url: str = "http://localhost:3000/callback?error=server_error&state=cs"

    with (
        patch(
            "contactsafe_server.oauth.router._build_oauth_service"
        ) as mock_oauth_svc,
        patch(
            "contactsafe_server.oauth.router._build_oauth_server_service"
        ) as mock_server_svc,
    ):
        mock_oauth_svc.return_value.get_session_by_state = AsyncMock(
            return_value=session
        )
        mock_oauth_svc.return_value.complete_oauth = AsyncMock(
            side_effect=RuntimeError("Google API down")
        )
        mock_oauth_svc.return_value.mark_session_failed = AsyncMock(return_value=None)
        mock_server_svc.return_value.build_client_redirect_url = MagicMock(
            return_value=error_url
        )

        resp = await client.get(
            "/oauth/callback",
            params={"code": "bad-code", "state": session.state},
            follow_redirects=False,
        )

    assert resp.status_code == 302
    assert resp.headers["location"] == error_url


@pytest.mark.asyncio
async def test_callback_oauth_failure_no_redirect(client: AsyncClient) -> None:
    """GET /oauth/callback failure without redirect_uri returns error HTML."""
    session: ConnectSession = _make_session(oauth_redirect_uri=None)

    with patch(
        "contactsafe_server.oauth.router._build_oauth_service"
    ) as mock_oauth_svc:
        mock_oauth_svc.return_value.get_session_by_state = AsyncMock(
            return_value=session
        )
        mock_oauth_svc.return_value.complete_oauth = AsyncMock(
            side_effect=RuntimeError("Token exchange failed")
        )
        mock_oauth_svc.return_value.mark_session_failed = AsyncMock(return_value=None)

        resp = await client.get(
            "/oauth/callback", params={"code": "bad", "state": session.state}
        )

    assert resp.status_code == 500
    assert "Token exchange failed" in resp.text


@pytest.mark.asyncio
async def test_callback_post_redirect_failure(client: AsyncClient) -> None:
    """GET /oauth/callback success but redirect build fails returns error HTML."""
    session: ConnectSession = _make_session(
        oauth_redirect_uri="http://localhost:3000/callback",
        requested_scopes=["contactsafe:read"],
    )
    user: User = _make_user()
    source: Source = _make_source(user.id)

    with (
        patch(
            "contactsafe_server.oauth.router._build_oauth_service"
        ) as mock_oauth_svc,
        patch(
            "contactsafe_server.oauth.router._build_oauth_server_service"
        ) as mock_server_svc,
        patch(
            "contactsafe_server.oauth.router.build_source_service"
        ) as mock_source_svc,
    ):
        mock_oauth_svc.return_value.get_session_by_state = AsyncMock(
            return_value=session
        )
        mock_oauth_svc.return_value.complete_oauth = AsyncMock(
            return_value=(user, source)
        )
        mock_source_svc.return_value.request_sync = AsyncMock(return_value=None)
        mock_server_svc.return_value.create_authorization_code = AsyncMock(
            side_effect=RuntimeError("DB write failed")
        )

        resp = await client.get(
            "/oauth/callback", params={"code": "c", "state": session.state}
        )

    assert resp.status_code == 500
    assert "redirect failed" in resp.text


# ---------------------------------------------------------------------------
# GET /oauth/complete/{session_id}
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_complete_page_not_found(client: AsyncClient) -> None:
    """GET /oauth/complete/{id} for unknown session returns 404."""
    with patch(
        "contactsafe_server.oauth.router._build_oauth_service"
    ) as mock_oauth_svc:
        mock_oauth_svc.return_value.get_session_by_id = AsyncMock(return_value=None)

        resp = await client.get(f"/oauth/complete/{uuid.uuid4()}")

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_complete_page_no_user(client: AsyncClient) -> None:
    """GET /oauth/complete/{id} for session with no user_id returns 404."""
    session: ConnectSession = _make_session(user_id=None)

    with patch(
        "contactsafe_server.oauth.router._build_oauth_service"
    ) as mock_oauth_svc:
        mock_oauth_svc.return_value.get_session_by_id = AsyncMock(return_value=session)

        resp = await client.get(f"/oauth/complete/{session.id}")

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_complete_page_success() -> None:
    """GET /oauth/complete/{id} for valid session returns complete HTML."""
    from httpx import ASGITransport
    from contactsafe_server.main import create_app
    from contactsafe_server.oauth.router import get_db_session

    user: User = _make_user(email="done@example.com")
    session: ConnectSession = _make_session(
        status=SessionStatus.CONNECTED.value, user_id=user.id
    )

    mock_db = AsyncMock()
    mock_db.get = AsyncMock(return_value=user)

    async def _override_db() -> Any:
        yield mock_db

    app = create_app()
    app.dependency_overrides[get_db_session] = _override_db

    with patch(
        "contactsafe_server.oauth.router._build_oauth_service"
    ) as mock_oauth_svc:
        mock_oauth_svc.return_value.get_session_by_id = AsyncMock(return_value=session)

        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as ac:
            resp = await ac.get(f"/oauth/complete/{session.id}")

    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    assert "done@example.com" in resp.text
