"""Add user-scoped organization lists

Revision ID: 027
Revises: 026
Create Date: 2026-06-09

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "027"
down_revision: str | None = "026"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "org_lists",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("user_id", "name", name="uq_org_list_user_name"),
    )
    op.create_index("ix_org_lists_user_id", "org_lists", ["user_id"])

    op.create_table(
        "org_list_memberships",
        sa.Column("org_list_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "added_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["org_list_id"], ["org_lists.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["org_id"], ["orgs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("org_list_id", "org_id"),
    )
    op.create_index(
        "ix_org_list_memberships_org_id",
        "org_list_memberships",
        ["org_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_org_list_memberships_org_id", table_name="org_list_memberships")
    op.drop_table("org_list_memberships")
    op.drop_index("ix_org_lists_user_id", table_name="org_lists")
    op.drop_table("org_lists")
