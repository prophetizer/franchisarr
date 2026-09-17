"""add franchises

Revision ID: 0015
Revises: 0014
Create Date: 2026-09-17 09:00:00.000000

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel  # SQLModel columns render as sqlmodel.sql.sqltypes.AutoString
from alembic import op

revision: str = "0015"
down_revision: str | None = "0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "franchises",
        sa.Column("wikidata_id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("name", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("kind", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("fetched_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("wikidata_id"),
    )
    with op.batch_alter_table("franchises", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_franchises_fetched_at"), ["fetched_at"], unique=False)

    op.create_table(
        "franchise_members",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("franchise_id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("item_type", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("tmdb_id", sa.Integer(), nullable=False),
        sa.Column("title", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("year", sa.Integer(), nullable=True),
        sa.Column("poster_path", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.ForeignKeyConstraint(
            ["franchise_id"], ["franchises.wikidata_id"], ondelete="CASCADE",
            name="fk_franchise_members_franchise_id_franchises",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("franchise_id", "item_type", "tmdb_id", name="uq_franchise_member"),
    )
    with op.batch_alter_table("franchise_members", schema=None) as batch_op:
        for column in ("franchise_id", "item_type", "tmdb_id"):
            batch_op.create_index(
                batch_op.f(f"ix_franchise_members_{column}"), [column], unique=False
            )


def downgrade() -> None:
    op.drop_table("franchise_members")
    op.drop_table("franchises")
