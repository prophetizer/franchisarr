"""Playlist sync: per-playlist target servers, and a history of runs.

Revision ID: 0028
Revises: 0027
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel
from alembic import op

revision: str = "0028"
down_revision: str | None = "0027"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("playlist_syncs", schema=None) as batch_op:
        batch_op.add_column(sa.Column("targets", sqlmodel.sql.sqltypes.AutoString(), nullable=True))
    op.create_table(
        "playlist_sync_runs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("trigger", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("finished_at", sa.DateTime(), nullable=False),
        sa.Column("created", sa.Integer(), nullable=False),
        sa.Column("updated", sa.Integer(), nullable=False),
        sa.Column("unchanged", sa.Integer(), nullable=False),
        sa.Column("deleted", sa.Integer(), nullable=False),
        sa.Column("blocked", sa.Integer(), nullable=False),
        sa.Column("failed", sa.Integer(), nullable=False),
        sa.Column("errors", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("playlist_sync_runs")
    with op.batch_alter_table("playlist_syncs", schema=None) as batch_op:
        batch_op.drop_column("targets")
