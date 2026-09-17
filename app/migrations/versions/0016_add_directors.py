"""add directors

Revision ID: 0016
Revises: 0015
Create Date: 2026-09-17 16:00:00.000000

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel  # SQLModel columns render as sqlmodel.sql.sqltypes.AutoString
from alembic import op

revision: str = "0016"
down_revision: str | None = "0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "movie_directors",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tmdb_movie_id", sa.Integer(), nullable=False),
        sa.Column("person_id", sa.Integer(), nullable=False),
        sa.Column("name", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("fetched_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tmdb_movie_id", "person_id", name="uq_movie_director"),
    )
    with op.batch_alter_table("movie_directors", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_movie_directors_tmdb_movie_id"), ["tmdb_movie_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_movie_directors_person_id"), ["person_id"], unique=False)

    op.create_table(
        "director_films",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("person_id", sa.Integer(), nullable=False),
        sa.Column("tmdb_movie_id", sa.Integer(), nullable=False),
        sa.Column("title", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("release_date", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("poster_path", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("vote_average", sa.Float(), nullable=True),
        sa.Column("vote_count", sa.Integer(), nullable=True),
        sa.Column("is_documentary", sa.Boolean(), nullable=False),
        sa.Column("fetched_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("person_id", "tmdb_movie_id", name="uq_director_film"),
    )
    with op.batch_alter_table("director_films", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_director_films_person_id"), ["person_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_director_films_tmdb_movie_id"), ["tmdb_movie_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_director_films_fetched_at"), ["fetched_at"], unique=False)


def downgrade() -> None:
    op.drop_table("director_films")
    op.drop_table("movie_directors")
