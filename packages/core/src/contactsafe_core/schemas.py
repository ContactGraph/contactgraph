from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from contactsafe_core.enums import (
    EnrichmentRunState,
    SessionStatus,
    SourceConnectionStatus,
    SourceType,
    SyncState,
    TrustListInviteStatus,
    TrustListMembershipStatus,
)
from contactsafe_core.query_plan import QueryPlan


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
    system_messages: list[str] = Field(default_factory=list)


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
    access_token: str | None = None
    refresh_token: str | None = None
    system_messages: list[str] = Field(default_factory=list)
    upload_url: str | None = None
    upload_instructions: str | None = None


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
    system_messages: list[str] = Field(default_factory=list)


class SyncSourceResult(BaseModel):
    """Response from sync_source MCP tool."""

    source_id: UUID
    scheduled: bool
    sync_state: SyncState
    email: str | None = None
    message: str
    system_messages: list[str] = Field(default_factory=list)


class PersonMatch(BaseModel):
    person_id: UUID
    name: str
    emails: list[str]
    org_name: str | None = None
    current_role: str | None = None
    inferred_categories: list[str] = Field(default_factory=list)
    descriptive_tags: list[str] = Field(default_factory=list)
    social_profiles: dict[str, str] = Field(default_factory=dict)
    bio_summary: str | None = None
    also_known_as: list[str] = Field(default_factory=list)
    last_seen_in_email: datetime | None = None
    tie_strength_score: float = 0.0
    match_reason: str = ""
    relevance: str = ""


class CategoryCount(BaseModel):
    category: str
    count: int


class OrgCount(BaseModel):
    org_name: str
    count: int


class DescribeGraphResult(BaseModel):
    """High-level summary of the user's contact graph."""

    total_contacts: int = 0
    human_contacts: int = 0
    broadcast_contacts: int = 0
    automated_contacts: int = 0
    queryable_contacts: int = 0
    top_categories: list[CategoryCount] = Field(default_factory=lambda: list[CategoryCount]())
    top_orgs: list[OrgCount] = Field(default_factory=lambda: list[OrgCount]())
    strongest_ties: list[PersonMatch] = Field(default_factory=lambda: list[PersonMatch]())
    message: str
    system_messages: list[str] = Field(default_factory=list)


class SecondDegreeMatch(BaseModel):
    """A contact found via a trust-list member's graph (identity-level only)."""

    holder_name: str
    holder_user_id: UUID
    person_id: UUID
    person_name: str
    person_org: str | None = None
    person_role: str | None = None
    person_categories: list[str] = Field(default_factory=list)
    person_location: str | None = None
    match_reason: str = ""


class QueryNetworkResult(BaseModel):
    question: str
    matches: list[PersonMatch] = Field(default_factory=lambda: list[PersonMatch]())
    second_degree_matches: list[SecondDegreeMatch] = Field(default_factory=list)
    message: str
    applied_plan: QueryPlan | None = None
    system_messages: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Trust List schemas
# ---------------------------------------------------------------------------


class TrustListMemberSummary(BaseModel):
    membership_id: UUID
    user_id: UUID
    email: str
    name: str | None = None
    status: TrustListMembershipStatus
    established_at: datetime


class TrustListInviteSummary(BaseModel):
    invite_id: UUID
    invitee_email: str
    status: TrustListInviteStatus
    created_at: datetime


class PendingInboundInvite(BaseModel):
    invite_id: UUID
    inviter_email: str
    inviter_name: str | None = None
    created_at: datetime


class ViewTrustedUsersResult(BaseModel):
    members: list[TrustListMemberSummary] = Field(default_factory=list)
    outbound_invites: list[TrustListInviteSummary] = Field(default_factory=list)
    inbound_invites: list[PendingInboundInvite] = Field(default_factory=list)
    max_members: int = 20
    message: str
    system_messages: list[str] = Field(default_factory=list)


class EditTrustedUsersResult(BaseModel):
    added: list[str] = Field(default_factory=list)
    removed: list[str] = Field(default_factory=list)
    accepted: list[str] = Field(default_factory=list)
    declined: list[str] = Field(default_factory=list)
    privacy_updated: list[str] = Field(default_factory=list)
    invite_copy: str | None = None
    message: str
    system_messages: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Poll-connect (unauthenticated token dispensing)
# ---------------------------------------------------------------------------


class PollConnectResult(BaseModel):
    status: str
    access_token: str | None = None
    refresh_token: str | None = None
    email: str | None = None
    message: str


# ---------------------------------------------------------------------------
# REST API request bodies
# ---------------------------------------------------------------------------


class ConnectSourceRequest(BaseModel):
    source_type: str = "google_mail"
    user_token: str | None = None


class GetSourceStatusRequest(BaseModel):
    source_id: str | None = None


class SyncSourceRequest(BaseModel):
    source_id: str | None = None


class StartEnrichmentResult(BaseModel):
    run_id: UUID | None = None
    scheduled: bool
    state: EnrichmentRunState
    message: str
    system_messages: list[str] = Field(default_factory=list)


class EnrichmentStatusResult(BaseModel):
    run_id: UUID | None = None
    state: EnrichmentRunState
    contacts_total: int = 0
    contacts_enriched: int = 0
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error: str | None = None
    message: str
    system_messages: list[str] = Field(default_factory=list)


class UploadSourceRequest(BaseModel):
    source_type: str
    filename: str
    content: str


class UploadSourceResult(BaseModel):
    source_id: UUID
    scheduled: bool
    sync_state: SyncState
    message: str
    system_messages: list[str] = Field(default_factory=list)


class UserProfileResult(BaseModel):
    display_name: str | None = None
    location: str | None = None
    google_profile_name: str | None = None
    message: str = ""


class UpdateUserProfileRequest(BaseModel):
    display_name: str | None = None
    location: str | None = None


class QueryNetworkRequest(BaseModel):
    question: str


class EditTrustedUsersRequest(BaseModel):
    add: list[str] | None = None
    remove: list[str] | None = None
    accept: list[str] | None = None
    decline: list[str] | None = None
    set_privacy: list[dict[str, str]] | None = None
