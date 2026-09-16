"""add upcoming watch

Revision ID: 0013
Revises: 0012
Create Date: 2026-09-15 23:30:00.000000

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel  # SQLModel columns render as sqlmodel.sql.sqltypes.AutoString
from alembic import op

revision: str = "0013"
down_revision: str | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "upcoming_watch",
        sa.Column("tmdb_id", sa.Integer(), nullable=False),
        sa.Column("title", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("collection_id", sa.Integer(), nullable=False),
        sa.Column("collection_name", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("release_date", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("first_seen_at", sa.DateTime(), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("tmdb_id"),
    )
    with op.batch_alter_table("upcoming_watch", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_upcoming_watch_collection_id"), ["collection_id"], unique=False
        )


def downgrade() -> None:
    with op.batch_alter_table("upcoming_watch", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_upcoming_watch_collection_id"))
    op.drop_table("upcoming_watch")
