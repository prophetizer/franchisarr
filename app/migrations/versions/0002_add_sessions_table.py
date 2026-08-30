"""add sessions table

Revision ID: 0002
Revises: 0001
Create Date: 2026-08-30 00:35:54.329855

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel  # SQLModel columns render as sqlmodel.sql.sqltypes.AutoString
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Reviewed by hand.
    op.create_table('sessions',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('token_hash', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('expires_at', sa.DateTime(), nullable=False),
    sa.Column('last_seen_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('sessions', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_sessions_expires_at'), ['expires_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_sessions_token_hash'), ['token_hash'], unique=True)
        batch_op.create_index(batch_op.f('ix_sessions_user_id'), ['user_id'], unique=False)

    


def downgrade() -> None:
    # Reviewed by hand.
    with op.batch_alter_table('sessions', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_sessions_user_id'))
        batch_op.drop_index(batch_op.f('ix_sessions_token_hash'))
        batch_op.drop_index(batch_op.f('ix_sessions_expires_at'))

    op.drop_table('sessions')
    
