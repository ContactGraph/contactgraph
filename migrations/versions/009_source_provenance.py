"""Source provenance on graph edges

Revision ID: 009
Revises: 008
Create Date: 2026-05-24

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "009"
down_revision: str | None = "008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "person_edges",
        sa.Column("source_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_person_edges_source_id",
        "person_edges",
        "sources",
        ["source_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.add_column(
        "person_person_edges",
        sa.Column("source_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_person_person_edges_source_id",
        "person_person_edges",
        "sources",
        ["source_id"],
        ["id"],
        ondelete="CASCADE",
    )

    op.execute(
        """
        UPDATE person_edges pe
        SET source_id = s.id
        FROM sources s
        WHERE s.user_id = pe.user_id
          AND s.source_type = 'google_mail'
          AND pe.source_id IS NULL
        """
    )
    op.execute(
        """
        UPDATE person_person_edges ppe
        SET source_id = s.id
        FROM sources s
        WHERE s.user_id = ppe.user_id
          AND s.source_type = 'google_mail'
          AND ppe.source_id IS NULL
        """
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_person_person_edges_source_id", "person_person_edges", type_="foreignkey"
    )
    op.drop_column("person_person_edges", "source_id")
    op.drop_constraint("fk_person_edges_source_id", "person_edges", type_="foreignkey")
    op.drop_column("person_edges", "source_id")
