"""Add enrichment_queue for per-contact enrichment workers

Revision ID: 022
Revises: 021
Create Date: 2026-06-04

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "022"
down_revision: str | None = "021"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "enrichment_queue",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "person_id",
            UUID(as_uuid=True),
            sa.ForeignKey("persons.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column(
            "trigger_user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "enrichment_run_id",
            UUID(as_uuid=True),
            sa.ForeignKey("enrichment_runs.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(32), nullable=False, server_default="pending"),
        sa.Column(
            "strategies_attempted",
            JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "strategies_remaining",
            JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "result_confidence",
            sa.Float(),
            nullable=False,
            server_default="0",
        ),
        sa.Column("attempts_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_attempted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_attempt_after", sa.DateTime(timezone=True), nullable=True),
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
    op.create_index(
        "ix_enrichment_queue_status_priority",
        "enrichment_queue",
        ["status", "priority"],
    )
    op.create_index(
        "ix_enrichment_queue_trigger_user_id",
        "enrichment_queue",
        ["trigger_user_id"],
    )
    op.create_index(
        "ix_enrichment_queue_enrichment_run_id",
        "enrichment_queue",
        ["enrichment_run_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_enrichment_queue_enrichment_run_id", table_name="enrichment_queue")
    op.drop_index("ix_enrichment_queue_trigger_user_id", table_name="enrichment_queue")
    op.drop_index("ix_enrichment_queue_status_priority", table_name="enrichment_queue")
    op.drop_table("enrichment_queue")
