"""Remove placeholder orgs without a primary domain

Revision ID: 036
Revises: 035
Create Date: 2026-06-12

"""

from collections.abc import Sequence
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from alembic import op

from contactsafe_server.services.org_search import is_placeholder_org_name

revision: str = "036"
down_revision: str | None = "035"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    conn = op.get_bind()
    rows: list[Any] = conn.execute(
        sa.text("SELECT id, canonical_name FROM orgs WHERE primary_domain IS NULL"),
    ).fetchall()

    placeholder_ids: list[UUID] = [
        row.id
        for row in rows
        if is_placeholder_org_name(str(row.canonical_name))
    ]
    if not placeholder_ids:
        return

    conn.execute(
        sa.text("DELETE FROM orgs WHERE id = ANY(:ids)"),
        {"ids": placeholder_ids},
    )


def downgrade() -> None:
    pass
