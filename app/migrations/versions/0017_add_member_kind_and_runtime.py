"""add franchise member kind and director film runtime

Revision ID: 0017
Revises: 0016
Create Date: 2026-09-18 09:00:00.000000

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel  # SQLModel columns render as sqlmodel.sql.sqltypes.AutoString
from alembic import op

revision: str = "0017"
down_revision: str | None = "0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("franchise_members", schema=None) as batch_op:
        batch_op.add_column(sa.Column("kind", sqlmodel.sql.sqltypes.AutoString(), nullable=True))
    with op.batch_alter_table("director_films", schema=None) as batch_op:
        batch_op.add_column(sa.Column("runtime", sa.Integer(), nullable=True))

    # Existing franchise rosters predate `kind`, so the preference could not tell a TV film from
    # a feature. Dating the franchises to the epoch makes the next scan rebuild them once.
    op.execute("UPDATE franchises SET fetched_at = '1970-01-01 00:00:00'")


def downgrade() -> None:
    with op.batch_alter_table("director_films", schema=None) as batch_op:
        batch_op.drop_column("runtime")
    with op.batch_alter_table("franchise_members", schema=None) as batch_op:
        batch_op.drop_column("kind")
