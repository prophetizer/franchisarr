"""drop fan films from franchise rosters

Revision ID: 0034
Revises: 0033
Create Date: 2026-09-30 21:00:00.000000

"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0034"
down_revision: str | None = "0033"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Wikidata's rosters are kept for the cache TTL (a week), so the import-time filter (fan films
    # joined MEMBER_DENY in 0.55.2) would take that long to reach a stored roster. Its kind is
    # Wikidata's class labels joined with " / ", e.g. "fan film / film".
    op.execute("DELETE FROM franchise_members WHERE kind LIKE '%fan film%'")


def downgrade() -> None:
    # Nothing to restore: the next roster refresh brings back whatever the older code keeps.
    pass
