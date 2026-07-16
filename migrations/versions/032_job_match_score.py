"""Add match_score column to user_job_relevance

Revision ID: 032
Revises: 031
Create Date: 2026-06-11

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "032"
down_revision: str | None = "031"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("user_job_relevance", sa.Column("match_score", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("user_job_relevance", "match_score")
