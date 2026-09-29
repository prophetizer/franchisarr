"""The Franchisarr playlist set: the playlists it keeps, and each one's copy per server.

Replaces 0027's presence table and the "keep Franchisarr's playlists on every server" switch:
keeping them everywhere is now what the set does. Existing "(Franchisarr)" playlists are adopted
into the set at the first sync after the upgrade -- that needs the servers, so it can't happen
here; this only marks that it's due.

Revision ID: 0029
Revises: 0028
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel
from alembic import op

revision: str = "0029"
down_revision: str | None = "0028"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "franchisarr_playlists",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("kind", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("ref", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("name", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("servers", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("min_items", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("refreshed_at", sa.DateTime(), nullable=True),
        sa.Column("removed_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("kind", "ref", name="uq_franchisarr_playlist"),
    )
    op.create_table(
        "franchisarr_playlist_copies",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("playlist_id", sa.Integer(), nullable=False),
        sa.Column("server_id", sa.Integer(), nullable=False),
        sa.Column("server_playlist_id", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("fingerprint", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("items", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default="ok"),
        sa.Column("message", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("refreshed_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["playlist_id"], ["franchisarr_playlists.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["server_id"], ["media_servers.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("playlist_id", "server_id", name="uq_franchisarr_playlist_copy"),
    )
    op.create_index(op.f("ix_franchisarr_playlist_copies_playlist_id"), "franchisarr_playlist_copies", ["playlist_id"])
    op.create_index(op.f("ix_franchisarr_playlist_copies_server_id"), "franchisarr_playlist_copies", ["server_id"])
    op.drop_table("franchisarr_playlist_presence")
    op.execute("DELETE FROM settings WHERE key = 'playlist_sync_franchisarr'")
    # An install with servers may already have "(Franchisarr)" playlists: the first sync takes
    # them into the set. A fresh one has none, and no sync runs until there's something to do.
    op.execute("INSERT OR REPLACE INTO settings (key, value, updated_at) "
               "SELECT 'franchisarr_playlists_to_adopt', 'true', CURRENT_TIMESTAMP "
               "WHERE EXISTS (SELECT 1 FROM media_servers)")


def downgrade() -> None:
    op.create_table(
        "franchisarr_playlist_presence",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("title", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("server_ids", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_franchisarr_playlist_presence_title"), "franchisarr_playlist_presence", ["title"], unique=True)
    op.drop_index(op.f("ix_franchisarr_playlist_copies_server_id"), table_name="franchisarr_playlist_copies")
    op.drop_index(op.f("ix_franchisarr_playlist_copies_playlist_id"), table_name="franchisarr_playlist_copies")
    op.drop_table("franchisarr_playlist_copies")
    op.drop_table("franchisarr_playlists")
