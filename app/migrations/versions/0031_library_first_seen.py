"""When each library item was first seen, for the home page's "Just added".

Existing rows get none: nobody recorded when they arrived, and dating them all today would call
the whole library new.

Revision ID: 0031
Revises: 0030
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0031"
down_revision: str | None = "0030"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("library_items", schema=None) as batch_op:
        batch_op.add_column(sa.Column("first_seen_at", sa.DateTime(), nullable=True))
        batch_op.create_index(batch_op.f("ix_library_items_first_seen_at"), ["first_seen_at"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("library_items", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_library_items_first_seen_at"))
        batch_op.drop_column("first_seen_at")
