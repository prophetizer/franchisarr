"""add radarr movie cache and last used instance

Revision ID: 0004
Revises: 0003
Create Date: 2026-08-30 14:58:26.979137

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel  # SQLModel columns render as sqlmodel.sql.sqltypes.AutoString
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Reviewed by hand.
    op.create_table('radarr_movies',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('instance_id', sa.Integer(), nullable=False),
    sa.Column('tmdb_id', sa.Integer(), nullable=False),
    sa.Column('title', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('monitored', sa.Boolean(), nullable=False),
    sa.Column('has_file', sa.Boolean(), nullable=False),
    sa.Column('in_queue', sa.Boolean(), nullable=False),
    sa.Column('fetched_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['instance_id'], ['radarr_instances.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('instance_id', 'tmdb_id', name='uq_radarr_movie')
    )
    with op.batch_alter_table('radarr_movies', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_radarr_movies_instance_id'), ['instance_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_radarr_movies_tmdb_id'), ['tmdb_id'], unique=False)

    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('last_radarr_instance_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('last_sonarr_instance_id', sa.Integer(), nullable=True))

    


def downgrade() -> None:
    # Reviewed by hand.
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_column('last_sonarr_instance_id')
        batch_op.drop_column('last_radarr_instance_id')

    with op.batch_alter_table('radarr_movies', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_radarr_movies_tmdb_id'))
        batch_op.drop_index(batch_op.f('ix_radarr_movies_instance_id'))

    op.drop_table('radarr_movies')
    
