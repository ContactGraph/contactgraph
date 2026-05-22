from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from contactsafe_core.enums import (
    SessionStatus,
    SourceConnectionStatus,
    SourceType,
    SyncState,
)


class UserPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: str
    google_profile_name: str | None
    created_at: datetime


class SessionPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    status: SessionStatus
    user_id: UUID | None
    requested_scopes: list[str]
    created_at: datetime
    completed_at: datetime | None


class OAuthCredentialSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    provider: str
    scopes: list[str]
    is_valid: bool
    token_expires_at: datetime


class SourceSummary(BaseModel):
    source_id: UUID
    source_type: SourceType
    label: str
    external_account_id: str
    connection_status: SourceConnectionStatus
    sync_state: SyncState
    contacts_found: int = 0
    contacts_resolved: int = 0
    contacts_pending: int = 0


class ListSourcesResult(BaseModel):
    sources: list[SourceSummary] = Field(default_factory=lambda: list[SourceSummary]())
    message: str


class ConnectSourceResult(BaseModel):
    """Response from connect_source MCP tool."""

    connect_session_id: UUID
    oauth_url: str
    status: SessionStatus
    message: str
    already_connected: bool = False
    email: str | None = None
    scopes: list[str] = Field(default_factory=list)
    source_id: UUID | None = None


class SourceStatusResult(BaseModel):
    """Response from get_source_status MCP tool."""

    source_id: UUID
    connect_session_id: UUID | None = None
    status: SessionStatus
    connection_status: SourceConnectionStatus
    sync_state: SyncState
    email: str | None = None
    scopes: list[str] = Field(default_factory=list)
    contacts_found: int = 0
    contacts_resolved: int = 0
    contacts_pending: int = 0
    message: str


class SyncSourceResult(BaseModel):
    """Response from sync_source MCP tool."""

    source_id: UUID
    scheduled: bool
    sync_state: SyncState
    email: str | None = None
    message: str


class PersonMatch(BaseModel):
    person_id: UUID
    name: str
    emails: list[str]
    org_name: str | None = None
    last_seen_in_email: datetime | None = None
    tie_strength_score: float = 0.0
    relevance: str = ""


class QueryNetworkResult(BaseModel):
    question: str
    matches: list[PersonMatch] = Field(default_factory=lambda: list[PersonMatch]())
    message: str
