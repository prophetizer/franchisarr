"""keep a collection film's plot and genres

Revision ID: 0033
Revises: 0032
Create Date: 2026-09-30 13:00:00.000000

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel  # SQLModel columns render as sqlmodel.sql.sqltypes.AutoString
from alembic import op

revision: str = "0033"
down_revision: str | None = "0032"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("tmdb_collection_movies", schema=None) as batch_op:
        batch_op.add_column(sa.Column("overview", sqlmodel.sql.sqltypes.AutoString(), nullable=True))
        batch_op.add_column(sa.Column("genre_ids", sqlmodel.sql.sqltypes.AutoString(), nullable=True))

    # As 0009/0010: TMDb sent both all along, but the rows cached so far dropped them, and the
    # cache is kept a week. Dating every collection to the epoch makes the next scan refetch them
    # once, so the plots and the horror check work from that scan rather than a week later.
    op.execute("UPDATE tmdb_collections SET fetched_at = '1970-01-01 00:00:00'")


def downgrade() -> None:
    with op.batch_alter_table("tmdb_collection_movies", schema=None) as batch_op:
        batch_op.drop_column("genre_ids")
        batch_op.drop_column("overview")
