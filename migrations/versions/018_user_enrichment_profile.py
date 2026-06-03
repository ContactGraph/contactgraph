"""Add user display_name and location for enrichment context."""

from alembic import op
import sqlalchemy as sa


revision = "018"
down_revision = "017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("display_name", sa.Text(), nullable=True))
    op.add_column("users", sa.Column("location", sa.Text(), nullable=True))
    op.execute(
        "UPDATE users SET display_name = google_profile_name "
        "WHERE display_name IS NULL AND google_profile_name IS NOT NULL"
    )


def downgrade() -> None:
    op.drop_column("users", "location")
    op.drop_column("users", "display_name")
