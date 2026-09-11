"""add collection member ratings

Revision ID: 0012
Revises: 0011
Create Date: 2026-09-10 12:00:00.000000

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("tmdb_collection_movies", schema=None) as batch_op:
        batch_op.add_column(sa.Column("vote_average", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("vote_count", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("popularity", sa.Float(), nullable=True))

    # As 0009-0011: existing rows predate these columns, so the next scan refetches them once
    # rather than a week from now.
    op.execute("UPDATE tmdb_collections SET fetched_at = '1970-01-01 00:00:00'")


def downgrade() -> None:
    with op.batch_alter_table("tmdb_collection_movies", schema=None) as batch_op:
        batch_op.drop_column("popularity")
        batch_op.drop_column("vote_count")
        batch_op.drop_column("vote_average")
