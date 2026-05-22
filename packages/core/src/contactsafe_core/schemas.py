from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from contactsafe_core.enums import ImportState, OAuthProvider, SessionStatus


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

    provider: OAuthProvider
    scopes: list[str]
    is_valid: bool
    token_expires_at: datetime


class ConnectGmailResult(BaseModel):
    """Response from connect_gmail MCP tool."""

    session_id: UUID
    oauth_url: str
    status: SessionStatus
    message: str
    already_connected: bool = False
    email: str | None = None
    scopes: list[str] = Field(default_factory=list)


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


class ImportStatus(BaseModel):
    """Response from get_import_status MCP tool."""

    session_id: UUID
    status: SessionStatus
    import_state: ImportState
    email: str | None = None
    scopes: list[str] = Field(default_factory=list)
    contacts_found: int = 0
    contacts_resolved: int = 0
    contacts_pending: int = 0
    message: str
