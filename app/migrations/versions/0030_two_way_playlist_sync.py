"""Two-way playlist sync: the merged list and what each side held after the last sync.

Existing syncs start with none, which the first two-way sync reads as "no edits since" -- the
same as the one-way sync they were, so nothing on anyone's playlist changes by upgrading.

Revision ID: 0030
Revises: 0029
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel
from alembic import op

revision: str = "0030"
down_revision: str | None = "0029"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("playlist_syncs", schema=None) as batch_op:
        batch_op.add_column(sa.Column("merged", sqlmodel.sql.sqltypes.AutoString(), nullable=True))
        batch_op.add_column(sa.Column("source_seen", sqlmodel.sql.sqltypes.AutoString(), nullable=True))
        batch_op.add_column(sa.Column("source_unmatched", sa.Integer(), nullable=False, server_default="0"))
        batch_op.add_column(sa.Column("source_unmatched_titles", sqlmodel.sql.sqltypes.AutoString(), nullable=True))
    with op.batch_alter_table("playlist_copies", schema=None) as batch_op:
        batch_op.add_column(sa.Column("seen", sqlmodel.sql.sqltypes.AutoString(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("playlist_copies", schema=None) as batch_op:
        batch_op.drop_column("seen")
    with op.batch_alter_table("playlist_syncs", schema=None) as batch_op:
        batch_op.drop_column("source_unmatched_titles")
        batch_op.drop_column("source_unmatched")
        batch_op.drop_column("source_seen")
        batch_op.drop_column("merged")
