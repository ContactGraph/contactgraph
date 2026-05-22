import ssl
from functools import lru_cache
from typing import Any, Literal

import certifi
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: Literal["development", "staging", "production"] = "development"
    base_url: str = "http://localhost:8000"
    log_level: str = "info"

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
        ]
    )

    mcp_path: str = "/mcp"

    import_initial_contact_target: int = Field(
        default=200,
        description="Contacts resolved before marking import partial",
    )
    import_max_messages: int = Field(
        default=500,
        description="Max Gmail messages scanned per import run",
    )
    import_gmail_query: str = Field(
        default="newer_than:1y",
        description="Gmail search query for import",
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


@lru_cache
def get_settings() -> Settings:
    return Settings()  # pyright: ignore[reportCallIssue]
