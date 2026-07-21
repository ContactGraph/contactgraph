"""Add qualification scores and profile-derived role suggestions

Revision ID: 041
Revises: 040
Create Date: 2026-07-21

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "041"
down_revision: str | None = "040"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("job_suggested_roles", sa.Text(), nullable=True),
    )
    op.add_column(
        "user_job_relevance",
        sa.Column("qualification_score", sa.Integer(), nullable=True),
    )
    op.add_column(
        "user_job_relevance",
        sa.Column("qualification_reason", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("user_job_relevance", "qualification_reason")
    op.drop_column("user_job_relevance", "qualification_score")
    op.drop_column("users", "job_suggested_roles")
