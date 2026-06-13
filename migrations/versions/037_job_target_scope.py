"""Add job target scope preferences to users

Revision ID: 037
Revises: 036
Create Date: 2026-06-12

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "037"
down_revision: str | None = "036"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("job_target_scope", JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "job_target_scope")
