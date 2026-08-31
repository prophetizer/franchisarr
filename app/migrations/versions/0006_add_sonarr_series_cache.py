"""add sonarr series cache

Revision ID: 0006
Revises: 0005
Create Date: 2026-08-31 08:47:53.067857

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel  # SQLModel columns render as sqlmodel.sql.sqltypes.AutoString
from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Reviewed by hand.
    op.create_table('sonarr_series',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('instance_id', sa.Integer(), nullable=False),
    sa.Column('tmdb_id', sa.Integer(), nullable=False),
    sa.Column('tvdb_id', sa.Integer(), nullable=True),
    sa.Column('title', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('monitored', sa.Boolean(), nullable=False),
    sa.Column('in_queue', sa.Boolean(), nullable=False),
    sa.Column('fetched_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['instance_id'], ['sonarr_instances.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('instance_id', 'tmdb_id', name='uq_sonarr_series')
    )
    with op.batch_alter_table('sonarr_series', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_sonarr_series_instance_id'), ['instance_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_sonarr_series_tmdb_id'), ['tmdb_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_sonarr_series_tvdb_id'), ['tvdb_id'], unique=False)

    


def downgrade() -> None:
    # Reviewed by hand.
    with op.batch_alter_table('sonarr_series', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_sonarr_series_tvdb_id'))
        batch_op.drop_index(batch_op.f('ix_sonarr_series_tmdb_id'))
        batch_op.drop_index(batch_op.f('ix_sonarr_series_instance_id'))

    op.drop_table('sonarr_series')
    
