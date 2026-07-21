"""Add org funding stage and user preferred funding stages

Revision ID: 042
Revises: 041
Create Date: 2026-07-21

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "042"
down_revision: str | None = "041"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("orgs", sa.Column("funding_stage", sa.String(length=32), nullable=True))
    op.add_column("users", sa.Column("preferred_funding_stages", JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "preferred_funding_stages")
    op.drop_column("orgs", "funding_stage")
