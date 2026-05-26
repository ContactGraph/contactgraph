"""Tests for MCP auth middleware and OAuth metadata endpoints."""

import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.applications import Starlette
from starlette.responses import PlainTextResponse
from starlette.routing import Route

from contactsafe_server.config import get_settings
from contactsafe_server.deps import build_jwt_service
from contactsafe_server.mcp.auth_middleware import McpAuthMiddleware
from contactsafe_server.services.jwt_service import JWTService
from contactsafe_server.services.oauth_server_service import OAuthServerService, parse_scopes_param


async def _ok_handler(_request: object) -> PlainTextResponse:
    return PlainTextResponse("ok")


@pytest.fixture
def jwt_service() -> JWTService:
    return build_jwt_service(get_settings())


def _make_bearer(user_id: uuid.UUID, jwt_service: JWTService) -> str:
    return jwt_service.create_access_token(user_id, ["contactsafe:read"])


@pytest.mark.asyncio
async def test_well_known_protected_resource(client: AsyncClient) -> None:
    response = await client.get("/.well-known/oauth-protected-resource")
    assert response.status_code == 200
    body: dict[str, object] = response.json()
    assert "authorization_servers" in body
    assert "contactsafe:read" in body["scopes_supported"]  # type: ignore[index]


@pytest.mark.asyncio
async def test_well_known_authorization_server(client: AsyncClient) -> None:
    response = await client.get("/.well-known/oauth-authorization-server")
    assert response.status_code == 200
    body: dict[str, object] = response.json()
    assert body["token_endpoint"] == "http://testserver/oauth/token"
    assert body["registration_endpoint"] == "http://testserver/oauth/register"
    assert "S256" in body["code_challenge_methods_supported"]  # type: ignore[operator]


@pytest.mark.asyncio
async def test_mcp_missing_bearer_returns_401(jwt_service: JWTService) -> None:
    settings = get_settings()
    inner: Starlette = Starlette(routes=[Route("/", _ok_handler)])
    app = McpAuthMiddleware(inner, settings=settings, jwt_service=jwt_service)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        response = await ac.post("/")
    assert response.status_code == 401
    assert "WWW-Authenticate" in response.headers
    assert "resource_metadata" in response.headers["WWW-Authenticate"]
    body: dict[str, str] = response.json()
    assert body["error"] == "invalid_token"


@pytest.mark.asyncio
async def test_mcp_options_passes_without_auth(jwt_service: JWTService) -> None:
    settings = get_settings()
    inner: Starlette = Starlette(routes=[Route("/", _ok_handler)])
    app = McpAuthMiddleware(inner, settings=settings, jwt_service=jwt_service)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        response = await ac.options("/")
    assert response.status_code != 401


@pytest.mark.asyncio
async def test_oauth_register_client(
    client: AsyncClient,
    postgres_available: bool,
) -> None:
    if not postgres_available:
        pytest.skip("Postgres not available")
    response = await client.post(
        "/oauth/register",
        json={
            "redirect_uris": ["https://claude.ai/api/mcp/auth_callback"],
            "token_endpoint_auth_method": "none",
            "client_name": "Claude Test",
        },
    )
    assert response.status_code == 201
    body: dict[str, object] = response.json()
    assert body["client_id"]
    assert body["redirect_uris"] == ["https://claude.ai/api/mcp/auth_callback"]


@pytest.mark.asyncio
async def test_mcp_invalid_bearer_returns_401(jwt_service: JWTService) -> None:
    settings = get_settings()
    inner: Starlette = Starlette(routes=[Route("/", _ok_handler)])
    app = McpAuthMiddleware(inner, settings=settings, jwt_service=jwt_service)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        response = await ac.get("/", headers={"Authorization": "Bearer not-a-valid-token"})
    assert response.status_code == 401
    assert "WWW-Authenticate" in response.headers
    body: dict[str, str] = response.json()
    assert body["error"] == "invalid_token"


@pytest.mark.asyncio
async def test_mcp_valid_bearer_reaches_app(jwt_service: JWTService) -> None:
    user_id: uuid.UUID = uuid.uuid4()
    token: str = _make_bearer(user_id, jwt_service)
    settings = get_settings()
    inner: Starlette = Starlette(routes=[Route("/", _ok_handler)])
    app = McpAuthMiddleware(inner, settings=settings, jwt_service=jwt_service)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        response = await ac.get("/", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    assert response.text == "ok"


@pytest.mark.asyncio
async def test_oauth_token_rejects_invalid_grant(
    db_session: AsyncSession,
    postgres_available: bool,
) -> None:
    if not postgres_available:
        pytest.skip("Postgres not available")
    settings = get_settings()
    oauth_server = OAuthServerService(
        db=db_session,
        settings=settings,
        jwt_service=build_jwt_service(settings),
    )
    with pytest.raises(ValueError, match="Invalid authorization code"):
        await oauth_server.exchange_authorization_code(
            code="invalid",
            redirect_uri="http://localhost/callback",
            code_verifier="verifier",
        )


def test_parse_scopes_param_rejects_admin_by_default() -> None:
    with pytest.raises(ValueError, match="Unsupported scope"):
        parse_scopes_param("contactsafe:read contactsafe:admin")


def test_parse_scopes_param_allows_default_scopes() -> None:
    assert parse_scopes_param("") == ["contactsafe:read", "contactsafe:write"]


def test_parse_scopes_param_allow_admin_flag() -> None:
    assert parse_scopes_param("contactsafe:read contactsafe:admin", allow_admin=True) == [
        "contactsafe:read",
        "contactsafe:admin",
    ]
