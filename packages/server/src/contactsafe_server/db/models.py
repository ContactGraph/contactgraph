import uuid
from datetime import UTC, date, datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    ARRAY,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    LargeBinary,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

EMBEDDING_DIMENSIONS: int = 1536


class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------------------
# Auth / infrastructure (unchanged)
# ---------------------------------------------------------------------------


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    google_profile_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    google_profile_picture: Mapped[str | None] = mapped_column(Text, nullable=True)
    display_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    location: Mapped[str | None] = mapped_column(Text, nullable=True)
    person_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("persons.id", ondelete="SET NULL"), nullable=True)
    job_monitor_list_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("org_lists.id", ondelete="SET NULL"),
        nullable=True,
    )
    job_monitor_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    job_preferences_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    job_suggested_roles: Mapped[str | None] = mapped_column(Text, nullable=True)
    job_location_pref: Mapped[str | None] = mapped_column(Text, nullable=True)
    job_location_city: Mapped[str | None] = mapped_column(Text, nullable=True)
    job_commute_max_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    job_commute_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    job_target_scope: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    preferred_funding_stages: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)
    job_scoring_weights: Mapped[dict[str, object] | None] = mapped_column(JSONB, nullable=True)
    job_digest_frequency: Mapped[str] = mapped_column(Text, nullable=False, default="daily")
    job_digest_last_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    person: Mapped["Person | None"] = relationship(foreign_keys=[person_id])
    job_monitor_list: Mapped["OrgList | None"] = relationship(foreign_keys=[job_monitor_list_id])
    identities: Mapped[list["UserIdentity"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    oauth_credentials: Mapped[list["OAuthCredential"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    sessions: Mapped[list["ConnectSession"]] = relationship(back_populates="user")
    authorization_codes: Mapped[list["AuthorizationCode"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    refresh_tokens: Mapped[list["RefreshToken"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    sources: Mapped[list["Source"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    person_observations: Mapped[list["UserPersonObservation"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    interaction_excerpts: Mapped[list["InteractionExcerpt"]] = relationship(back_populates="user", cascade="all, delete-orphan")


class UserIdentity(Base):
    __tablename__ = "user_identities"
    __table_args__ = (UniqueConstraint("kind", "value", name="uq_identity_kind_value"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    is_primary: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    user: Mapped["User"] = relationship(back_populates="identities")


class OAuthCredential(Base):
    __tablename__ = "oauth_credentials"
    __table_args__ = (UniqueConstraint("user_id", "provider", "external_account_id", name="uq_oauth_user_provider_account"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    source_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("sources.id", ondelete="SET NULL"), nullable=True)
    provider: Mapped[str] = mapped_column(String(32), nullable=False, default="google")
    external_account_id: Mapped[str] = mapped_column(Text, nullable=False)
    access_token_encrypted: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    refresh_token_encrypted: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    token_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    scopes: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False)
    is_valid: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    user: Mapped["User"] = relationship(back_populates="oauth_credentials")
    source: Mapped["Source | None"] = relationship(back_populates="oauth_credential")


class Source(Base):
    __tablename__ = "sources"
    __table_args__ = (UniqueConstraint("user_id", "source_type", "external_account_id", name="uq_source_user_type_account"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    source_type: Mapped[str] = mapped_column(String(64), nullable=False)
    label: Mapped[str] = mapped_column(Text, nullable=False)
    external_account_id: Mapped[str] = mapped_column(Text, nullable=False)
    connection_status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending_oauth")
    sync_state: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    contacts_found: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    contacts_resolved: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    contacts_pending: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    sync_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sync_completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sync_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    sync_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    upload_payload: Mapped[dict[str, object] | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    user: Mapped["User"] = relationship(back_populates="sources")
    oauth_credential: Mapped["OAuthCredential | None"] = relationship(back_populates="source", uselist=False)


class EnrichmentQueueItem(Base):
    __tablename__ = "enrichment_queue"
    __table_args__ = (
        {"comment": "Per-person enrichment work queue"},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    person_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("persons.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    trigger_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    enrichment_run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("enrichment_runs.id", ondelete="SET NULL"),
        nullable=True,
    )
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    strategies_attempted: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    strategies_remaining: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    result_confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    attempts_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_attempted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    next_attempt_after: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class EnrichmentRun(Base):
    __tablename__ = "enrichment_runs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    state: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    contacts_total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    contacts_enriched: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    progress_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class OrgEnrichmentRun(Base):
    __tablename__ = "org_enrichment_runs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    state: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    orgs_total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    orgs_enriched: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    progress_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class ConnectSession(Base):
    __tablename__ = "sessions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    state: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    requested_scopes: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False)
    oauth_redirect_uri: Mapped[str | None] = mapped_column(Text, nullable=True)
    oauth_client_state: Mapped[str | None] = mapped_column(Text, nullable=True)
    code_challenge: Mapped[str | None] = mapped_column(Text, nullable=True)
    code_challenge_method: Mapped[str | None] = mapped_column(String(16), nullable=True)
    token_dispensed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    poll_secret_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped["User | None"] = relationship(back_populates="sessions")


class AuthorizationCode(Base):
    __tablename__ = "authorization_codes"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    code_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    code_challenge: Mapped[str | None] = mapped_column(Text, nullable=True)
    code_challenge_method: Mapped[str | None] = mapped_column(String(16), nullable=True)
    redirect_uri: Mapped[str] = mapped_column(Text, nullable=False)
    scopes: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    user: Mapped["User"] = relationship(back_populates="authorization_codes")


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    scopes: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    user: Mapped["User"] = relationship(back_populates="refresh_tokens")


class OAuthClient(Base):
    __tablename__ = "oauth_clients"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_id: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    client_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    redirect_uris: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False)
    token_endpoint_auth_method: Mapped[str] = mapped_column(String(32), nullable=False, default="none")
    grant_types: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False)
    response_types: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


# ---------------------------------------------------------------------------
# Layer 1: Global entities
# ---------------------------------------------------------------------------


class Person(Base):
    __tablename__ = "persons"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    canonical_name: Mapped[str] = mapped_column(Text, nullable=False)
    primary_email: Mapped[str | None] = mapped_column(Text, nullable=True)
    current_org_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("orgs.id", ondelete="SET NULL"), nullable=True)
    current_org_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    current_role: Mapped[str | None] = mapped_column("current_role", Text, nullable=True, quote=True)
    bio_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    social_profiles: Mapped[dict[str, str]] = mapped_column(JSONB, nullable=False, default=dict)
    inferred_categories: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, default=list)
    descriptive_tags: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, default=list)
    phone_numbers: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, default=list)
    location: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    current_org: Mapped["Org | None"] = relationship(back_populates="persons", foreign_keys=[current_org_id])
    aliases: Mapped[list["PersonAlias"]] = relationship(back_populates="person", cascade="all, delete-orphan")
    employment_claims: Mapped[list["EmploymentClaim"]] = relationship(back_populates="person", cascade="all, delete-orphan")
    attribute_claims: Mapped[list["PersonAttributeClaim"]] = relationship(back_populates="person", cascade="all, delete-orphan")
    observations: Mapped[list["UserPersonObservation"]] = relationship(back_populates="person", cascade="all, delete-orphan")


class Org(Base):
    __tablename__ = "orgs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    canonical_name: Mapped[str] = mapped_column(Text, nullable=False)
    primary_domain: Mapped[str | None] = mapped_column(Text, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    careers_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    ats_provider: Mapped[str | None] = mapped_column(Text, nullable=True)
    ats_board_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    linkedin_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    categories: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, default=list)
    employee_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    company_size_band: Mapped[str | None] = mapped_column(String(32), nullable=True)
    funding_stage: Mapped[str | None] = mapped_column(String(32), nullable=True)
    attributes: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    persons: Mapped[list["Person"]] = relationship(back_populates="current_org", foreign_keys=[Person.current_org_id])
    aliases: Mapped[list["OrgAlias"]] = relationship(back_populates="org", cascade="all, delete-orphan")
    employment_claims: Mapped[list["EmploymentClaim"]] = relationship(back_populates="org", cascade="all, delete-orphan")
    jobs: Mapped[list["OrgJob"]] = relationship(back_populates="org", cascade="all, delete-orphan")
    job_scrape_runs: Mapped[list["JobScrapeRun"]] = relationship(back_populates="org", cascade="all, delete-orphan")
    enrichment_scrape_runs: Mapped[list["OrgEnrichmentScrapeRun"]] = relationship(
        back_populates="org",
        cascade="all, delete-orphan",
    )


class OrgJob(Base):
    __tablename__ = "org_jobs"
    __table_args__ = (
        UniqueConstraint("org_id", "external_job_id", "source", name="uq_org_job_external"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("orgs.id", ondelete="CASCADE"), nullable=False)
    external_job_id: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    location: Mapped[str | None] = mapped_column(Text, nullable=True)
    department: Mapped[str | None] = mapped_column(Text, nullable=True)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    description_snippet: Mapped[str | None] = mapped_column(Text, nullable=True)
    salary_min: Mapped[int | None] = mapped_column(Integer, nullable=True)
    salary_max: Mapped[int | None] = mapped_column(Integer, nullable=True)
    remote_status: Mapped[str | None] = mapped_column(Text, nullable=True)
    seniority_level: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    location_lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    location_lng: Mapped[float | None] = mapped_column(Float, nullable=True)
    location_normalized: Mapped[str | None] = mapped_column(String(128), nullable=True)
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    org: Mapped["Org"] = relationship(back_populates="jobs")


class JobScrapeRun(Base):
    __tablename__ = "job_scrape_runs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("orgs.id", ondelete="CASCADE"), nullable=False)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    jobs_found: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    new_jobs: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    org: Mapped["Org"] = relationship(back_populates="job_scrape_runs")


class OrgEnrichmentScrapeRun(Base):
    __tablename__ = "org_enrichment_scrape_runs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("orgs.id", ondelete="CASCADE"), nullable=False)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    fields_updated: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    org: Mapped["Org"] = relationship(back_populates="enrichment_scrape_runs")


class JobDiscoveryRun(Base):
    __tablename__ = "job_discovery_runs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    state: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    orgs_total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    orgs_processed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    jobs_found: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    new_jobs: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    progress_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class PersonAlias(Base):
    __tablename__ = "person_aliases"
    __table_args__ = (UniqueConstraint("kind", "value", name="uq_person_alias_kind_value"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    person_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("persons.id", ondelete="CASCADE"), nullable=False)
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.9)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    person: Mapped["Person"] = relationship(back_populates="aliases")


class OrgAlias(Base):
    __tablename__ = "org_aliases"
    __table_args__ = (UniqueConstraint("kind", "value", name="uq_org_alias_kind_value"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("orgs.id", ondelete="CASCADE"), nullable=False)
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.9)

    org: Mapped["Org"] = relationship(back_populates="aliases")


# ---------------------------------------------------------------------------
# Layer 2: Claims (global, with provenance)
# ---------------------------------------------------------------------------


class EmploymentClaim(Base):
    __tablename__ = "employment_claims"
    __table_args__ = (
        UniqueConstraint(
            "person_id",
            "org_id",
            "role_title",
            "started_at",
            "contributor_source_kind",
            "contributor_user_id",
            name="uq_employment_claim",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    person_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("persons.id", ondelete="CASCADE"), nullable=False)
    org_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("orgs.id", ondelete="CASCADE"), nullable=False)
    role_title: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    started_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    ended_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    contributor_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    contributor_source_kind: Mapped[str] = mapped_column(Text, nullable=False)
    contributor_source_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), default=lambda: datetime.now(UTC), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.7)
    evidence: Mapped[dict[str, object] | None] = mapped_column(JSONB, nullable=True)

    person: Mapped["Person"] = relationship(back_populates="employment_claims")
    org: Mapped["Org"] = relationship(back_populates="employment_claims")


class RelationshipClaim(Base):
    __tablename__ = "relationship_claims"
    __table_args__ = (
        UniqueConstraint("person_a_id", "person_b_id", "kind", "contributor_user_id", name="uq_relationship_claim"),
        CheckConstraint("person_a_id < person_b_id", name="ck_relationship_claim_order"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    person_a_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("persons.id", ondelete="CASCADE"), nullable=False)
    person_b_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("persons.id", ondelete="CASCADE"), nullable=False)
    kind: Mapped[str] = mapped_column(Text, nullable=False, default="co_thread")
    observed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    contributor_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    contributor_source_kind: Mapped[str] = mapped_column(Text, nullable=False, default="gmail")
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), default=lambda: datetime.now(UTC), nullable=False)
    last_seen_together_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    evidence: Mapped[dict[str, object] | None] = mapped_column(JSONB, nullable=True)


class PersonAttributeClaim(Base):
    __tablename__ = "person_attribute_claims"
    __table_args__ = (
        UniqueConstraint("person_id", "kind", "value", "contributor_source_kind", "contributor_user_id", name="uq_person_attr_claim"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    person_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("persons.id", ondelete="CASCADE"), nullable=False)
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    contributor_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    contributor_source_kind: Mapped[str] = mapped_column(Text, nullable=False)
    contributor_source_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), default=lambda: datetime.now(UTC), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.7)
    evidence: Mapped[dict[str, object] | None] = mapped_column(JSONB, nullable=True)

    person: Mapped["Person"] = relationship(back_populates="attribute_claims")


class OrgAttributeClaim(Base):
    __tablename__ = "org_attribute_claims"
    __table_args__ = (
        UniqueConstraint("org_id", "kind", "value", "contributor_source_kind", "contributor_user_id", name="uq_org_attr_claim"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("orgs.id", ondelete="CASCADE"), nullable=False)
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    contributor_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    contributor_source_kind: Mapped[str] = mapped_column(Text, nullable=False)
    contributor_source_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), default=lambda: datetime.now(UTC), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.7)
    evidence: Mapped[dict[str, object] | None] = mapped_column(JSONB, nullable=True)


class EnrichmentAttempt(Base):
    __tablename__ = "enrichment_attempts"
    __table_args__ = (
        UniqueConstraint("person_id", "source_kind", name="uq_enrichment_attempt"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    person_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("persons.id", ondelete="CASCADE"), nullable=False)
    source_kind: Mapped[str] = mapped_column(Text, nullable=False)
    last_attempted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    succeeded: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    result_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    contributor_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)


# ---------------------------------------------------------------------------
# Layer 3: Per-user observations
# ---------------------------------------------------------------------------


class UserPersonObservation(Base):
    __tablename__ = "user_person_observations"
    __table_args__ = (
        {"comment": "Per-user observation of relationship with a person"},
    )

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    person_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("persons.id", ondelete="CASCADE"), primary_key=True)
    first_observed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_observed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_genuine_interaction_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    email_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    outbound_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    inbound_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    thread_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    tie_strength_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    is_human: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_broadcast: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_automated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    relationship_types: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, default=list)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    import_snippets: Mapped[list[str] | None] = mapped_column(ARRAY(Text), nullable=True)
    source_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("sources.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    user: Mapped["User"] = relationship(back_populates="person_observations")
    person: Mapped["Person"] = relationship(back_populates="observations")
    source: Mapped["Source | None"] = relationship()


class UserRelationshipObservation(Base):
    __tablename__ = "user_relationship_observations"
    __table_args__ = (
        CheckConstraint("person_a_id < person_b_id", name="ck_user_rel_obs_order"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    person_a_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("persons.id", ondelete="CASCADE"), primary_key=True)
    person_b_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("persons.id", ondelete="CASCADE"), primary_key=True)
    co_thread_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_seen_together_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    source_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("sources.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class UserOrgObservation(Base):
    __tablename__ = "user_org_observations"

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    org_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("orgs.id", ondelete="CASCADE"), primary_key=True)
    associated_person_ids: Mapped[list[uuid.UUID]] = mapped_column(ARRAY(UUID(as_uuid=True)), nullable=False, default=list)
    total_email_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_interaction_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    tie_strength_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    relationship_types: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


# ---------------------------------------------------------------------------
# Interaction excerpts (per-user, semantic search)
# ---------------------------------------------------------------------------


class InteractionExcerpt(Base):
    __tablename__ = "interaction_excerpts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    person_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("persons.id", ondelete="CASCADE"), nullable=False)
    excerpt_text: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIMENSIONS), nullable=True)
    occurred_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    user: Mapped["User"] = relationship(back_populates="interaction_excerpts")


# ---------------------------------------------------------------------------
# Trust List (2nd-degree queries)
# ---------------------------------------------------------------------------


class TrustListInvite(Base):
    __tablename__ = "trust_list_invites"
    __table_args__ = (
        UniqueConstraint("inviter_user_id", "invitee_email", name="uq_trust_invite_pair"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    inviter_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    invitee_email: Mapped[str] = mapped_column(Text, nullable=False)
    referral_code: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    inviter: Mapped["User"] = relationship(foreign_keys=[inviter_user_id])


class TrustListMembership(Base):
    __tablename__ = "trust_list_memberships"
    __table_args__ = (
        UniqueConstraint("user_a_id", "user_b_id", name="uq_trust_membership_pair"),
        CheckConstraint("user_a_id < user_b_id", name="ck_trust_membership_order"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_a_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    user_b_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    established_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    user_a: Mapped["User"] = relationship(foreign_keys=[user_a_id])
    user_b: Mapped["User"] = relationship(foreign_keys=[user_b_id])


class ContactPrivacyLabelRow(Base):
    __tablename__ = "contact_privacy_labels"
    __table_args__ = (
        UniqueConstraint("user_id", "person_id", name="uq_contact_privacy_user_person"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    person_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("persons.id", ondelete="CASCADE"), nullable=False)
    label: Mapped[str] = mapped_column(String(32), nullable=False, default="standard")


# ---------------------------------------------------------------------------
# User-scoped organization lists
# ---------------------------------------------------------------------------


class OrgList(Base):
    __tablename__ = "org_lists"
    __table_args__ = (
        UniqueConstraint("user_id", "name", name="uq_org_list_user_name"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    memberships: Mapped[list["OrgListMembership"]] = relationship(
        back_populates="org_list",
        cascade="all, delete-orphan",
    )


class OrgListMembership(Base):
    __tablename__ = "org_list_memberships"

    org_list_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("org_lists.id", ondelete="CASCADE"),
        primary_key=True,
    )
    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("orgs.id", ondelete="CASCADE"),
        primary_key=True,
    )
    added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    org_list: Mapped["OrgList"] = relationship(back_populates="memberships")
    org: Mapped["Org"] = relationship()


class UserJobRelevance(Base):
    __tablename__ = "user_job_relevance"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("org_jobs.id", ondelete="CASCADE"),
        primary_key=True,
    )
    is_relevant: Mapped[bool] = mapped_column(Boolean, nullable=False)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    match_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    role_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    role_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    location_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    location_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    seniority_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    seniority_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    qualification_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    qualification_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    classified_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class UserJobFeedback(Base):
    __tablename__ = "user_job_feedback"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("org_jobs.id", ondelete="CASCADE"),
        primary_key=True,
    )
    interest: Mapped[str] = mapped_column(Text, nullable=False)
    reviewed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class UserTask(Base):
    __tablename__ = "user_tasks"
    __table_args__ = (UniqueConstraint("user_id", "dedup_key", name="uq_user_tasks_user_dedup_key"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    dedup_key: Mapped[str] = mapped_column(Text, nullable=False)
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="open")
    title: Mapped[str] = mapped_column(Text, nullable=False)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    sort_rank: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    job_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("org_jobs.id", ondelete="CASCADE"),
        nullable=True,
    )
    person_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("persons.id", ondelete="SET NULL"),
        nullable=True,
    )
    org_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("orgs.id", ondelete="SET NULL"),
        nullable=True,
    )
    payload: Mapped[dict[str, object] | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class OutreachAttempt(Base):
    """One recorded attempt to reach a person, per user.

    Append-a-row, not update-a-status: a relationship is a sequence of touches, and
    collapsing that to a single "last contacted" field throws away the history that makes
    follow-up possible. Attempts are mutable only in their outcome (sent -> replied).

    person_id is SET NULL rather than CASCADE on purpose. PersonDedupService._merge_person
    hard-deletes the losing Person row, so CASCADE would silently destroy user-authored
    outreach history during a routine merge. The reassignment step in that service is the
    real fix; SET NULL is the backstop for when it is missed, because an orphaned row can
    be recovered and a deleted one cannot.
    """

    __tablename__ = "outreach_attempts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    person_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("persons.id", ondelete="SET NULL"),
        nullable=True,
    )
    org_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("orgs.id", ondelete="SET NULL"),
        nullable=True,
    )
    user_task_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("user_tasks.id", ondelete="SET NULL"),
        nullable=True,
    )
    channel: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="sent")
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    next_step_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class PersonList(Base):
    """A user-curated set of people — the candidate set that survives between sessions.

    Mirrors OrgList / OrgListMembership exactly; the two should stay in step.
    """

    __tablename__ = "person_lists"
    __table_args__ = (UniqueConstraint("user_id", "name", name="uq_person_lists_user_name"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class PersonListMembership(Base):
    __tablename__ = "person_list_memberships"

    person_list_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("person_lists.id", ondelete="CASCADE"),
        primary_key=True,
    )
    person_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("persons.id", ondelete="CASCADE"),
        primary_key=True,
    )
    added_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
