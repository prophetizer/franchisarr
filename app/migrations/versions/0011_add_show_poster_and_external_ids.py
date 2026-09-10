"""add show poster and external ids

Revision ID: 0011
Revises: 0010
Create Date: 2026-09-10 09:00:00.000000

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel  # SQLModel columns render as sqlmodel.sql.sqltypes.AutoString
from alembic import op

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("tmdb_shows", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("poster_path", sqlmodel.sql.sqltypes.AutoString(), nullable=True)
        )
        batch_op.add_column(
            sa.Column("imdb_id", sqlmodel.sql.sqltypes.AutoString(), nullable=True)
        )
        batch_op.add_column(sa.Column("tvdb_id", sa.Integer(), nullable=True))

    # Same reasoning as 0009 and 0010: rows cached before these columns existed would show no
    # poster and no links until the TTL lapsed a week later. Dating them to the epoch makes the
    # next scan refetch them once.
    op.execute("UPDATE tmdb_shows SET fetched_at = '1970-01-01 00:00:00'")


def downgrade() -> None:
    with op.batch_alter_table("tmdb_shows", schema=None) as batch_op:
        batch_op.drop_column("tvdb_id")
        batch_op.drop_column("imdb_id")
        batch_op.drop_column("poster_path")
