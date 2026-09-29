"""Playlist sync: "sync every playlist" and keeping Franchisarr's playlists on every server.

Revision ID: 0027
Revises: 0026
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel
from alembic import op

revision: str = "0027"
down_revision: str | None = "0026"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("playlist_syncs", schema=None) as batch_op:
        batch_op.add_column(sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()))
        batch_op.add_column(sa.Column("auto", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.create_table(
        "franchisarr_playlist_presence",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("title", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("server_ids", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_franchisarr_playlist_presence_title"), "franchisarr_playlist_presence",
                    ["title"], unique=True)


def downgrade() -> None:
    op.drop_index(op.f("ix_franchisarr_playlist_presence_title"), table_name="franchisarr_playlist_presence")
    op.drop_table("franchisarr_playlist_presence")
    with op.batch_alter_table("playlist_syncs", schema=None) as batch_op:
        batch_op.drop_column("auto")
        batch_op.drop_column("enabled")
