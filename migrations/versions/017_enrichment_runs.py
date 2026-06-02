"""Add enrichment_runs, import_snippets, and upload_payload

Revision ID: 017
Revises: 016
Create Date: 2026-06-02

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID

revision: str = "017"
down_revision: str | None = "016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "enrichment_runs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("state", sa.String(32), nullable=False, server_default="pending"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("contacts_total", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("contacts_enriched", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error", sa.Text(), nullable=True),
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
    )
    op.create_index("ix_enrichment_runs_user_id", "enrichment_runs", ["user_id"])

    op.add_column(
        "user_person_observations",
        sa.Column("import_snippets", ARRAY(sa.Text()), nullable=True),
    )
    op.add_column(
        "sources",
        sa.Column("upload_payload", JSONB(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("sources", "upload_payload")
    op.drop_column("user_person_observations", "import_snippets")
    op.drop_index("ix_enrichment_runs_user_id", table_name="enrichment_runs")
    op.drop_table("enrichment_runs")
