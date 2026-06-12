"""Add commute preference fields to users

Revision ID: 033
Revises: 032
Create Date: 2026-06-11

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "033"
down_revision: str | None = "032"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("job_commute_max_minutes", sa.Integer(), nullable=True))
    op.add_column("users", sa.Column("job_commute_note", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "job_commute_note")
    op.drop_column("users", "job_commute_max_minutes")
