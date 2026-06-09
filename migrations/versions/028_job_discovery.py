"""Job discovery tables and org ATS fields

Revision ID: 028
Revises: 027
Create Date: 2026-06-09

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "028"
down_revision: str | None = "027"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("orgs", sa.Column("ats_provider", sa.Text(), nullable=True))
    op.add_column("orgs", sa.Column("ats_board_token", sa.Text(), nullable=True))

    op.add_column(
        "users",
        sa.Column("job_monitor_list_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column(
            "job_monitor_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.create_foreign_key(
        "fk_users_job_monitor_list_id",
        "users",
        "org_lists",
        ["job_monitor_list_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.create_table(
        "org_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("external_job_id", sa.Text(), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("location", sa.Text(), nullable=True),
        sa.Column("department", sa.Text(), nullable=True),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("description_snippet", sa.Text(), nullable=True),
        sa.Column("salary_min", sa.Integer(), nullable=True),
        sa.Column("salary_max", sa.Integer(), nullable=True),
        sa.Column("remote_status", sa.Text(), nullable=True),
        sa.Column("posted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "first_seen_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "last_seen_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
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
        sa.ForeignKeyConstraint(["org_id"], ["orgs.id"], ondelete="CASCADE"),
        sa.UniqueConstraint(
            "org_id",
            "external_job_id",
            "source",
            name="uq_org_job_external",
        ),
    )
    op.create_index("ix_org_jobs_org_id", "org_jobs", ["org_id"])
    op.create_index("ix_org_jobs_org_id_is_active", "org_jobs", ["org_id", "is_active"])

    op.create_table(
        "job_scrape_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("jobs_found", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("new_jobs", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["org_id"], ["orgs.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_job_scrape_runs_org_id", "job_scrape_runs", ["org_id"])

    op.create_table(
        "job_discovery_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("state", sa.String(32), nullable=False, server_default="pending"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("orgs_total", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("orgs_processed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("jobs_found", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("new_jobs", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("progress_message", sa.Text(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
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
    )
    op.create_index("ix_job_discovery_runs_user_id", "job_discovery_runs", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_job_discovery_runs_user_id", table_name="job_discovery_runs")
    op.drop_table("job_discovery_runs")
    op.drop_index("ix_job_scrape_runs_org_id", table_name="job_scrape_runs")
    op.drop_table("job_scrape_runs")
    op.drop_index("ix_org_jobs_org_id_is_active", table_name="org_jobs")
    op.drop_index("ix_org_jobs_org_id", table_name="org_jobs")
    op.drop_table("org_jobs")
    op.drop_constraint("fk_users_job_monitor_list_id", "users", type_="foreignkey")
    op.drop_column("users", "job_monitor_enabled")
    op.drop_column("users", "job_monitor_list_id")
    op.drop_column("orgs", "ats_board_token")
    op.drop_column("orgs", "ats_provider")
