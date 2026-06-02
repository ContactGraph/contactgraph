import ssl
from functools import lru_cache
from typing import Any, Literal
from urllib.parse import urlparse

import certifi
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from mcp.server.transport_security import TransportSecuritySettings


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: Literal["development", "staging", "production"] = "development"
    base_url: str = "http://localhost:8000"
    log_level: str = "info"
    database_echo: bool = Field(default=False, description="Echo all SQL statements (very verbose)")


    database_url: str = Field(
        default="postgresql+asyncpg://contactsafe:contactsafe@localhost:5432/contactsafe"
    )
    # Set true for Supabase (or leave unset to auto-detect *.supabase.co in DATABASE_URL)
    database_ssl: bool | None = Field(default=None)
    # macOS uv Python often lacks system CA certs; set false for local Supabase dev if needed
    database_ssl_verify: bool = Field(default=True)

    token_encryption_key: str = Field(
        description="Fernet key for encrypting OAuth tokens at rest"
    )
    session_secret: str = Field(description="Secret for signing OAuth state parameters")

    jwt_signing_key: str | None = Field(
        default=None,
        description="HMAC secret for MCP JWT tokens; falls back to SESSION_SECRET in dev",
    )
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 15
    jwt_refresh_token_expire_days: int = 30
    jwt_issuer: str | None = Field(
        default=None,
        description="JWT issuer claim; defaults to BASE_URL",
    )
    jwt_audience: str | None = Field(
        default=None,
        description="JWT audience (RFC 8707 resource); defaults to canonical MCP URL",
    )

    google_client_id: str
    google_client_secret: str
    google_redirect_uri: str = "http://localhost:8000/oauth/callback"

    google_scopes: list[str] = Field(
        default_factory=lambda: [
            "openid",
            "email",
            "profile",
            "https://www.googleapis.com/auth/gmail.readonly",
            "https://www.googleapis.com/auth/calendar.readonly",
            "https://www.googleapis.com/auth/contacts.readonly",
        ]
    )

    mcp_path: str = "/mcp"

    import_initial_contact_target: int = Field(
        default=200,
        description="Contacts resolved before marking import partial",
    )
    import_partial_contact_target: int = Field(
        default=50,
        description="Contacts resolved before the graph becomes queryable (partial)",
    )
    import_progress_commit_messages: int = Field(
        default=25,
        description="Commit scan/upsert progress to the DB every N Gmail messages",
    )
    import_sent_max_messages: int = Field(
        default=10000,
        description="Max sent-mail messages scanned during Phase 2 import",
    )
    import_timeline_max_contacts: int = Field(
        default=1000,
        description="Max contacts to fetch Gmail timelines for in Phase 3",
    )
    import_timeline_max_pages: int = Field(
        default=10,
        description="Max pagination depth when finding earliest message per contact",
    )

    import_contacts_max_results: int = Field(
        default=2000,
        description="Max Google Contacts fetched per sync",
    )
    import_contacts_page_size: int = Field(
        default=100,
        description="Page size for People API connections.list (max 1000)",
    )

    openai_api_key: str | None = Field(default=None, description="OpenAI API key for query planning")
    openai_base_url: str = Field(default="https://api.openai.com/v1")
    openai_query_model: str = Field(default="gpt-4o-mini")
    openai_enrichment_model: str = Field(default="gpt-4o-mini")
    openai_embedding_model: str = Field(default="text-embedding-3-small")
    enrichment_contact_limit: int = Field(
        default=100,
        description="Max contacts to LLM-classify per sync",
    )

    exa_api_key: str | None = Field(
        default=None,
        description="Exa API key for web enrichment during ingest",
    )
    exa_base_url: str = Field(default="https://api.exa.ai")
    exa_enrichment_contact_limit: int = Field(
        default=50,
        description="Max contacts to Exa-enrich per sync (top tie strength)",
    )
    exa_search_num_results: int = Field(
        default=3,
        description="Exa search results per contact",
    )
    exa_request_timeout_seconds: float = Field(
        default=30.0,
        description="HTTP timeout for Exa API requests",
    )
    exa_activity_search_num_results: int = Field(
        default=3,
        description="Exa personal_site search results per contact",
    )

    tavily_api_key: str | None = Field(
        default=None,
        description="Tavily API key for web enrichment fallback",
    )
    tavily_base_url: str = Field(default="https://api.tavily.com")
    tavily_search_depth: Literal["basic", "advanced"] = Field(default="basic")
    tavily_search_num_results: int = Field(default=3)
    tavily_request_timeout_seconds: float = Field(default=30.0)

    serper_api_key: str | None = Field(
        default=None,
        description="Serper API key for Google SERP enrichment fallback",
    )
    serper_base_url: str = Field(default="https://google.serper.dev")
    serper_search_num_results: int = Field(default=3)
    serper_request_timeout_seconds: float = Field(default=30.0)

    web_enrichment_contact_limit: int = Field(
        default=50,
        description="Max contacts for web discovery enrichment per sync",
    )
    platform_activity_enabled: bool = Field(
        default=False,
        description="Tier 2: fetch Bluesky/GitHub posts when social handles are discovered",
    )
    platform_activity_max_posts: int = Field(default=5)
    platform_activity_timeout_seconds: float = Field(default=20.0)

    web_enrichment_ttl_days: int = Field(
        default=30,
        description="Days before re-querying web enrichment providers for a contact",
    )

    @field_validator("database_url", mode="before")
    @classmethod
    def ensure_asyncpg_driver(cls, value: str) -> str:
        url: str = str(value)
        if url.startswith("postgresql://"):
            return url.replace("postgresql://", "postgresql+asyncpg://", 1)
        return url

    @property
    def database_connect_args(self) -> dict[str, Any]:
        use_ssl: bool
        if self.database_ssl is not None:
            use_ssl = self.database_ssl
        else:
            use_ssl = "supabase.co" in self.database_url
        if not use_ssl:
            return {}
        if self.database_ssl_verify:
            ctx: ssl.SSLContext = ssl.create_default_context(cafile=certifi.where())
        else:
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
        return {"ssl": ctx}

    @property
    def oauth_start_url_template(self) -> str:
        return f"{self.base_url.rstrip('/')}/oauth/start/{{session_id}}"

    @property
    def effective_jwt_signing_key(self) -> str:
        return self.jwt_signing_key or self.session_secret

    @property
    def effective_jwt_issuer(self) -> str:
        return (self.jwt_issuer or self.base_url).rstrip("/")

    @property
    def canonical_mcp_resource(self) -> str:
        """RFC 8707 canonical resource: lowercase scheme/host, no trailing slash."""
        parsed_base: str = self.base_url.strip().rstrip("/")
        if "://" in parsed_base:
            scheme, rest = parsed_base.split("://", 1)
            parsed_base = f"{scheme.lower()}://{rest.lower()}"
        path: str = self.mcp_path.rstrip("/")
        return f"{parsed_base}{path}"

    @property
    def effective_jwt_audience(self) -> str:
        return self.jwt_audience or self.canonical_mcp_resource

    @property
    def mcp_resource_url(self) -> str:
        return self.canonical_mcp_resource

    @property
    def mcp_transport_security(self) -> TransportSecuritySettings:
        """DNS rebinding protection for the MCP SDK transport layer."""
        if self.app_env != "production":
            return TransportSecuritySettings(enable_dns_rebinding_protection=False)

        hostname: str = (urlparse(self.base_url).hostname or "localhost").lower()
        allowed_hosts: list[str] = [
            hostname,
            f"{hostname}:*",
            "localhost",
            "localhost:*",
            "127.0.0.1",
            "127.0.0.1:*",
        ]
        return TransportSecuritySettings(
            enable_dns_rebinding_protection=True,
            allowed_hosts=allowed_hosts,
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()  # pyright: ignore[reportCallIssue]
