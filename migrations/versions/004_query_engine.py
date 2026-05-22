"""Query engine: orgs, edge flags, indexes, interaction_excerpts + pgvector

Revision ID: 004
Revises: 003
Create Date: 2026-05-22

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "004"
down_revision: str | None = "003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    op.create_table(
        "orgs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("canonical_name", sa.Text(), nullable=False),
        sa.Column("domain", sa.Text(), nullable=False),
        sa.Column("aliases", postgresql.ARRAY(sa.Text()), nullable=False, server_default="{}"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("user_id", "domain", name="uq_org_user_domain"),
    )
    op.create_index("ix_orgs_user_id", "orgs", ["user_id"])

    op.add_column(
        "persons",
        sa.Column("current_org_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_persons_current_org_id",
        "persons",
        "orgs",
        ["current_org_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.add_column(
        "person_edges",
        sa.Column("is_broadcast", sa.Boolean(), nullable=False, server_default="false"),
    )
    op.add_column(
        "person_edges",
        sa.Column("is_human", sa.Boolean(), nullable=False, server_default="false"),
    )

    op.execute(
        "CREATE INDEX ix_persons_inferred_categories_gin "
        "ON persons USING gin (inferred_categories)"
    )
    op.execute(
        "CREATE INDEX ix_persons_canonical_name_trgm "
        "ON persons USING gin (canonical_name gin_trgm_ops)"
    )
    # Org/role trgm: skip — Supabase rejects gin_trgm_ops on nullable text (IMMUTABLE errors).
    # Query executor uses ILIKE; GIN on categories + canonical_name covers MVP scale.
    op.execute(
        "CREATE INDEX ix_orgs_canonical_name_trgm "
        "ON orgs USING gin (canonical_name gin_trgm_ops)"
    )

    op.execute(
        """
        CREATE TABLE interaction_excerpts (
            id UUID PRIMARY KEY,
            user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            person_id UUID NOT NULL REFERENCES persons(id) ON DELETE CASCADE,
            excerpt_text TEXT NOT NULL,
            embedding vector(1536),
            occurred_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        """
        CREATE INDEX ix_interaction_excerpts_embedding_hnsw
        ON interaction_excerpts USING hnsw (embedding vector_cosine_ops)
        WHERE embedding IS NOT NULL
        """
    )
    op.create_index("ix_interaction_excerpts_user_person", "interaction_excerpts", ["user_id", "person_id"])


def downgrade() -> None:
    op.drop_index("ix_interaction_excerpts_user_person", table_name="interaction_excerpts")
    op.execute("DROP INDEX IF EXISTS ix_interaction_excerpts_embedding_hnsw")
    op.drop_table("interaction_excerpts")
    op.execute("DROP INDEX IF EXISTS ix_orgs_canonical_name_trgm")
    op.execute("DROP INDEX IF EXISTS ix_persons_canonical_name_trgm")
    op.execute("DROP INDEX IF EXISTS ix_persons_inferred_categories_gin")
    op.drop_column("person_edges", "is_human")
    op.drop_column("person_edges", "is_broadcast")
    op.drop_constraint("fk_persons_current_org_id", "persons", type_="foreignkey")
    op.drop_column("persons", "current_org_id")
    op.drop_index("ix_orgs_user_id", table_name="orgs")
    op.drop_table("orgs")
