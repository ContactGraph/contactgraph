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
    database_pool_size: int = Field(
        default=3,
        description="SQLAlchemy pool size per process (keep low for Supabase session pooler)",
    )
    database_max_overflow: int = Field(
        default=2,
        description="Extra connections beyond pool_size under burst load",
    )

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

    web_base_url: str | None = Field(
        default=None,
        description="Public web app URL for upload links; defaults to BASE_URL",
    )
    upload_max_file_size_mb: int = Field(
        default=50,
        description="Max VCF/CSV upload size in MB",
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
    employment_recency_days: int = Field(
        default=365,
        description="Max age (days) for a signal to count as current employment",
    )
    enrichment_worker_concurrency: int = Field(
        default=3,
        description="Max concurrent per-contact enrichment workers",
    )
    enrichment_confidence_threshold: float = Field(
        default=0.7,
        description="Stop enrichment strategies when confidence reaches this score",
    )
    enrichment_max_retries: int = Field(
        default=3,
        description="Max attempts before marking a queue item failed",
    )
    enrichment_backoff_base_seconds: int = Field(
        default=300,
        description="Base backoff seconds between enrichment retries (exponential)",
    )
    enrichment_queue_poll_interval_seconds: float = Field(
        default=10.0,
        description="How often the enrichment poller checks for pending work",
    )
    enrichment_max_strategies_per_contact: int = Field(
        default=8,
        description="Max strategies to run per contact per attempt",
    )
    enrichment_email_domain_freshness_days: int = Field(
        default=180,
        description="Only trust email domain as current employer if seen within this window",
    )

    scrapingdog_api_key: str | None = Field(
        default=None,
        description="ScrapingDog API key for LinkedIn profile scraping",
    )
    scrapingdog_base_url: str = Field(default="https://api.scrapingdog.com")
    scrapingdog_request_timeout_seconds: float = Field(default=30.0)
    scrapingdog_retry_delay_seconds: float = Field(
        default=180.0,
        description="Delay before retrying a 202 (accepted, not yet scraped) response",
    )
    scrapingdog_concurrency: int = Field(
        default=1,
        description="Max concurrent ScrapingDog requests (plan-dependent)",
    )
    scrapingdog_request_delay_seconds: float = Field(
        default=2.0,
        description="Minimum delay between ScrapingDog requests for rate limiting",
    )

    theirstack_api_key: str | None = Field(
        default=None,
        description="TheirStack API key for aggregated job discovery",
    )
    theirstack_webhook_secret: str | None = Field(
        default=None,
        description="HMAC signing secret for TheirStack webhook verification",
    )

    admin_emails: list[str] = Field(
        default_factory=list,
        description="Email addresses that automatically receive contactsafe:admin scope on login",
    )
    theirstack_base_url: str = Field(default="https://api.theirstack.com")
    theirstack_request_timeout_seconds: float = Field(default=90.0)
    theirstack_job_max_age_days: int = Field(
        default=30,
        description="Max age of job postings returned by TheirStack searches",
    )

    job_discovery_request_timeout_seconds: float = Field(default=30.0)
    job_scrape_cooldown_hours: int = Field(
        default=24,
        description="Skip re-scraping an org if it was successfully checked within this window",
    )
    job_scan_poll_interval_minutes: int = Field(
        default=5,
        description="How often the global job scanner checks for orgs needing a scrape",
    )

    org_enrichment_cooldown_days: int = Field(
        default=30,
        description="Skip re-enriching an org if it was successfully enriched within this window",
    )
    org_enrichment_scan_poll_interval_minutes: int = Field(
        default=10,
        description="How often the global org enrichment scanner checks for orgs needing enrichment",
    )

    redis_url: str = Field(
        default="redis://localhost:6379",
        description="Redis URL for arq task queue and cross-process event pub/sub",
    )
    use_arq_worker: bool = Field(
        default=False,
        description="When true, background work is enqueued to arq instead of in-process asyncio tasks",
    )
    arq_max_jobs: int = Field(
        default=3,
        description="Max concurrent jobs per arq worker process",
    )
    arq_job_timeout_seconds: int = Field(
        default=600,
        description="Default arq job timeout in seconds",
    )

    resend_api_key: str | None = Field(
        default=None,
        description="Resend API key for transactional email; unset disables outbound email",
    )
    email_from_address: str = Field(
        default="ContactGraph <notifications@contactsafe.com>",
        description="From address for transactional emails",
    )
    email_digest_send_hour_utc: int = Field(
        default=15,
        ge=0,
        le=23,
        description="UTC hour when daily/weekly job digests are enqueued (~morning US)",
    )
    email_digest_min_match_score: int = Field(
        default=60,
        ge=0,
        le=100,
        description="Minimum match score for jobs included in email digests",
    )
    email_digest_max_jobs: int = Field(
        default=20,
        ge=1,
        le=100,
        description="Maximum jobs included in a single digest email",
    )
    email_unsubscribe_token_expire_days: int = Field(
        default=365,
        description="Lifetime of one-click unsubscribe tokens in email footers",
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
    def effective_web_base_url(self) -> str:
        return (self.web_base_url or self.base_url).rstrip("/")

    def upload_url_for_source(self, source_id: object) -> str:
        return f"{self.effective_web_base_url}/setup/upload/{source_id}"

    @property
    def upload_max_file_size_bytes(self) -> int:
        return self.upload_max_file_size_mb * 1024 * 1024

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
