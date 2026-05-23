import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_health(client: AsyncClient) -> None:
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_landing_page(client: AsyncClient) -> None:
    response = await client.get("/")
    assert response.status_code == 200
    assert "ContactSafe" in response.text
    assert "agent-native" in response.text


@pytest.mark.asyncio
async def test_skill_md(client: AsyncClient) -> None:
    response = await client.get("/skill.md")
    assert response.status_code == 200
    assert "connect_source" in response.text


@pytest.mark.asyncio
async def test_mcp_browser_request_redirects_to_marketing_site(client: AsyncClient) -> None:
    response = await client.get(
        "/mcp",
        headers={"Accept": "text/html,application/xhtml+xml"},
        follow_redirects=False,
    )
    assert response.status_code == 307
    assert response.headers["location"] == "https://www.contactsafe.ai"


@pytest.mark.asyncio
async def test_oauth_start_not_found(
    client: AsyncClient, postgres_available: bool
) -> None:
    import uuid

    if not postgres_available:
        pytest.skip("Postgres not available")

    missing_id: uuid.UUID = uuid.uuid4()
    response = await client.get(f"/oauth/start/{missing_id}")
    assert response.status_code == 404
