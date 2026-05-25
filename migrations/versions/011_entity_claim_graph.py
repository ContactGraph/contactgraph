"""Entity-claim graph: global entities, claims with provenance, per-user observations.

Drops user-coupled person/org/edge tables and replaces them with a three-layer
model. Existing users must re-sync their data sources after this migration.

Revision ID: 011
Revises: 010
Create Date: 2026-05-25

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "011"
down_revision: str | None = "010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # Drop old tables (order matters for FK deps)
    # ------------------------------------------------------------------
    op.drop_table("interaction_excerpts")
    op.drop_table("org_edges")
    op.drop_table("person_org_edges")
    op.drop_table("person_person_edges")
    op.drop_table("person_edges")
    op.drop_table("persons")
    op.drop_table("orgs")

    # ------------------------------------------------------------------
    # Layer 1: Global entities
    # ------------------------------------------------------------------
    op.create_table(
        "persons",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("canonical_name", sa.Text(), nullable=False),
        sa.Column("primary_email", sa.Text(), nullable=True),
        sa.Column("current_org_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("current_org_name", sa.Text(), nullable=True),
        sa.Column("current_role", sa.Text(), nullable=True),
        sa.Column("bio_summary", sa.Text(), nullable=True),
        sa.Column("social_profiles", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("inferred_categories", postgresql.ARRAY(sa.Text()), nullable=False, server_default=sa.text("'{}'::text[]")),
        sa.Column("phone_numbers", postgresql.ARRAY(sa.Text()), nullable=False, server_default=sa.text("'{}'::text[]")),
        sa.Column("location", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )

    op.create_table(
        "orgs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("canonical_name", sa.Text(), nullable=False),
        sa.Column("primary_domain", sa.Text(), nullable=True),
        sa.Column("categories", postgresql.ARRAY(sa.Text()), nullable=False, server_default=sa.text("'{}'::text[]")),
        sa.Column("attributes", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )

    # FK from persons.current_org_id -> orgs.id
    op.create_foreign_key("fk_person_current_org", "persons", "orgs", ["current_org_id"], ["id"], ondelete="SET NULL")

    op.create_table(
        "person_aliases",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("person_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("persons.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False, server_default=sa.text("0.9")),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("kind", "value", name="uq_person_alias_kind_value"),
    )
    op.create_index("ix_person_alias_person_id", "person_aliases", ["person_id"])

    op.create_table(
        "org_aliases",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("orgs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False, server_default=sa.text("0.9")),
        sa.UniqueConstraint("kind", "value", name="uq_org_alias_kind_value"),
    )
    op.create_index("ix_org_alias_org_id", "org_aliases", ["org_id"])

    # ------------------------------------------------------------------
    # Layer 2: Claims (global, with provenance)
    # ------------------------------------------------------------------
    op.create_table(
        "employment_claims",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("person_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("persons.id", ondelete="CASCADE"), nullable=False),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("orgs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role_title", sa.Text(), nullable=True),
        sa.Column("is_current", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("started_at", sa.Date(), nullable=True),
        sa.Column("ended_at", sa.Date(), nullable=True),
        sa.Column("contributor_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("contributor_source_kind", sa.Text(), nullable=False),
        sa.Column("contributor_source_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("observed_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False, server_default=sa.text("0.7")),
        sa.Column("evidence", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.UniqueConstraint("person_id", "org_id", "contributor_source_kind", "contributor_user_id", name="uq_employment_claim"),
    )
    op.create_index("ix_employment_claim_person_current", "employment_claims", ["person_id", "is_current"])

    op.create_table(
        "relationship_claims",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("person_a_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("persons.id", ondelete="CASCADE"), nullable=False),
        sa.Column("person_b_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("persons.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False, server_default=sa.text("'co_thread'")),
        sa.Column("observed_count", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("contributor_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("contributor_source_kind", sa.Text(), nullable=False, server_default=sa.text("'gmail'")),
        sa.Column("observed_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("last_seen_together_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("evidence", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.UniqueConstraint("person_a_id", "person_b_id", "kind", "contributor_user_id", name="uq_relationship_claim"),
        sa.CheckConstraint("person_a_id < person_b_id", name="ck_relationship_claim_order"),
    )
    op.create_index("ix_relationship_claim_a_kind", "relationship_claims", ["person_a_id", "kind"])
    op.create_index("ix_relationship_claim_b_kind", "relationship_claims", ["person_b_id", "kind"])

    op.create_table(
        "person_attribute_claims",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("person_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("persons.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column("contributor_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("contributor_source_kind", sa.Text(), nullable=False),
        sa.Column("contributor_source_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("observed_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False, server_default=sa.text("0.7")),
        sa.Column("evidence", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.UniqueConstraint("person_id", "kind", "value", "contributor_source_kind", "contributor_user_id", name="uq_person_attr_claim"),
    )
    op.create_index("ix_person_attr_claim_person_kind", "person_attribute_claims", ["person_id", "kind"])

    op.create_table(
        "org_attribute_claims",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("orgs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column("contributor_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("contributor_source_kind", sa.Text(), nullable=False),
        sa.Column("contributor_source_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("observed_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False, server_default=sa.text("0.7")),
        sa.Column("evidence", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.UniqueConstraint("org_id", "kind", "value", "contributor_source_kind", "contributor_user_id", name="uq_org_attr_claim"),
    )
    op.create_index("ix_org_attr_claim_org_kind", "org_attribute_claims", ["org_id", "kind"])

    # Enrichment freshness tracker
    op.create_table(
        "enrichment_attempts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("person_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("persons.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_kind", sa.Text(), nullable=False),
        sa.Column("last_attempted_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("succeeded", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("result_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("contributor_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.UniqueConstraint("person_id", "source_kind", name="uq_enrichment_attempt"),
    )
    op.create_index("ix_enrichment_attempt_staleness", "enrichment_attempts", ["last_attempted_at"])

    # ------------------------------------------------------------------
    # Layer 3: Per-user observations
    # ------------------------------------------------------------------
    op.create_table(
        "user_person_observations",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("person_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("persons.id", ondelete="CASCADE"), nullable=False),
        sa.Column("first_observed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_observed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_genuine_interaction_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("email_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("outbound_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("inbound_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("thread_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("tie_strength_score", sa.Float(), nullable=False, server_default=sa.text("0.0")),
        sa.Column("is_human", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("is_broadcast", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("is_automated", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("relationship_types", postgresql.ARRAY(sa.Text()), nullable=False, server_default=sa.text("'{}'::text[]")),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("source_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("sources.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("user_id", "person_id", name="pk_user_person_obs"),
    )
    op.create_index("ix_upo_user_tie", "user_person_observations", ["user_id", sa.text("tie_strength_score DESC")])

    op.create_table(
        "user_relationship_observations",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("person_a_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("persons.id", ondelete="CASCADE"), nullable=False),
        sa.Column("person_b_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("persons.id", ondelete="CASCADE"), nullable=False),
        sa.Column("co_thread_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("last_seen_together_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("sources.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("user_id", "person_a_id", "person_b_id", name="pk_user_rel_obs"),
        sa.CheckConstraint("person_a_id < person_b_id", name="ck_user_rel_obs_order"),
    )

    op.create_table(
        "user_org_observations",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("orgs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("associated_person_ids", postgresql.ARRAY(postgresql.UUID(as_uuid=True)), nullable=False, server_default=sa.text("'{}'::uuid[]")),
        sa.Column("total_email_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("last_interaction_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("tie_strength_score", sa.Float(), nullable=False, server_default=sa.text("0.0")),
        sa.Column("relationship_types", postgresql.ARRAY(sa.Text()), nullable=False, server_default=sa.text("'{}'::text[]")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("user_id", "org_id", name="pk_user_org_obs"),
    )

    # ------------------------------------------------------------------
    # Recreate interaction_excerpts with FK to new persons
    # ------------------------------------------------------------------
    op.create_table(
        "interaction_excerpts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("person_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("persons.id", ondelete="CASCADE"), nullable=False),
        sa.Column("excerpt_text", sa.Text(), nullable=False),
        sa.Column("embedding", sa.Text(), nullable=True),  # pgvector column added by app code
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )


def downgrade() -> None:
    raise NotImplementedError("Irreversible migration — clean-slate rebuild.")
