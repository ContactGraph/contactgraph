from functools import lru_cache
from typing import Literal

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

    @field_validator("database_url", mode="before")
    @classmethod
    def ensure_asyncpg_driver(cls, value: str) -> str:
        url: str = str(value)
        if url.startswith("postgresql://"):
            return url.replace("postgresql://", "postgresql+asyncpg://", 1)
        return url

    @property
    def oauth_start_url_template(self) -> str:
        return f"{self.base_url.rstrip('/')}/oauth/start/{{session_id}}"


@lru_cache
def get_settings() -> Settings:
    return Settings()  # pyright: ignore[reportCallIssue]
