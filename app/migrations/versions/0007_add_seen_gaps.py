"""add seen gaps

Revision ID: 0007
Revises: 0006
Create Date: 2026-08-31 09:39:01.657878

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel  # SQLModel columns render as sqlmodel.sql.sqltypes.AutoString
from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Reviewed by hand.
    op.create_table('seen_gaps',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('item_type', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('tmdb_id', sa.Integer(), nullable=False),
    sa.Column('title', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('first_seen_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('item_type', 'tmdb_id', name='uq_seen_gap')
    )
    with op.batch_alter_table('seen_gaps', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_seen_gaps_item_type'), ['item_type'], unique=False)
        batch_op.create_index(batch_op.f('ix_seen_gaps_tmdb_id'), ['tmdb_id'], unique=False)

    


def downgrade() -> None:
    # Reviewed by hand.
    with op.batch_alter_table('seen_gaps', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_seen_gaps_tmdb_id'))
        batch_op.drop_index(batch_op.f('ix_seen_gaps_item_type'))

    op.drop_table('seen_gaps')
    
