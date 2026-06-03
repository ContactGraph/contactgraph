"""Add progress_message to enrichment_runs

Revision ID: 020
Revises: 019
Create Date: 2026-06-03

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "020"
down_revision: str | None = "019"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "enrichment_runs",
        sa.Column("progress_message", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("enrichment_runs", "progress_message")
