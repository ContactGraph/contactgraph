"""Add indexes for top sequential-scan tables

Revision ID: 031
Revises: 030
Create Date: 2026-06-11

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "031"
down_revision: str | None = "030"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "ix_upo_user_active_tie",
        "user_person_observations",
        ["user_id", sa.text("tie_strength_score DESC")],
        postgresql_where=sa.text(
            "is_broadcast = false AND is_automated = false"
        ),
    )
    op.create_index(
        "ix_upo_relationship_types_gin",
        "user_person_observations",
        ["relationship_types"],
        postgresql_using="gin",
    )
    op.create_index(
        "ix_upo_user_human",
        "user_person_observations",
        ["user_id"],
        postgresql_where=sa.text(
            "is_human = true AND is_broadcast = false AND is_automated = false"
        ),
    )

    op.create_index(
        "ix_persons_current_org_id",
        "persons",
        ["current_org_id"],
        postgresql_where=sa.text("current_org_id IS NOT NULL"),
    )
    op.create_index(
        "ix_persons_canonical_name_trgm",
        "persons",
        ["canonical_name"],
        postgresql_using="gin",
        postgresql_ops={"canonical_name": "gin_trgm_ops"},
    )

    op.create_index(
        "ix_person_alias_person_kind",
        "person_aliases",
        ["person_id", "kind"],
    )

    op.create_index(
        "ix_employment_claim_person_source",
        "employment_claims",
        ["person_id", "contributor_source_kind"],
    )


def downgrade() -> None:
    op.drop_index("ix_employment_claim_person_source", "employment_claims")
    op.drop_index("ix_person_alias_person_kind", "person_aliases")
    op.drop_index("ix_persons_canonical_name_trgm", "persons")
    op.drop_index("ix_persons_current_org_id", "persons")
    op.drop_index("ix_upo_user_human", "user_person_observations")
    op.drop_index("ix_upo_relationship_types_gin", "user_person_observations")
    op.drop_index("ix_upo_user_active_tie", "user_person_observations")
