"""settle user on delete semantics

Revision ID: 0008
Revises: 0007
Create Date: 2026-08-31 11:09:11.186359

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel  # SQLModel columns render as sqlmodel.sql.sqltypes.AutoString
from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: Lets batch mode name the unnamed constraints 0001 created, so they can be dropped.
NAMING_CONVENTION = {
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
}


def upgrade() -> None:
    # SQLite cannot ALTER a foreign key, so each table is rebuilt via batch mode -- which is
    # exactly why render_as_batch was turned on in Phase 1.
    #
    # The constraints created in 0001 are unnamed, and batch mode cannot drop what it cannot
    # name. Supplying a naming convention lets SQLAlchemy derive the name it would have had, so
    # the drop can be expressed at all. Without this the whole migration is impossible on SQLite.
    for table, column, action in (
        ("activity_log", "triggered_by", "SET NULL"),
        ("collection_excludes", "added_by_user_id", "SET NULL"),
        ("dismissed_items", "user_id", "CASCADE"),
        ("spinoff_mappings", "added_by_user_id", "SET NULL"),
    ):
        with op.batch_alter_table(
            table, schema=None, naming_convention=NAMING_CONVENTION
        ) as batch_op:
            batch_op.drop_constraint(
                f"fk_{table}_{column}_users", type_="foreignkey"
            )
            batch_op.create_foreign_key(
                f"fk_{table}_{column}_users", "users", [column], ["id"], ondelete=action
            )


def downgrade() -> None:
    for table, column in (
        ("activity_log", "triggered_by"),
        ("collection_excludes", "added_by_user_id"),
        ("dismissed_items", "user_id"),
        ("spinoff_mappings", "added_by_user_id"),
    ):
        with op.batch_alter_table(
            table, schema=None, naming_convention=NAMING_CONVENTION
        ) as batch_op:
            batch_op.drop_constraint(f"fk_{table}_{column}_users", type_="foreignkey")
            batch_op.create_foreign_key(
                f"fk_{table}_{column}_users", "users", [column], ["id"]
            )
