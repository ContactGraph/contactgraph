"""Add job location preference fields to users

Revision ID: 030
Revises: 029
Create Date: 2026-06-10

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "030"
down_revision: str | None = "029"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("job_location_pref", sa.Text(), nullable=True))
    op.add_column("users", sa.Column("job_location_city", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "job_location_city")
    op.drop_column("users", "job_location_pref")
