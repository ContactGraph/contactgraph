import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    ARRAY,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    LargeBinary,
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


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    email: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    google_profile_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    google_profile_picture: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    oauth_credentials: Mapped[list["OAuthCredential"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    sessions: Mapped[list["ConnectSession"]] = relationship(back_populates="user")
    authorization_codes: Mapped[list["AuthorizationCode"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    refresh_tokens: Mapped[list["RefreshToken"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    sources: Mapped[list["Source"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    persons: Mapped[list["Person"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    person_edges: Mapped[list["PersonEdge"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    person_person_edges: Mapped[list["PersonPersonEdge"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    person_org_edges: Mapped[list["PersonOrgEdge"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    org_edges: Mapped[list["OrgEdge"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    orgs: Mapped[list["Org"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    interaction_excerpts: Mapped[list["InteractionExcerpt"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class OAuthCredential(Base):
    __tablename__ = "oauth_credentials"
    __table_args__ = (UniqueConstraint("user_id", "provider", name="uq_oauth_user_provider"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    source_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sources.id", ondelete="SET NULL"), nullable=True
    )
    provider: Mapped[str] = mapped_column(String(32), nullable=False, default="google")
    access_token_encrypted: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    refresh_token_encrypted: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    token_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    scopes: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False)
    is_valid: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    user: Mapped["User"] = relationship(back_populates="oauth_credentials")
    source: Mapped["Source | None"] = relationship(back_populates="oauth_credential")


class Source(Base):
    __tablename__ = "sources"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "source_type",
            "external_account_id",
            name="uq_source_user_type_account",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    source_type: Mapped[str] = mapped_column(String(64), nullable=False)
    label: Mapped[str] = mapped_column(Text, nullable=False)
    external_account_id: Mapped[str] = mapped_column(Text, nullable=False)
    connection_status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="pending_oauth"
    )
    sync_state: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    contacts_found: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    contacts_resolved: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    contacts_pending: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    sync_started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    sync_completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    sync_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    user: Mapped["User"] = relationship(back_populates="sources")
    oauth_credential: Mapped["OAuthCredential | None"] = relationship(
        back_populates="source", uselist=False
    )


class ConnectSession(Base):
    __tablename__ = "sessions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    state: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    requested_scopes: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False)
    oauth_redirect_uri: Mapped[str | None] = mapped_column(Text, nullable=True)
    oauth_client_state: Mapped[str | None] = mapped_column(Text, nullable=True)
    code_challenge: Mapped[str | None] = mapped_column(Text, nullable=True)
    code_challenge_method: Mapped[str | None] = mapped_column(String(16), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped["User | None"] = relationship(back_populates="sessions")


class AuthorizationCode(Base):
    __tablename__ = "authorization_codes"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    code_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    code_challenge: Mapped[str | None] = mapped_column(Text, nullable=True)
    code_challenge_method: Mapped[str | None] = mapped_column(String(16), nullable=True)
    redirect_uri: Mapped[str] = mapped_column(Text, nullable=False)
    scopes: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    user: Mapped["User"] = relationship(back_populates="authorization_codes")


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    scopes: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    user: Mapped["User"] = relationship(back_populates="refresh_tokens")


class OAuthClient(Base):
    __tablename__ = "oauth_clients"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    client_id: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    client_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    redirect_uris: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False)
    token_endpoint_auth_method: Mapped[str] = mapped_column(
        String(32), nullable=False, default="none"
    )
    grant_types: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False)
    response_types: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class Org(Base):
    __tablename__ = "orgs"
    __table_args__ = (UniqueConstraint("user_id", "domain", name="uq_org_user_domain"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    canonical_name: Mapped[str] = mapped_column(Text, nullable=False)
    domain: Mapped[str] = mapped_column(Text, nullable=False)
    aliases: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, default=list)
    categories: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, default=list)
    attributes: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False, default=dict)
    last_enriched_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    user: Mapped["User"] = relationship(back_populates="orgs")
    persons: Mapped[list["Person"]] = relationship(back_populates="current_org")
    person_org_edges: Mapped[list["PersonOrgEdge"]] = relationship(back_populates="org")
    org_edges: Mapped[list["OrgEdge"]] = relationship(back_populates="org")


class Person(Base):
    __tablename__ = "persons"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    canonical_name: Mapped[str] = mapped_column(Text, nullable=False)
    email_addresses: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False)
    phone_numbers: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, default=list)
    current_role: Mapped[str | None] = mapped_column(Text, nullable=True)
    current_org_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("orgs.id", ondelete="SET NULL"), nullable=True
    )
    current_org_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    location: Mapped[str | None] = mapped_column(Text, nullable=True)
    inferred_categories: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, default=list
    )
    last_seen_in_email: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    confidence_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.8)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    user: Mapped["User"] = relationship(back_populates="persons")
    current_org: Mapped["Org | None"] = relationship(back_populates="persons")
    edge: Mapped["PersonEdge | None"] = relationship(
        back_populates="person", uselist=False, cascade="all, delete-orphan"
    )
    org_affiliations: Mapped[list["PersonOrgEdge"]] = relationship(
        back_populates="person", cascade="all, delete-orphan"
    )


class PersonEdge(Base):
    __tablename__ = "person_edges"
    __table_args__ = (UniqueConstraint("user_id", "person_id", name="uq_person_edge_user_person"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    person_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("persons.id", ondelete="CASCADE"), nullable=False
    )
    relationship_types: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, default=list)
    email_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    outbound_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    inbound_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    thread_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_email_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_genuine_interaction_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    first_contact_date: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    tie_strength_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    is_broadcast: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_human: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_automated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    user: Mapped["User"] = relationship(back_populates="person_edges")
    person: Mapped["Person"] = relationship(back_populates="edge")


class PersonPersonEdge(Base):
    __tablename__ = "person_person_edges"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "left_person_id",
            "right_person_id",
            name="uq_person_person_edge_user_pair",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    left_person_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("persons.id", ondelete="CASCADE"), nullable=False
    )
    right_person_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("persons.id", ondelete="CASCADE"), nullable=False
    )
    co_occurrence_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    relationship_hint: Mapped[str] = mapped_column(Text, nullable=False, default="co_thread")
    tie_strength_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    user: Mapped["User"] = relationship(back_populates="person_person_edges")


class PersonOrgEdge(Base):
    __tablename__ = "person_org_edges"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "person_id",
            "org_id",
            name="uq_person_org_edge_user_person_org",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    person_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("persons.id", ondelete="CASCADE"), nullable=False
    )
    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("orgs.id", ondelete="CASCADE"), nullable=False
    )
    relationship_type: Mapped[str] = mapped_column(Text, nullable=False, default="employee")
    role_title: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    source: Mapped[str] = mapped_column(Text, nullable=False, default="email_domain")
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.7)
    attributes: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    user: Mapped["User"] = relationship(back_populates="person_org_edges")
    person: Mapped["Person"] = relationship(back_populates="org_affiliations")
    org: Mapped["Org"] = relationship(back_populates="person_org_edges")


class OrgEdge(Base):
    __tablename__ = "org_edges"
    __table_args__ = (UniqueConstraint("user_id", "org_id", name="uq_org_edge_user_org"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("orgs.id", ondelete="CASCADE"), nullable=False
    )
    relationship_types: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, default=list)
    associated_person_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(UUID(as_uuid=True)), nullable=False, default=list
    )
    total_email_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_interaction_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    tie_strength_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    attributes: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    user: Mapped["User"] = relationship(back_populates="org_edges")
    org: Mapped["Org"] = relationship(back_populates="org_edges")


class InteractionExcerpt(Base):
    __tablename__ = "interaction_excerpts"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    person_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("persons.id", ondelete="CASCADE"), nullable=False
    )
    excerpt_text: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[list[float] | None] = mapped_column(
        Vector(EMBEDDING_DIMENSIONS), nullable=True
    )
    occurred_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    user: Mapped["User"] = relationship(back_populates="interaction_excerpts")
