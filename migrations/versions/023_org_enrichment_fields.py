"""Add org enrichment fields

Revision ID: 023
Revises: 022
Create Date: 2026-06-08

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "023"
down_revision: str | None = "022"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("orgs", sa.Column("description", sa.Text(), nullable=True))
    op.add_column("orgs", sa.Column("careers_url", sa.Text(), nullable=True))
    op.add_column("orgs", sa.Column("linkedin_url", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("orgs", "linkedin_url")
    op.drop_column("orgs", "careers_url")
    op.drop_column("orgs", "description")
