"""add poster paths

Revision ID: 0009
Revises: 0008
Create Date: 2026-09-01 05:50:09.222392

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel  # SQLModel columns render as sqlmodel.sql.sqltypes.AutoString
from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Reviewed by hand.
    with op.batch_alter_table('tmdb_collection_movies', schema=None) as batch_op:
        batch_op.add_column(sa.Column('poster_path', sqlmodel.sql.sqltypes.AutoString(), nullable=True))

    with op.batch_alter_table('tmdb_collections', schema=None) as batch_op:
        batch_op.add_column(sa.Column('poster_path', sqlmodel.sql.sqltypes.AutoString(), nullable=True))

    


    # Existing rows were cached before posters were stored, so they would show nothing until the
    # TTL lapsed a week later. Dating them to the epoch makes the next scan treat them as stale
    # and refetch, which costs one pass over collections the user already has.
    op.execute("UPDATE tmdb_collections SET fetched_at = '1970-01-01 00:00:00'")


def downgrade() -> None:
    # Reviewed by hand.
    with op.batch_alter_table('tmdb_collections', schema=None) as batch_op:
        batch_op.drop_column('poster_path')

    with op.batch_alter_table('tmdb_collection_movies', schema=None) as batch_op:
        batch_op.drop_column('poster_path')

    
