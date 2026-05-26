"""Add descriptive_tags column to persons table

Revision ID: 016
Revises: 015
Create Date: 2026-05-26

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ARRAY

revision: str = "016"
down_revision: str | None = "015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "persons",
        sa.Column("descriptive_tags", ARRAY(sa.Text()), nullable=False, server_default="{}"),
    )
    op.create_index(
        "ix_persons_descriptive_tags_gin",
        "persons",
        ["descriptive_tags"],
        postgresql_using="gin",
    )


def downgrade() -> None:
    op.drop_index("ix_persons_descriptive_tags_gin", table_name="persons")
    op.drop_column("persons", "descriptive_tags")
