"""Alembic environment.

Two things matter here:
  * the database URL comes from the app's own config, never from alembic.ini, so `alembic
    upgrade head` inside the container hits the same /config SQLite file the app opens;
  * `render_as_batch=True`, because SQLite cannot ALTER most column properties in place --
    without it, any future column change would be unmigratable on other people's databases.
"""

from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool
from sqlmodel import SQLModel

from app import models  # noqa: F401  -- import registers every table on SQLModel.metadata
from app.db import get_database_url

config = context.config

# Tests set configure_logger=False so running a migration does not stomp on pytest's own
# logging configuration (and, in turn, the secret-redaction handler under test).
if config.config_file_name is not None and config.attributes.get("configure_logger", True):
    fileConfig(config.config_file_name)

target_metadata = SQLModel.metadata


def _url() -> str:
    # An explicit -x url=... wins (used by tests), then alembic.ini, then the app config.
    return (
        context.get_x_argument(as_dictionary=True).get("url")
        or config.get_main_option("sqlalchemy.url")
        or get_database_url()
    )


def run_migrations_offline() -> None:
    context.configure(
        url=_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = create_engine(_url(), poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
