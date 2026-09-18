"""neutral user identity

Revision ID: 0019
Revises: 0018
Create Date: 2026-09-18 22:00:00.000000

A user used to be a Plex account or a local admin. With Jellyfin and Emby sign-in the external
identity is (provider, id): plex_user_id becomes external_user_id, plex_username becomes
external_username, and auth_provider records which server vouched. Existing Plex users are
marked as such; local admins stay unmarked.
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel  # SQLModel columns render as sqlmodel.sql.sqltypes.AutoString
from alembic import op

revision: str = "0019"
down_revision: str | None = "0018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_users_plex_user_id"))
        batch_op.alter_column("plex_user_id", new_column_name="external_user_id")
        batch_op.alter_column("plex_username", new_column_name="external_username")
        batch_op.add_column(sa.Column("auth_provider", sqlmodel.sql.sqltypes.AutoString(), nullable=True))
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_users_external_user_id"), ["external_user_id"], unique=True)
    op.execute("UPDATE users SET auth_provider = 'plex' WHERE external_user_id IS NOT NULL")


def downgrade() -> None:
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_users_external_user_id"))
        batch_op.drop_column("auth_provider")
        batch_op.alter_column("external_username", new_column_name="plex_username")
        batch_op.alter_column("external_user_id", new_column_name="plex_user_id")
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_users_plex_user_id"), ["plex_user_id"], unique=True)
