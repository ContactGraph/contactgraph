"""User job feedback (interested / dismissed)

Revision ID: 039
Revises: 038
Create Date: 2026-06-15

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "039"
down_revision: str | None = "038"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "user_job_feedback",
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("job_id", sa.UUID(), nullable=False),
        sa.Column("interest", sa.Text(), nullable=False),
        sa.Column(
            "reviewed_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("user_id", "job_id"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["job_id"], ["org_jobs.id"], ondelete="CASCADE"),
    )
    op.create_index(
        "ix_user_job_feedback_user_interest",
        "user_job_feedback",
        ["user_id", "interest"],
    )


def downgrade() -> None:
    op.drop_index("ix_user_job_feedback_user_interest", table_name="user_job_feedback")
    op.drop_table("user_job_feedback")
