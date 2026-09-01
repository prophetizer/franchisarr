"""add collection backdrop and logo

Revision ID: 0010
Revises: 0009
Create Date: 2026-09-01 07:20:00.000000

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel  # SQLModel columns render as sqlmodel.sql.sqltypes.AutoString
from alembic import op

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("tmdb_collections", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("backdrop_path", sqlmodel.sql.sqltypes.AutoString(), nullable=True)
        )
        batch_op.add_column(
            sa.Column("logo_url", sqlmodel.sql.sqltypes.AutoString(), nullable=True)
        )

    # Same reasoning as 0009: rows cached before these columns existed would show a bare heading
    # until the TTL lapsed a week later. Dating them to the epoch makes the next scan refetch
    # them once. 0009 already did this for anyone upgrading across both in one go -- repeating it
    # is what makes the migration correct for someone who ran 0009 and scanned in between.
    op.execute("UPDATE tmdb_collections SET fetched_at = '1970-01-01 00:00:00'")


def downgrade() -> None:
    with op.batch_alter_table("tmdb_collections", schema=None) as batch_op:
        batch_op.drop_column("logo_url")
        batch_op.drop_column("backdrop_path")
