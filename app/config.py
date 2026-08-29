"""Bootstrap settings loaded from environment variables.

This is intentionally minimal for Phase 0 (CI/repo skeleton) — just enough for the app to boot
and for BASE_URL-aware routing to exist from the start (see technical challenge #10 in
PROJECT_PLAN.md: base URL correctness is easy to regress if it isn't there from day one).

Full settings (Plex/TMDb/Radarr/Sonarr, PUID/PGID handling, scheduling, webhooks) land in
Phase 1 alongside the SQLModel schema — most of those live in the DB `settings` table after
first boot, not here; env vars are only the bootstrap/convenience path.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


def _normalize_base_url(raw: str) -> str:
    """Normalize BASE_URL to a form like '' or '/franchisarr' (no trailing slash)."""
    value = raw.strip()
    if value in ("", "/"):
        return ""
    if not value.startswith("/"):
        value = "/" + value
    return value.rstrip("/")


@dataclass(frozen=True)
class Settings:
    base_url: str
    log_level: str


def get_settings() -> Settings:
    return Settings(
        base_url=_normalize_base_url(os.environ.get("BASE_URL", "/")),
        log_level=os.environ.get("LOG_LEVEL", "INFO").upper(),
    )
