"""Collections the library has completed, for Showcase's celebrations.

Revision ID: 0032
Revises: 0031
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel
from alembic import op

revision: str = "0032"
down_revision: str | None = "0031"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "collection_completions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("collection_id", sa.Integer(), nullable=False),
        sa.Column("name", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=False),
        sa.Column("celebrate", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_collection_completions_collection_id"), "collection_completions", ["collection_id"],
                    unique=True)


def downgrade() -> None:
    op.drop_index(op.f("ix_collection_completions_collection_id"), table_name="collection_completions")
    op.drop_table("collection_completions")
