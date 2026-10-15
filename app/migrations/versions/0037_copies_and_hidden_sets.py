"""a film's number of copies; collections and franchises a person has hidden

Revision ID: 0037
Revises: 0036
Create Date: 2026-10-15 12:00:00.000000

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel  # SQLModel columns render as sqlmodel.sql.sqltypes.AutoString
from alembic import op

revision: str = "0037"
down_revision: str | None = "0036"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Filled by the next scan, which rewrites every row it sees.
    with op.batch_alter_table("library_items", schema=None) as batch_op:
        batch_op.add_column(sa.Column("copies", sa.Integer(), nullable=True))
    op.create_table(
        "user_hidden_sets",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", name="fk_user_hidden_sets_user_id_users",
                                                          ondelete="CASCADE"), nullable=False),
        sa.Column("kind", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("ref", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("user_id", "kind", "ref", name="uq_user_hidden_set"),
    )
    op.create_index("ix_user_hidden_sets_user_id", "user_hidden_sets", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_user_hidden_sets_user_id", table_name="user_hidden_sets")
    op.drop_table("user_hidden_sets")
    with op.batch_alter_table("library_items", schema=None) as batch_op:
        batch_op.drop_column("copies")
