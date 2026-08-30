"""add library snapshot and tmdb cache

Revision ID: 0003
Revises: 0002
Create Date: 2026-08-30 01:46:58.638426

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel  # SQLModel columns render as sqlmodel.sql.sqltypes.AutoString
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Reviewed by hand.
    op.create_table('library_items',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('plex_library_key', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('rating_key', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('item_type', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('title', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('year', sa.Integer(), nullable=True),
    sa.Column('tmdb_id', sa.Integer(), nullable=True),
    sa.Column('imdb_id', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    sa.Column('tvdb_id', sa.Integer(), nullable=True),
    sa.Column('match_source', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('match_confidence', sa.Float(), nullable=True),
    sa.Column('needs_review', sa.Boolean(), nullable=False),
    sa.Column('last_seen_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('plex_library_key', 'rating_key', name='uq_library_item')
    )
    with op.batch_alter_table('library_items', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_library_items_last_seen_at'), ['last_seen_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_library_items_plex_library_key'), ['plex_library_key'], unique=False)
        batch_op.create_index(batch_op.f('ix_library_items_rating_key'), ['rating_key'], unique=False)
        batch_op.create_index(batch_op.f('ix_library_items_tmdb_id'), ['tmdb_id'], unique=False)

    op.create_table('tmdb_collections',
    sa.Column('tmdb_collection_id', sa.Integer(), nullable=False),
    sa.Column('name', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('fetched_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('tmdb_collection_id')
    )
    with op.batch_alter_table('tmdb_collections', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_tmdb_collections_fetched_at'), ['fetched_at'], unique=False)

    op.create_table('tmdb_movies',
    sa.Column('tmdb_id', sa.Integer(), nullable=False),
    sa.Column('title', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('release_year', sa.Integer(), nullable=True),
    sa.Column('collection_id', sa.Integer(), nullable=True),
    sa.Column('fetched_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('tmdb_id')
    )
    with op.batch_alter_table('tmdb_movies', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_tmdb_movies_collection_id'), ['collection_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_tmdb_movies_fetched_at'), ['fetched_at'], unique=False)

    op.create_table('tmdb_collection_movies',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('collection_id', sa.Integer(), nullable=False),
    sa.Column('tmdb_movie_id', sa.Integer(), nullable=False),
    sa.Column('title', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('release_year', sa.Integer(), nullable=True),
    sa.Column('release_date', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    sa.Column('position', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['collection_id'], ['tmdb_collections.tmdb_collection_id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('collection_id', 'tmdb_movie_id', name='uq_collection_member')
    )
    with op.batch_alter_table('tmdb_collection_movies', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_tmdb_collection_movies_collection_id'), ['collection_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_tmdb_collection_movies_tmdb_movie_id'), ['tmdb_movie_id'], unique=False)

    


def downgrade() -> None:
    # Reviewed by hand.
    with op.batch_alter_table('tmdb_collection_movies', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_tmdb_collection_movies_tmdb_movie_id'))
        batch_op.drop_index(batch_op.f('ix_tmdb_collection_movies_collection_id'))

    op.drop_table('tmdb_collection_movies')
    with op.batch_alter_table('tmdb_movies', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_tmdb_movies_fetched_at'))
        batch_op.drop_index(batch_op.f('ix_tmdb_movies_collection_id'))

    op.drop_table('tmdb_movies')
    with op.batch_alter_table('tmdb_collections', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_tmdb_collections_fetched_at'))

    op.drop_table('tmdb_collections')
    with op.batch_alter_table('library_items', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_library_items_tmdb_id'))
        batch_op.drop_index(batch_op.f('ix_library_items_rating_key'))
        batch_op.drop_index(batch_op.f('ix_library_items_plex_library_key'))
        batch_op.drop_index(batch_op.f('ix_library_items_last_seen_at'))

    op.drop_table('library_items')
    
