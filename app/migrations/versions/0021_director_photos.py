"""director photos

Revision ID: 0021
Revises: 0020
Create Date: 2026-09-19 01:30:00.000000

A profile image path per director credit. Nullable: existing rows are backfilled by the next
scan, one /person request per qualifying director.
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0021"
down_revision: str | None = "0020"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("movie_directors", schema=None) as batch_op:
        batch_op.add_column(sa.Column("profile_path", sa.String(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("movie_directors", schema=None) as batch_op:
        batch_op.drop_column("profile_path")
