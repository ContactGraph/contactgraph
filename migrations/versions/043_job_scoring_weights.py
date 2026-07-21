"""Add per-user job scoring knock-out weights

Revision ID: 043
Revises: 042
Create Date: 2026-07-21

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "043"
down_revision: str | None = "042"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("job_scoring_weights", JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "job_scoring_weights")
