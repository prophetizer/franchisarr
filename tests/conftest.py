"""Shared fixtures.

Note the `isolated_env` autouse fixture: every env var Franchisarr reads is cleared before each
test, so a developer's own exported PLEX_TOKEN or BASE_URL can never change a test's outcome.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from sqlmodel import Session, SQLModel

from app import models  # noqa: F401  -- registers tables on SQLModel.metadata
from app.db import create_db_engine, reset_engine

FRANCHISARR_ENV_VARS = (
    "BASE_URL",
    "LOG_LEVEL",
    "DB_PATH",
    "FRANCHISARR_CONFIG_DIR",
    "PLEX_URL",
    "PLEX_TOKEN",
    "TMDB_API_KEY",
    "TMDB_CACHE_TTL_DAYS",
    "SCAN_SCHEDULE_CRON",
    "WEBHOOK_URL",
    "WEBHOOK_FORMAT",
    "CROSS_INSTANCE_DEDUP",
    "RADARR_URL",
    "RADARR_API_KEY",
    "SONARR_URL",
    "SONARR_API_KEY",
    "ADMIN_USERNAME",
    "ADMIN_PASSWORD",
)


@pytest.fixture(autouse=True)
def isolated_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in FRANCHISARR_ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    reset_engine()
    yield
    reset_engine()


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "franchisarr.db"


@pytest.fixture
def engine(db_path: Path):
    """An engine over a freshly created schema.

    Built with `create_all` rather than by running migrations, deliberately: service tests should
    fail because of the service, not because of a migration. `tests/test_migrations.py` is what
    proves the migration and the models agree.
    """
    eng = create_db_engine(f"sqlite:///{db_path}")
    SQLModel.metadata.create_all(eng)
    yield eng
    eng.dispose()


@pytest.fixture
def session(engine) -> Session:
    with Session(engine) as sess:
        yield sess


@pytest.fixture
def fixtures_dir() -> Path:
    return Path(__file__).parent / "fixtures"
