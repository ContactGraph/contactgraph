from fastapi import APIRouter, Depends

from contactsafe_server.config import Settings, get_settings
from contactsafe_server.services.jwt_service import DEFAULT_MCP_SCOPES

router: APIRouter = APIRouter(tags=["oauth-metadata"])


def _protected_resource_document(settings: Settings) -> dict[str, object]:
    base: str = settings.base_url.rstrip("/")
    return {
        "resource": settings.canonical_mcp_resource,
        "authorization_servers": [base],
        "scopes_supported": list(DEFAULT_MCP_SCOPES),
    }


@router.get("/.well-known/oauth-protected-resource")
async def oauth_protected_resource_metadata(
    settings: Settings = Depends(get_settings),
) -> dict[str, object]:
    return _protected_resource_document(settings)


@router.get("/mcp/.well-known/oauth-protected-resource")
async def mcp_oauth_protected_resource_metadata(
    settings: Settings = Depends(get_settings),
) -> dict[str, object]:
    return _protected_resource_document(settings)


@router.get("/.well-known/oauth-authorization-server")
async def oauth_authorization_server_metadata(
    settings: Settings = Depends(get_settings),
) -> dict[str, object]:
    base: str = settings.base_url.rstrip("/")
    return {
        "issuer": settings.effective_jwt_issuer,
        "authorization_endpoint": f"{base}/oauth/authorize",
        "token_endpoint": f"{base}/oauth/token",
        "registration_endpoint": f"{base}/oauth/register",
        "scopes_supported": list(DEFAULT_MCP_SCOPES),
        "response_types_supported": ["code"],
        "code_challenge_methods_supported": ["S256"],
        "grant_types_supported": ["authorization_code", "refresh_token"],
        "token_endpoint_auth_methods_supported": ["none"],
    }
