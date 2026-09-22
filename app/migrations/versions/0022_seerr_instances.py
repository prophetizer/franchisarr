"""seerr instances

Revision ID: 0022
Revises: 0021
Create Date: 2026-09-22 03:00:00.000000

Overseerr / Jellyseerr as an add target, alongside the Radarr and Sonarr instances, with a
cache of its existing requests so a pending request keeps a title out of the gap lists, and a
`target` on activity rows so a Seerr request is labelled as one.
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0022"
down_revision: str | None = "0021"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "seerr_instances",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("url", sa.String(), nullable=False),
        sa.Column("api_key", sa.String(), nullable=False),
        sa.Column("is_default", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_seerr_instances_name"), "seerr_instances", ["name"], unique=False)
    op.create_table(
        "seerr_requests",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("instance_id", sa.Integer(), nullable=False),
        sa.Column("media_type", sa.String(), nullable=False),
        sa.Column("tmdb_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.Integer(), nullable=False),
        sa.Column("fetched_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["instance_id"], ["seerr_instances.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("instance_id", "media_type", "tmdb_id", name="uq_seerr_request"),
    )
    op.create_index(op.f("ix_seerr_requests_instance_id"), "seerr_requests", ["instance_id"], unique=False)
    op.create_index(op.f("ix_seerr_requests_tmdb_id"), "seerr_requests", ["tmdb_id"], unique=False)
    # Which kind of instance an activity row's instance_id points at. Rows from before this
    # are all *arr adds, read by item type as before.
    with op.batch_alter_table("activity_log", schema=None) as batch_op:
        batch_op.add_column(sa.Column("target", sa.String(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("activity_log", schema=None) as batch_op:
        batch_op.drop_column("target")
    op.drop_table("seerr_requests")
    op.drop_table("seerr_instances")
