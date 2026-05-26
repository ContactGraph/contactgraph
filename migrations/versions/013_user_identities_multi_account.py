"""Add user_identities table and rekey oauth_credentials for multi-account

Revision ID: 013
Revises: 012
Create Date: 2026-05-25

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "013"
down_revision: str | None = "012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "user_identities",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column("is_primary", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("kind", "value", name="uq_identity_kind_value"),
    )
    op.create_index("ix_user_identities_user_id", "user_identities", ["user_id"])

    # Backfill: one email identity per existing user
    op.execute(
        sa.text(
            """
            INSERT INTO user_identities (id, user_id, kind, value, is_primary, verified_at, created_at)
            SELECT gen_random_uuid(), id, 'email', email, true, created_at, created_at
            FROM users
            """
        )
    )

    # Add external_account_id to oauth_credentials (nullable first for backfill)
    op.add_column(
        "oauth_credentials",
        sa.Column("external_account_id", sa.Text(), nullable=True),
    )

    # Backfill external_account_id from the user's email
    op.execute(
        sa.text(
            """
            UPDATE oauth_credentials oc
            SET external_account_id = u.email
            FROM users u
            WHERE u.id = oc.user_id
            """
        )
    )

    # Make it NOT NULL now that all rows are backfilled
    op.alter_column("oauth_credentials", "external_account_id", nullable=False)

    # Swap unique constraint
    op.drop_constraint("uq_oauth_user_provider", "oauth_credentials", type_="unique")
    op.create_unique_constraint(
        "uq_oauth_user_provider_account",
        "oauth_credentials",
        ["user_id", "provider", "external_account_id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_oauth_user_provider_account", "oauth_credentials", type_="unique"
    )
    op.create_unique_constraint(
        "uq_oauth_user_provider",
        "oauth_credentials",
        ["user_id", "provider"],
    )
    op.drop_column("oauth_credentials", "external_account_id")

    op.drop_index("ix_user_identities_user_id", table_name="user_identities")
    op.drop_table("user_identities")
