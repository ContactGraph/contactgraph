"""Outreach attempts and user-curated person lists

Revision ID: 045
Revises: 044
Create Date: 2026-07-30

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "045"
down_revision: str | None = "044"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # person_id is SET NULL, not CASCADE. PersonDedupService._merge_person hard-deletes the
    # losing Person row, so CASCADE would silently destroy user-authored outreach history
    # during a routine merge. The reassignment step in that service is the real fix; this is
    # the backstop, because an orphaned row can be recovered and a deleted one cannot.
    op.create_table(
        "outreach_attempts",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("person_id", sa.UUID(), nullable=True),
        sa.Column("org_id", sa.UUID(), nullable=True),
        sa.Column("user_task_id", sa.UUID(), nullable=True),
        sa.Column("channel", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="sent"),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("next_step_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["person_id"], ["persons.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["org_id"], ["orgs.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_task_id"], ["user_tasks.id"], ondelete="SET NULL"),
    )
    # The queue queries all filter by user then order by recency; the person index serves
    # "show me this person's history" on the detail panel.
    op.create_index(
        "ix_outreach_attempts_user_occurred",
        "outreach_attempts",
        ["user_id", "occurred_at"],
    )
    op.create_index(
        "ix_outreach_attempts_user_person",
        "outreach_attempts",
        ["user_id", "person_id"],
    )
    op.create_index(
        "ix_outreach_attempts_user_next_step",
        "outreach_attempts",
        ["user_id", "next_step_at"],
    )

    # Mirrors org_lists / org_list_memberships. Kept deliberately identical in shape so the
    # two stay comparable; a candidate set is the same idea applied to people.
    op.create_table(
        "person_lists",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("user_id", "name", name="uq_person_lists_user_name"),
    )

    op.create_table(
        "person_list_memberships",
        sa.Column("person_list_id", sa.UUID(), nullable=False),
        sa.Column("person_id", sa.UUID(), nullable=False),
        sa.Column(
            "added_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("person_list_id", "person_id"),
        sa.ForeignKeyConstraint(["person_list_id"], ["person_lists.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["person_id"], ["persons.id"], ondelete="CASCADE"),
    )


def downgrade() -> None:
    op.drop_table("person_list_memberships")
    op.drop_table("person_lists")
    op.drop_index("ix_outreach_attempts_user_next_step", table_name="outreach_attempts")
    op.drop_index("ix_outreach_attempts_user_person", table_name="outreach_attempts")
    op.drop_index("ix_outreach_attempts_user_occurred", table_name="outreach_attempts")
    op.drop_table("outreach_attempts")
