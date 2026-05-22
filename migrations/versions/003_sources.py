"""Sources table and migrate sync state off users

Revision ID: 003
Revises: 002
Create Date: 2026-05-22

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "003"
down_revision: str | None = "002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "sources",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_type", sa.String(length=64), nullable=False),
        sa.Column("label", sa.Text(), nullable=False),
        sa.Column("external_account_id", sa.Text(), nullable=False),
        sa.Column(
            "connection_status",
            sa.String(length=32),
            nullable=False,
            server_default="pending_oauth",
        ),
        sa.Column(
            "sync_state",
            sa.String(length=32),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("contacts_found", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("contacts_resolved", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("contacts_pending", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("sync_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sync_completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sync_error", sa.Text(), nullable=True),
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
        sa.UniqueConstraint(
            "user_id",
            "source_type",
            "external_account_id",
            name="uq_source_user_type_account",
        ),
    )
    op.create_index("ix_sources_user_id", "sources", ["user_id"])

    op.add_column(
        "oauth_credentials",
        sa.Column("source_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_oauth_credentials_source_id",
        "oauth_credentials",
        "sources",
        ["source_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # Backfill google_mail sources from users with OAuth credentials
    op.execute(
        sa.text(
            """
            INSERT INTO sources (
                id,
                user_id,
                source_type,
                label,
                external_account_id,
                connection_status,
                sync_state,
                contacts_found,
                contacts_resolved,
                contacts_pending,
                sync_started_at,
                sync_completed_at,
                sync_error,
                created_at,
                updated_at
            )
            SELECT
                gen_random_uuid(),
                u.id,
                'google_mail',
                u.email,
                u.email,
                'connected',
                CASE u.import_state
                    WHEN 'importing' THEN 'syncing'
                    ELSE u.import_state
                END,
                u.contacts_found,
                u.contacts_resolved,
                u.contacts_pending,
                u.import_started_at,
                u.import_completed_at,
                u.import_error,
                u.created_at,
                u.updated_at
            FROM users u
            INNER JOIN oauth_credentials oc ON oc.user_id = u.id AND oc.is_valid = true
            """
        )
    )

    op.execute(
        sa.text(
            """
            UPDATE oauth_credentials oc
            SET source_id = s.id
            FROM sources s
            WHERE s.user_id = oc.user_id
              AND s.source_type = 'google_mail'
              AND s.external_account_id = (
                  SELECT email FROM users WHERE id = oc.user_id
              )
            """
        )
    )

    op.drop_column("users", "import_error")
    op.drop_column("users", "import_completed_at")
    op.drop_column("users", "import_started_at")
    op.drop_column("users", "contacts_pending")
    op.drop_column("users", "contacts_resolved")
    op.drop_column("users", "contacts_found")
    op.drop_column("users", "import_state")


def downgrade() -> None:
    op.add_column(
        "users",
        sa.Column("import_state", sa.String(length=32), nullable=False, server_default="pending"),
    )
    op.add_column(
        "users",
        sa.Column("contacts_found", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "users",
        sa.Column("contacts_resolved", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "users",
        sa.Column("contacts_pending", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column("users", sa.Column("import_started_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("users", sa.Column("import_completed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("users", sa.Column("import_error", sa.Text(), nullable=True))

    op.execute(
        sa.text(
            """
            UPDATE users u
            SET
                import_state = CASE s.sync_state
                    WHEN 'syncing' THEN 'importing'
                    ELSE s.sync_state
                END,
                contacts_found = s.contacts_found,
                contacts_resolved = s.contacts_resolved,
                contacts_pending = s.contacts_pending,
                import_started_at = s.sync_started_at,
                import_completed_at = s.sync_completed_at,
                import_error = s.sync_error
            FROM sources s
            WHERE s.user_id = u.id AND s.source_type = 'google_mail'
            """
        )
    )

    op.drop_constraint("fk_oauth_credentials_source_id", "oauth_credentials", type_="foreignkey")
    op.drop_column("oauth_credentials", "source_id")
    op.drop_index("ix_sources_user_id", table_name="sources")
    op.drop_table("sources")
