"""Add mechanical seniority + geocode columns to org_jobs

Revision ID: 044
Revises: 043
Create Date: 2026-07-22

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "044"
down_revision: str | None = "043"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "org_jobs",
        sa.Column("seniority_level", sa.SmallInteger(), nullable=True),
    )
    op.add_column(
        "org_jobs",
        sa.Column("location_lat", sa.Float(), nullable=True),
    )
    op.add_column(
        "org_jobs",
        sa.Column("location_lng", sa.Float(), nullable=True),
    )
    op.add_column(
        "org_jobs",
        sa.Column("location_normalized", sa.String(length=128), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("org_jobs", "location_normalized")
    op.drop_column("org_jobs", "location_lng")
    op.drop_column("org_jobs", "location_lat")
    op.drop_column("org_jobs", "seniority_level")
