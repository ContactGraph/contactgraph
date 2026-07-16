"""Add org company size fields

Revision ID: 026
Revises: 025
Create Date: 2026-06-09

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "026"
down_revision: str | None = "025"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("orgs", sa.Column("employee_count", sa.Integer(), nullable=True))
    op.add_column("orgs", sa.Column("company_size_band", sa.String(length=32), nullable=True))


def downgrade() -> None:
    op.drop_column("orgs", "company_size_band")
    op.drop_column("orgs", "employee_count")
