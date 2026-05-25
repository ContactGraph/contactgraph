"""Add sync_token column to sources for incremental People API sync

Revision ID: 012
Revises: 011
Create Date: 2026-05-25

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "012"
down_revision: str | None = "011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("sources", sa.Column("sync_token", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("sources", "sync_token")
