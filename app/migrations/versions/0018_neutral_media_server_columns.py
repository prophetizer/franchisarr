"""neutral media server columns

Revision ID: 0018
Revises: 0017
Create Date: 2026-09-18 21:00:00.000000

The library tables were named for Plex -- plex_library_key, rating_key -- because Plex was the
only server. With Jellyfin and Emby behind the same interface the names are just wrong, so they
become library_key, library_name and item_key. Data is untouched; the values mean what they did.
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0018"
down_revision: str | None = "0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Two batch blocks per table: a batch's column map is keyed by the *old* names, so an index
    # on a renamed column has to wait for the rename to land.
    with op.batch_alter_table("included_libraries", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_included_libraries_plex_library_key"))
        batch_op.alter_column("plex_library_key", new_column_name="library_key")
        batch_op.alter_column("plex_library_name", new_column_name="library_name")
    with op.batch_alter_table("included_libraries", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_included_libraries_library_key"), ["library_key"], unique=True)

    with op.batch_alter_table("library_items", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_library_items_plex_library_key"))
        batch_op.drop_index(batch_op.f("ix_library_items_rating_key"))
        batch_op.alter_column("plex_library_key", new_column_name="library_key")
        batch_op.alter_column("rating_key", new_column_name="item_key")
    with op.batch_alter_table("library_items", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_library_items_library_key"), ["library_key"], unique=False)
        batch_op.create_index(batch_op.f("ix_library_items_item_key"), ["item_key"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("library_items", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_library_items_item_key"))
        batch_op.drop_index(batch_op.f("ix_library_items_library_key"))
        batch_op.alter_column("item_key", new_column_name="rating_key")
        batch_op.alter_column("library_key", new_column_name="plex_library_key")
    with op.batch_alter_table("library_items", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_library_items_rating_key"), ["rating_key"], unique=False)
        batch_op.create_index(batch_op.f("ix_library_items_plex_library_key"), ["plex_library_key"], unique=False)

    with op.batch_alter_table("included_libraries", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_included_libraries_library_key"))
        batch_op.alter_column("library_name", new_column_name="plex_library_name")
        batch_op.alter_column("library_key", new_column_name="plex_library_key")
    with op.batch_alter_table("included_libraries", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_included_libraries_plex_library_key"), ["plex_library_key"], unique=True)
