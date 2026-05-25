"""Person enrichment fields for social profiles and activity summaries

Revision ID: 010
Revises: 009
Create Date: 2026-05-24

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "010"
down_revision: str | None = "009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "persons",
        sa.Column(
            "social_profiles",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.add_column(
        "persons",
        sa.Column("bio_summary", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("persons", "bio_summary")
    op.drop_column("persons", "social_profiles")
