"""Add user display_name and location for enrichment context."""

from alembic import op
import sqlalchemy as sa


revision = "018_user_enrichment_profile"
down_revision = "017_enrichment_runs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("display_name", sa.Text(), nullable=True))
    op.add_column("users", sa.Column("location", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "location")
    op.drop_column("users", "display_name")
