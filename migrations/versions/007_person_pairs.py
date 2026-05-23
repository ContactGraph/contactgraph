"""Person-to-person co-occurrence edges

Revision ID: 007
Revises: 006
Create Date: 2026-05-23

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "007"
down_revision: str | None = "006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "person_person_edges",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("left_person_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("right_person_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("co_occurrence_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.ForeignKeyConstraint(["left_person_id"], ["persons.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["right_person_id"], ["persons.id"], ondelete="CASCADE"),
        sa.UniqueConstraint(
            "user_id",
            "left_person_id",
            "right_person_id",
            name="uq_person_person_edge_user_pair",
        ),
    )
    op.create_index("ix_person_person_edges_user_id", "person_person_edges", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_person_person_edges_user_id", table_name="person_person_edges")
    op.drop_table("person_person_edges")
