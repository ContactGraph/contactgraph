"""Add auto-suggested ideal-roles text fields to users

Revision ID: 041
Revises: 040
Create Date: 2026-06-25

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "041"
down_revision: str | None = "040"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("job_preferences_suggestion", sa.Text(), nullable=True))
    op.add_column(
        "users",
        sa.Column(
            "job_preferences_suggestion_pending",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "job_preferences_suggestion_pending")
    op.drop_column("users", "job_preferences_suggestion")
