"""Graph edges, org attributes, and contact classification

Revision ID: 008
Revises: 007
Create Date: 2026-05-24

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "008"
down_revision: str | None = "007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "person_edges",
        sa.Column("is_automated", sa.Boolean(), nullable=False, server_default="false"),
    )

    op.add_column(
        "orgs",
        sa.Column("categories", postgresql.ARRAY(sa.Text()), nullable=False, server_default="{}"),
    )
    op.add_column(
        "orgs",
        sa.Column("attributes", postgresql.JSONB(), nullable=False, server_default="{}"),
    )
    op.add_column(
        "orgs",
        sa.Column("last_enriched_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.add_column(
        "person_person_edges",
        sa.Column("relationship_hint", sa.Text(), nullable=False, server_default="co_thread"),
    )
    op.add_column(
        "person_person_edges",
        sa.Column("tie_strength_score", sa.Float(), nullable=False, server_default="0"),
    )

    op.create_table(
        "person_org_edges",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("person_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("relationship_type", sa.Text(), nullable=False, server_default="employee"),
        sa.Column("role_title", sa.Text(), nullable=True),
        sa.Column("is_current", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source", sa.Text(), nullable=False, server_default="email_domain"),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0.7"),
        sa.Column("attributes", postgresql.JSONB(), nullable=False, server_default="{}"),
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
        sa.ForeignKeyConstraint(["org_id"], ["orgs.id"], ondelete="CASCADE"),
        sa.UniqueConstraint(
            "user_id",
            "person_id",
            "org_id",
            name="uq_person_org_edge_user_person_org",
        ),
    )
    op.create_index("ix_person_org_edges_user_id", "person_org_edges", ["user_id"])
    op.create_index(
        "ix_person_org_edges_user_current",
        "person_org_edges",
        ["user_id", "is_current"],
    )

    op.create_table(
        "org_edges",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "relationship_types",
            postgresql.ARRAY(sa.Text()),
            nullable=False,
            server_default="{}",
        ),
        sa.Column(
            "associated_person_ids",
            postgresql.ARRAY(postgresql.UUID(as_uuid=True)),
            nullable=False,
            server_default="{}",
        ),
        sa.Column("total_email_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_interaction_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("tie_strength_score", sa.Float(), nullable=False, server_default="0"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("attributes", postgresql.JSONB(), nullable=False, server_default="{}"),
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
        sa.ForeignKeyConstraint(["org_id"], ["orgs.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("user_id", "org_id", name="uq_org_edge_user_org"),
    )
    op.create_index("ix_org_edges_user_id", "org_edges", ["user_id"])

    # Backfill employment edges from denormalized person fields where org exists.
    op.execute(
        sa.text(
            """
            INSERT INTO person_org_edges (
                id, user_id, person_id, org_id, relationship_type, role_title,
                is_current, source, confidence, attributes, created_at, updated_at
            )
            SELECT
                gen_random_uuid(),
                p.user_id,
                p.id,
                p.current_org_id,
                'employee',
                p.current_role,
                true,
                'email_domain',
                0.7,
                '{}'::jsonb,
                now(),
                now()
            FROM persons p
            JOIN orgs o ON o.id = p.current_org_id
            WHERE p.current_org_id IS NOT NULL
              AND o.domain NOT LIKE '%noreply%'
              AND o.domain NOT IN (
                  'gmail.com', 'googlemail.com', 'yahoo.com', 'hotmail.com',
                  'outlook.com', 'icloud.com', 'me.com', 'live.com',
                  'protonmail.com', 'fastmail.com'
              )
            ON CONFLICT (user_id, person_id, org_id) DO NOTHING
            """
        )
    )

    op.execute(
        sa.text(
            """
            UPDATE person_person_edges
            SET tie_strength_score = LEAST(1.0, co_occurrence_count / 10.0)
            WHERE tie_strength_score = 0
            """
        )
    )


def downgrade() -> None:
    op.drop_index("ix_org_edges_user_id", table_name="org_edges")
    op.drop_table("org_edges")
    op.drop_index("ix_person_org_edges_user_current", table_name="person_org_edges")
    op.drop_index("ix_person_org_edges_user_id", table_name="person_org_edges")
    op.drop_table("person_org_edges")
    op.drop_column("person_person_edges", "tie_strength_score")
    op.drop_column("person_person_edges", "relationship_hint")
    op.drop_column("orgs", "last_enriched_at")
    op.drop_column("orgs", "attributes")
    op.drop_column("orgs", "categories")
    op.drop_column("person_edges", "is_automated")
