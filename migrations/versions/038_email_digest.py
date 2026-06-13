"""Add email digest notification preferences to users

Revision ID: 038
Revises: 037
Create Date: 2026-06-12

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "038"
down_revision: str | None = "037"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("job_digest_frequency", sa.Text(), nullable=False, server_default="daily"),
    )
    op.add_column(
        "users",
        sa.Column("job_digest_last_sent_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("users", "job_digest_last_sent_at")
    op.drop_column("users", "job_digest_frequency")
