"""Mark music-video compilations in directors' filmographies.

Revision ID: 0025
Revises: 0024
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0025"
down_revision: str | None = "0024"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("director_films", schema=None) as batch_op:
        batch_op.add_column(sa.Column("is_music_video", sa.Boolean(), nullable=False,
                                      server_default=sa.false()))
    # The flag comes from TMDb's credits, which cached rows were fetched without. Dating them to
    # the epoch (as 0009/0010 did for collections) makes the next scan refetch every filmography
    # once, rather than music videos leading the lists until the TTL lapses. A full date string,
    # not a bare year: SQLite compares a DATETIME column to '1971' as the integer 1971.
    op.execute("UPDATE director_films SET fetched_at = '1970-01-01 00:00:00'")


def downgrade() -> None:
    with op.batch_alter_table("director_films", schema=None) as batch_op:
        batch_op.drop_column("is_music_video")
