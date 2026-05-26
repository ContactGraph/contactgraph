"""Add trust list tables for 2nd-degree contact queries

Revision ID: 014
Revises: 013
Create Date: 2026-05-26

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "014"
down_revision: str | None = "013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "trust_list_invites",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("inviter_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("invitee_email", sa.Text(), nullable=False),
        sa.Column("referral_code", sa.Text(), nullable=False),
        sa.Column(
            "status", sa.String(length=32), nullable=False, server_default="pending"
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["inviter_user_id"], ["users.id"], ondelete="CASCADE"
        ),
        sa.UniqueConstraint(
            "inviter_user_id", "invitee_email", name="uq_trust_invite_pair"
        ),
        sa.UniqueConstraint("referral_code", name="uq_trust_invite_referral_code"),
    )
    op.create_index(
        "ix_trust_list_invites_invitee_email",
        "trust_list_invites",
        ["invitee_email"],
    )

    op.create_table(
        "trust_list_memberships",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_a_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_b_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "status", sa.String(length=32), nullable=False, server_default="active"
        ),
        sa.Column(
            "established_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_a_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_b_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("user_a_id", "user_b_id", name="uq_trust_membership_pair"),
        sa.CheckConstraint("user_a_id < user_b_id", name="ck_trust_membership_order"),
    )
    op.create_index(
        "ix_trust_list_memberships_user_a", "trust_list_memberships", ["user_a_id"]
    )
    op.create_index(
        "ix_trust_list_memberships_user_b", "trust_list_memberships", ["user_b_id"]
    )

    op.create_table(
        "contact_privacy_labels",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("person_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "label", sa.String(length=32), nullable=False, server_default="standard"
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["person_id"], ["persons.id"], ondelete="CASCADE"),
        sa.UniqueConstraint(
            "user_id", "person_id", name="uq_contact_privacy_user_person"
        ),
    )


def downgrade() -> None:
    op.drop_table("contact_privacy_labels")
    op.drop_index("ix_trust_list_memberships_user_b", table_name="trust_list_memberships")
    op.drop_index("ix_trust_list_memberships_user_a", table_name="trust_list_memberships")
    op.drop_table("trust_list_memberships")
    op.drop_index("ix_trust_list_invites_invitee_email", table_name="trust_list_invites")
    op.drop_table("trust_list_invites")
