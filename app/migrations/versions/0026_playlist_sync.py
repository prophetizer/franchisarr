"""Playlist sync: which playlists are synced, and the copies made of them.

Revision ID: 0026
Revises: 0025
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel
from alembic import op

revision: str = "0026"
down_revision: str | None = "0025"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "playlist_syncs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("source_server_id", sa.Integer(), nullable=False),
        sa.Column("source_playlist_id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("title", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("last_synced_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["source_server_id"], ["media_servers.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source_server_id", "source_playlist_id", name="uq_playlist_sync_source"),
    )
    op.create_index(op.f("ix_playlist_syncs_source_server_id"), "playlist_syncs", ["source_server_id"])
    op.create_table(
        "playlist_copies",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("sync_id", sa.Integer(), nullable=False),
        sa.Column("target_server_id", sa.Integer(), nullable=False),
        sa.Column("target_playlist_id", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("fingerprint", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("status", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("message", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("matched", sa.Integer(), nullable=False),
        sa.Column("unmatched", sa.Integer(), nullable=False),
        sa.Column("unmatched_titles", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("synced_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["sync_id"], ["playlist_syncs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["target_server_id"], ["media_servers.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("sync_id", "target_server_id", name="uq_playlist_copy_target"),
    )
    op.create_index(op.f("ix_playlist_copies_sync_id"), "playlist_copies", ["sync_id"])
    op.create_index(op.f("ix_playlist_copies_target_server_id"), "playlist_copies", ["target_server_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_playlist_copies_target_server_id"), table_name="playlist_copies")
    op.drop_index(op.f("ix_playlist_copies_sync_id"), table_name="playlist_copies")
    op.drop_table("playlist_copies")
    op.drop_index(op.f("ix_playlist_syncs_source_server_id"), table_name="playlist_syncs")
    op.drop_table("playlist_syncs")
