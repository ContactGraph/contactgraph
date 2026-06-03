"""Add poll_secret_hash to sessions for poll-connect authentication

Revision ID: 021
Revises: 020
Create Date: 2026-06-03

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "021"
down_revision: str | None = "020"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "sessions",
        sa.Column("poll_secret_hash", sa.String(64), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("sessions", "poll_secret_hash")
