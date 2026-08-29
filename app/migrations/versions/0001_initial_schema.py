"""initial schema

Revision ID: 0001
Revises: 
Create Date: 2026-08-29 17:00:42.912181

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel  # SQLModel columns render as sqlmodel.sql.sqltypes.AutoString
from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Reviewed by hand; batch_alter_table usage comes from render_as_batch (SQLite).
    op.create_table('included_libraries',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('plex_library_key', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('plex_library_name', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('library_type', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('enabled', sa.Boolean(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('included_libraries', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_included_libraries_plex_library_key'), ['plex_library_key'], unique=True)

    op.create_table('radarr_instances',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('url', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('api_key', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('default_root_folder', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    sa.Column('default_quality_profile_id', sa.Integer(), nullable=True),
    sa.Column('is_default', sa.Boolean(), nullable=False),
    sa.Column('hide_if_queued', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('radarr_instances', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_radarr_instances_name'), ['name'], unique=False)

    op.create_table('settings',
    sa.Column('key', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('value', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('key')
    )
    op.create_table('sonarr_instances',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('url', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('api_key', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('default_root_folder', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    sa.Column('default_quality_profile_id', sa.Integer(), nullable=True),
    sa.Column('default_monitor_mode', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('is_default', sa.Boolean(), nullable=False),
    sa.Column('hide_if_queued', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('sonarr_instances', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_sonarr_instances_name'), ['name'], unique=False)

    op.create_table('users',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('plex_user_id', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    sa.Column('plex_username', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    sa.Column('local_username', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    sa.Column('password_hash', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    sa.Column('is_admin', sa.Boolean(), nullable=False),
    sa.Column('api_key', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_users_api_key'), ['api_key'], unique=True)
        batch_op.create_index(batch_op.f('ix_users_local_username'), ['local_username'], unique=True)
        batch_op.create_index(batch_op.f('ix_users_plex_user_id'), ['plex_user_id'], unique=True)

    op.create_table('activity_log',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('timestamp', sa.DateTime(), nullable=False),
    sa.Column('item_type', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('tmdb_id', sa.Integer(), nullable=False),
    sa.Column('title', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('instance_id', sa.Integer(), nullable=True),
    sa.Column('triggered_by', sa.Integer(), nullable=True),
    sa.Column('trigger_source', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.ForeignKeyConstraint(['triggered_by'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('activity_log', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_activity_log_timestamp'), ['timestamp'], unique=False)
        batch_op.create_index(batch_op.f('ix_activity_log_tmdb_id'), ['tmdb_id'], unique=False)

    op.create_table('collection_excludes',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('tmdb_collection_id', sa.Integer(), nullable=False),
    sa.Column('tmdb_movie_id', sa.Integer(), nullable=False),
    sa.Column('added_by_user_id', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['added_by_user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('tmdb_collection_id', 'tmdb_movie_id', name='uq_collection_exclude')
    )
    with op.batch_alter_table('collection_excludes', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_collection_excludes_tmdb_collection_id'), ['tmdb_collection_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_collection_excludes_tmdb_movie_id'), ['tmdb_movie_id'], unique=False)

    op.create_table('dismissed_items',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('item_type', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('tmdb_id', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('user_id', 'item_type', 'tmdb_id', name='uq_dismissed_item')
    )
    with op.batch_alter_table('dismissed_items', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_dismissed_items_tmdb_id'), ['tmdb_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_dismissed_items_user_id'), ['user_id'], unique=False)

    op.create_table('spinoff_mappings',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('source_show_tmdb_id', sa.Integer(), nullable=False),
    sa.Column('spinoff_show_tmdb_id', sa.Integer(), nullable=False),
    sa.Column('source', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('confidence', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('origin_ref', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    sa.Column('added_by_user_id', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['added_by_user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('source_show_tmdb_id', 'spinoff_show_tmdb_id', name='uq_spinoff_pair')
    )
    with op.batch_alter_table('spinoff_mappings', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_spinoff_mappings_source_show_tmdb_id'), ['source_show_tmdb_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_spinoff_mappings_spinoff_show_tmdb_id'), ['spinoff_show_tmdb_id'], unique=False)

    


def downgrade() -> None:
    # Reviewed by hand; batch_alter_table usage comes from render_as_batch (SQLite).
    with op.batch_alter_table('spinoff_mappings', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_spinoff_mappings_spinoff_show_tmdb_id'))
        batch_op.drop_index(batch_op.f('ix_spinoff_mappings_source_show_tmdb_id'))

    op.drop_table('spinoff_mappings')
    with op.batch_alter_table('dismissed_items', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_dismissed_items_user_id'))
        batch_op.drop_index(batch_op.f('ix_dismissed_items_tmdb_id'))

    op.drop_table('dismissed_items')
    with op.batch_alter_table('collection_excludes', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_collection_excludes_tmdb_movie_id'))
        batch_op.drop_index(batch_op.f('ix_collection_excludes_tmdb_collection_id'))

    op.drop_table('collection_excludes')
    with op.batch_alter_table('activity_log', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_activity_log_tmdb_id'))
        batch_op.drop_index(batch_op.f('ix_activity_log_timestamp'))

    op.drop_table('activity_log')
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_users_plex_user_id'))
        batch_op.drop_index(batch_op.f('ix_users_local_username'))
        batch_op.drop_index(batch_op.f('ix_users_api_key'))

    op.drop_table('users')
    with op.batch_alter_table('sonarr_instances', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_sonarr_instances_name'))

    op.drop_table('sonarr_instances')
    op.drop_table('settings')
    with op.batch_alter_table('radarr_instances', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_radarr_instances_name'))

    op.drop_table('radarr_instances')
    with op.batch_alter_table('included_libraries', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_included_libraries_plex_library_key'))

    op.drop_table('included_libraries')
    
