"""Database engine/session plumbing.

The SQLite file lives inside the mounted config volume so it survives container replacement.
`DB_PATH` overrides the full path outright; otherwise it defaults to `franchisarr.db` inside
`FRANCHISARR_CONFIG_DIR` (which the Dockerfile sets to /config). The two compose rather than
compete: `FRANCHISARR_CONFIG_DIR` says *where the volume is*, `DB_PATH` says *where the DB is*.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlmodel import Session, create_engine

DEFAULT_CONFIG_DIR = "/config"
DEFAULT_DB_FILENAME = "franchisarr.db"

_engine: Engine | None = None


def get_database_path() -> Path:
    """Resolve the SQLite file path from the environment."""
    explicit = os.environ.get("DB_PATH", "").strip()
    if explicit:
        return Path(explicit)
    config_dir = os.environ.get("FRANCHISARR_CONFIG_DIR", "").strip() or DEFAULT_CONFIG_DIR
    return Path(config_dir) / DEFAULT_DB_FILENAME


def get_database_url() -> str:
    """SQLAlchemy URL for the configured SQLite file. Also read by the Alembic env."""
    return f"sqlite:///{get_database_path()}"


@event.listens_for(Engine, "connect")
def _set_sqlite_pragmas(dbapi_connection, connection_record) -> None:  # noqa: ANN001
    """SQLite disables foreign keys per-connection by default; WAL keeps reads unblocked
    while a scan writes. Both have to be set on every connection, not once per engine."""
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
    finally:
        cursor.close()


def create_db_engine(url: str | None = None, *, echo: bool = False) -> Engine:
    """Build an engine. `check_same_thread=False` because FastAPI serves requests from a
    threadpool while APScheduler writes from its own thread."""
    resolved = url or get_database_url()
    if resolved.startswith("sqlite:///"):
        path = Path(resolved.removeprefix("sqlite:///"))
        if str(path) != ":memory:":
            path.parent.mkdir(parents=True, exist_ok=True)
    return create_engine(resolved, echo=echo, connect_args={"check_same_thread": False})


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        _engine = create_db_engine()
    return _engine


def reset_engine() -> None:
    """Drop the cached engine — used by tests that repoint DB_PATH."""
    global _engine
    if _engine is not None:
        _engine.dispose()
    _engine = None


def get_session() -> Iterator[Session]:
    """FastAPI dependency yielding a session bound to the shared engine."""
    with Session(get_engine()) as session:
        yield session
