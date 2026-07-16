"""Allow multiple employment claims per org when role or dates differ

Revision ID: 025
Revises: 024
Create Date: 2026-06-08

"""

from collections.abc import Sequence

from alembic import op

revision: str = "025"
down_revision: str | None = "024"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("uq_employment_claim", "employment_claims", type_="unique")
    op.create_unique_constraint(
        "uq_employment_claim",
        "employment_claims",
        [
            "person_id",
            "org_id",
            "role_title",
            "started_at",
            "contributor_source_kind",
            "contributor_user_id",
        ],
    )


def downgrade() -> None:
    op.drop_constraint("uq_employment_claim", "employment_claims", type_="unique")
    op.create_unique_constraint(
        "uq_employment_claim",
        "employment_claims",
        [
            "person_id",
            "org_id",
            "contributor_source_kind",
            "contributor_user_id",
        ],
    )
