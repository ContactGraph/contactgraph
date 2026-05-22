"""Graph tables and user import progress

Revision ID: 002
Revises: 001
Create Date: 2026-05-22

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "002"
down_revision: str | None = "001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("import_state", sa.String(length=32), nullable=False, server_default="pending"),
    )
    op.add_column(
        "users",
        sa.Column("contacts_found", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "users",
        sa.Column("contacts_resolved", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "users",
        sa.Column("contacts_pending", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column("users", sa.Column("import_started_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("users", sa.Column("import_completed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("users", sa.Column("import_error", sa.Text(), nullable=True))

    op.create_table(
        "persons",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("canonical_name", sa.Text(), nullable=False),
        sa.Column("email_addresses", postgresql.ARRAY(sa.Text()), nullable=False),
        sa.Column("phone_numbers", postgresql.ARRAY(sa.Text()), nullable=False, server_default="{}"),
        sa.Column("current_role", sa.Text(), nullable=True),
        sa.Column("current_org_name", sa.Text(), nullable=True),
        sa.Column("location", sa.Text(), nullable=True),
        sa.Column("inferred_categories", postgresql.ARRAY(sa.Text()), nullable=False, server_default="{}"),
        sa.Column("last_seen_in_email", sa.DateTime(timezone=True), nullable=True),
        sa.Column("confidence_score", sa.Float(), nullable=False, server_default="0.8"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_persons_user_id", "persons", ["user_id"])
    op.create_index("ix_persons_user_org", "persons", ["user_id", "current_org_name"])

    op.create_table(
        "person_edges",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("person_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("relationship_types", postgresql.ARRAY(sa.Text()), nullable=False, server_default="{}"),
        sa.Column("email_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("outbound_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("inbound_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("thread_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_email_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_genuine_interaction_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("first_contact_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("tie_strength_score", sa.Float(), nullable=False, server_default="0"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["person_id"], ["persons.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("user_id", "person_id", name="uq_person_edge_user_person"),
    )
    op.create_index("ix_person_edges_user_id", "person_edges", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_person_edges_user_id", table_name="person_edges")
    op.drop_table("person_edges")
    op.drop_index("ix_persons_user_org", table_name="persons")
    op.drop_index("ix_persons_user_id", table_name="persons")
    op.drop_table("persons")
    op.drop_column("users", "import_error")
    op.drop_column("users", "import_completed_at")
    op.drop_column("users", "import_started_at")
    op.drop_column("users", "contacts_pending")
    op.drop_column("users", "contacts_resolved")
    op.drop_column("users", "contacts_found")
    op.drop_column("users", "import_state")
