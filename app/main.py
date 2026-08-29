"""FastAPI application entrypoint.

Phase 0 scope only: enough of an app for CI (pytest + Docker build) to have something real to
exercise. Routes, auth, the data layer, and everything else in PROJECT_PLAN.md section 3
("High-level architecture") land in Phase 1 onward.
"""

from __future__ import annotations

from fastapi import APIRouter, FastAPI

from app.config import get_settings

settings = get_settings()

app = FastAPI(title="Franchisarr")

# All real routes are mounted under BASE_URL so the app works correctly behind a reverse proxy
# at a subpath from day one (see PROJECT_PLAN.md technical challenge #10).
router = APIRouter()


@router.get("/health")
def health() -> dict:
    """Liveness endpoint for Docker HEALTHCHECK / reverse-proxy monitoring. Unauthenticated."""
    return {"status": "ok"}


app.include_router(router, prefix=settings.base_url)
