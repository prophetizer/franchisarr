"""add tmdb show cache

Revision ID: 0005
Revises: 0004
Create Date: 2026-08-31 02:07:11.386496

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel  # SQLModel columns render as sqlmodel.sql.sqltypes.AutoString
from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Reviewed by hand.
    op.create_table('tmdb_shows',
    sa.Column('tmdb_id', sa.Integer(), nullable=False),
    sa.Column('name', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('first_air_year', sa.Integer(), nullable=True),
    sa.Column('network', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    sa.Column('fetched_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('tmdb_id')
    )
    with op.batch_alter_table('tmdb_shows', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_tmdb_shows_fetched_at'), ['fetched_at'], unique=False)

    


def downgrade() -> None:
    # Reviewed by hand.
    with op.batch_alter_table('tmdb_shows', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_tmdb_shows_fetched_at'))

    op.drop_table('tmdb_shows')
    
