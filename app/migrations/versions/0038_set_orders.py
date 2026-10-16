"""story orders a household sets for a collection or franchise; a chronological playlist beside
the release-order one

Revision ID: 0038
Revises: 0037
Create Date: 2026-10-17 12:00:00.000000

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel  # SQLModel columns render as sqlmodel.sql.sqltypes.AutoString
from alembic import op

revision: str = "0038"
down_revision: str | None = "0037"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "set_orders",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("kind", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("ref", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("item_type", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("tmdb_id", sa.Integer(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("kind", "ref", "item_type", "tmdb_id", name="uq_set_order"),
    )
    op.create_index("ix_set_orders_kind", "set_orders", ["kind"])
    op.create_index("ix_set_orders_ref", "set_orders", ["ref"])
    # A set can keep two playlists now, one per order: the unique key takes the variant too.
    # Existing rows are release order, which is what they always were.
    with op.batch_alter_table("franchisarr_playlists", schema=None) as batch_op:
        batch_op.add_column(sa.Column("variant", sqlmodel.sql.sqltypes.AutoString(), nullable=False,
                                      server_default="release"))
        batch_op.drop_constraint("uq_franchisarr_playlist", type_="unique")
        batch_op.create_unique_constraint("uq_franchisarr_playlist", ["kind", "ref", "variant"])


def downgrade() -> None:
    # Back to one playlist per set: a chronological one is forgotten here (it stays on the
    # servers as an ordinary playlist), then the old key returns.
    op.execute("DELETE FROM franchisarr_playlist_copies WHERE playlist_id IN "
               "(SELECT id FROM franchisarr_playlists WHERE variant != 'release')")
    op.execute("DELETE FROM franchisarr_playlists WHERE variant != 'release'")
    with op.batch_alter_table("franchisarr_playlists", schema=None) as batch_op:
        batch_op.drop_constraint("uq_franchisarr_playlist", type_="unique")
        batch_op.create_unique_constraint("uq_franchisarr_playlist", ["kind", "ref"])
        batch_op.drop_column("variant")
    op.drop_index("ix_set_orders_ref", table_name="set_orders")
    op.drop_index("ix_set_orders_kind", table_name="set_orders")
    op.drop_table("set_orders")
