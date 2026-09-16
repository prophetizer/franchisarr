"""add cross media mappings

Revision ID: 0014
Revises: 0013
Create Date: 2026-09-16 10:00:00.000000

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel  # SQLModel columns render as sqlmodel.sql.sqltypes.AutoString
from alembic import op

revision: str = "0014"
down_revision: str | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "cross_media_mappings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("source_type", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("source_tmdb_id", sa.Integer(), nullable=False),
        sa.Column("target_type", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("target_tmdb_id", sa.Integer(), nullable=False),
        sa.Column("target_title", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("target_year", sa.Integer(), nullable=True),
        sa.Column("target_poster_path", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("relation", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("source", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("confidence", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "source_type", "source_tmdb_id", "target_type", "target_tmdb_id",
            name="uq_cross_media_pair",
        ),
    )
    with op.batch_alter_table("cross_media_mappings", schema=None) as batch_op:
        for column in ("source_type", "source_tmdb_id", "target_type", "target_tmdb_id"):
            batch_op.create_index(
                batch_op.f(f"ix_cross_media_mappings_{column}"), [column], unique=False
            )


def downgrade() -> None:
    op.drop_table("cross_media_mappings")
