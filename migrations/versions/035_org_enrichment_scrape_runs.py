"""Add org_enrichment_scrape_runs for global per-org enrichment tracking

Revision ID: 035
Revises: 034
Create Date: 2026-06-12

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "035"
down_revision: str | None = "034"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "org_enrichment_scrape_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("fields_updated", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["org_id"], ["orgs.id"], ondelete="CASCADE"),
    )
    op.create_index(
        "ix_org_enrichment_scrape_runs_org_id",
        "org_enrichment_scrape_runs",
        ["org_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_org_enrichment_scrape_runs_org_id",
        table_name="org_enrichment_scrape_runs",
    )
    op.drop_table("org_enrichment_scrape_runs")
