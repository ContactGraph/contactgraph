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
    assert "ContactGraph" in response.text
    assert "Turn your contacts into a superpower." in response.text
    assert 'property="og:title"' in response.text
    assert 'name="twitter:description"' in response.text
    assert 'href="/skill.md"' in response.text
    assert 'href="/mcp"' in response.text
    assert "https://github.com/contactsafe/contactsafe" in response.text
    assert 'href="/manifesto"' in response.text
    assert "for agents" not in response.text.lower()
    assert "for humans" not in response.text.lower()


@pytest.mark.asyncio
async def test_manifesto_page(client: AsyncClient) -> None:
    response = await client.get("/manifesto")
    assert response.status_code == 200
    assert "The ContactGraph Manifesto" in response.text
    assert 'property="og:description"' in response.text
    assert "Turn your contacts into a superpower." in response.text
    assert "We gave away our relationships" in response.text
    assert 'href="/"' in response.text
    assert "# THE CONTACTGRAPH MANIFESTO" not in response.text
    assert "## WE GAVE AWAY" not in response.text
    assert "<strong>ContactGraph is that graph.</strong>" in response.text


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
    assert response.headers["location"] == "http://testserver"


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
