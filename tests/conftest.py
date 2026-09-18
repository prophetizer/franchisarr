"""Shared fixtures.

Note the `isolated_env` autouse fixture: every env var Franchisarr reads is cleared before each
test, so a developer's own exported PLEX_TOKEN or BASE_URL can never change a test's outcome.
"""

from __future__ import annotations

import importlib
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
    "MEDIA_SERVER",
    "JELLYFIN_URL",
    "JELLYFIN_API_KEY",
    "EMBY_URL",
    "EMBY_API_KEY",
)


def seed_server(session: Session, kind: str = "plex", *, name: str | None = None,
                url: str | None = None, credential: str = "k" * 32, **fields) -> "models.MediaServer":
    """A media server row for tests that need library rows to hang off. Committed, id set."""
    default_url = "http://plex.test:32400" if kind == "plex" else f"http://{kind}.test:8096"
    server = models.MediaServer(name=name or kind.capitalize(), kind=kind, url=url or default_url,
                                credential=credential, **fields)
    session.add(server)
    session.commit()
    session.refresh(server)
    return server


def plex_source(session: Session, url: str, token: str) -> list:
    """[ScanSource] for a Plex at `url`, reusing the test's server row when its URL matches so
    library rows made with ensure_server() belong to the server being scanned."""
    from sqlmodel import select

    from app.clients.plex_client import PlexClient
    from app.services.scan_service import ScanSource

    server = session.exec(select(models.MediaServer).order_by(models.MediaServer.id)).first()
    if server is None:
        server = seed_server(session, "plex", url=url, credential=token)
    elif server.url != url:
        server.url = url
        session.add(server); session.commit(); session.refresh(server)
    return [ScanSource(server, PlexClient(url, token))]


def ensure_server(session: Session) -> int:
    """The id of a Plex server row, made on first call. For tests whose subject is something
    else entirely and just need library rows to have a server to belong to."""
    from sqlmodel import select

    existing = session.exec(select(models.MediaServer).order_by(models.MediaServer.id)).first()
    return existing.id if existing else seed_server(session, "plex").id


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
def app_factory(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Build the FastAPI app with a chosen BASE_URL and a throwaway database.

    app.main binds BASE_URL when it mounts its routers, so exercising a subpath deployment means
    re-importing it. The module is restored afterwards so later tests see it as they expect.
    """
    import app.main

    def build(base_url: str = "", **env: str):
        monkeypatch.setenv("BASE_URL", base_url or "/")
        monkeypatch.setenv("DB_PATH", str(tmp_path / "franchisarr.db"))
        monkeypatch.setenv("LOG_LEVEL", "WARNING")
        for key, value in env.items():
            monkeypatch.setenv(key, value)
        reset_engine()
        return importlib.reload(app.main)

    yield build

    monkeypatch.undo()
    reset_engine()
    importlib.reload(app.main)


@pytest.fixture
def fixtures_dir() -> Path:
    return Path(__file__).parent / "fixtures"
