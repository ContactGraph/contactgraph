"""Add explicit target seniority range to users

Revision ID: 045
Revises: 044
Create Date: 2026-08-12

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "045"
down_revision: str | None = "044"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("job_target_seniority_min", sa.SmallInteger(), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column("job_target_seniority_max", sa.SmallInteger(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("users", "job_target_seniority_max")
    op.drop_column("users", "job_target_seniority_min")
