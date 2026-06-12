"""Add sub-score columns to user_job_relevance

Revision ID: 034
Revises: 033
Create Date: 2026-06-11

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "034"
down_revision: str | None = "033"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("user_job_relevance", sa.Column("role_score", sa.Integer(), nullable=True))
    op.add_column("user_job_relevance", sa.Column("role_reason", sa.Text(), nullable=True))
    op.add_column("user_job_relevance", sa.Column("location_score", sa.Integer(), nullable=True))
    op.add_column("user_job_relevance", sa.Column("location_reason", sa.Text(), nullable=True))
    op.add_column("user_job_relevance", sa.Column("seniority_score", sa.Integer(), nullable=True))
    op.add_column("user_job_relevance", sa.Column("seniority_reason", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("user_job_relevance", "seniority_reason")
    op.drop_column("user_job_relevance", "seniority_score")
    op.drop_column("user_job_relevance", "location_reason")
    op.drop_column("user_job_relevance", "location_score")
    op.drop_column("user_job_relevance", "role_reason")
    op.drop_column("user_job_relevance", "role_score")
