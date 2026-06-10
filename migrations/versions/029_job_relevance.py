"""Job relevance filtering: user preferences and per-job classification

Revision ID: 029
Revises: 028
Create Date: 2026-06-09

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "029"
down_revision: str | None = "028"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("job_preferences_text", sa.Text(), nullable=True))

    op.create_table(
        "user_job_relevance",
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("job_id", sa.UUID(), nullable=False),
        sa.Column("is_relevant", sa.Boolean(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column(
            "classified_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("user_id", "job_id"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["job_id"], ["org_jobs.id"], ondelete="CASCADE"),
    )
    op.create_index(
        "ix_user_job_relevance_user_relevant",
        "user_job_relevance",
        ["user_id", "is_relevant"],
    )


def downgrade() -> None:
    op.drop_index("ix_user_job_relevance_user_relevant", table_name="user_job_relevance")
    op.drop_table("user_job_relevance")
    op.drop_column("users", "job_preferences_text")
