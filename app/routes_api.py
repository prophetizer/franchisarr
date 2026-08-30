"""JSON API.

The CLI and the web UI both come through here, which is the whole point of making the CLI an HTTP
client: there is one code path to keep correct, not two (PROJECT_PLAN.md decision log).
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, status

from app.auth.api_keys import generate_api_key
from app.auth.dependencies import DbSession, RequiredUser
from app.clients.plex_client import PlexClient
from app.clients.tmdb_client import TmdbAuthError, TmdbClient, TmdbError
from app.services import movie_gap_service, scan_service
from app.services.settings_service import SettingKey, get_setting

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api")


def _plex(session) -> PlexClient:
    url = get_setting(session, SettingKey.PLEX_URL)
    token = get_setting(session, SettingKey.PLEX_TOKEN)
    if not url or not token:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="No Plex connection is configured yet.",
        )
    return PlexClient(url, token)


def _tmdb(session) -> TmdbClient:
    api_key = get_setting(session, SettingKey.TMDB_API_KEY)
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="No TMDb API key is configured yet. Add one from themoviedb.org.",
        )
    return TmdbClient(api_key)


@router.get("/me")
def whoami(user: RequiredUser) -> dict:
    return {
        "id": user.id,
        "username": user.plex_username or user.local_username,
        "is_admin": user.is_admin,
    }


@router.post("/me/api-key")
def issue_api_key(session: DbSession, user: RequiredUser) -> dict:
    """Generate a CLI credential. Shown in full once and never again."""
    return {
        "api_key": generate_api_key(session, user),
        "note": "Store this now — it is not shown again. Send it as an X-Api-Key header.",
    }


@router.get("/tmdb/test")
def test_tmdb(session: DbSession, user: RequiredUser) -> dict:
    """Check the configured TMDb key and explain precisely what's wrong if it fails."""
    try:
        _tmdb(session).validate_key()
    except TmdbAuthError as exc:
        return {"ok": False, "error": str(exc)}
    except TmdbError as exc:
        return {"ok": False, "error": str(exc)}
    return {"ok": True}


@router.post("/scan/movies")
def scan_movies(session: DbSession, user: RequiredUser, force: bool = False) -> dict:
    """Re-walk the enabled movie libraries and refresh the TMDb cache.

    Synchronous for now: a scan of a few thousand films takes minutes, which is tolerable for a
    CLI invocation. Moving it onto the scheduler is Phase 8's job.
    """
    summary = scan_service.scan_movie_libraries(
        session, _plex(session), _tmdb(session), force_refresh=force
    )
    return {
        "libraries_scanned": summary.libraries_scanned,
        "items_seen": summary.items_seen,
        "matched": summary.matched,
        "needs_review": summary.needs_review,
        "unmatched": summary.unmatched,
        "removed": summary.removed,
        "collections_found": summary.collections_found,
        "tmdb_lookups": summary.tmdb_lookups,
        "errors": summary.errors,
    }


@router.get("/collections/gaps")
def collection_gaps(session: DbSession, user: RequiredUser, all: bool = False) -> dict:
    """Collections the library partly owns. By default only those with something missing."""
    gaps = (
        movie_gap_service.collection_gaps(session, user.id)
        if all
        else movie_gap_service.collections_with_gaps(session, user.id)
    )
    return {
        "collections": [
            {
                "collection_id": gap.collection_id,
                "name": gap.name,
                "owned_count": len(gap.owned),
                "missing_count": len(gap.missing),
                "missing": [
                    {"tmdb_id": m.tmdb_id, "title": m.title, "year": m.release_year}
                    for m in gap.missing
                ],
            }
            for gap in gaps
        ]
    }


@router.get("/matches/review")
def matches_needing_review(session: DbSession, user: RequiredUser) -> dict:
    """Plausible but unconfirmed matches, plus items nothing matched at all."""
    return {
        "needs_review": [
            {
                "title": item.title,
                "year": item.year,
                "tmdb_id": item.tmdb_id,
                "confidence": item.match_confidence,
            }
            for item in movie_gap_service.items_needing_review(session)
        ],
        "unmatched": [
            {"title": item.title, "year": item.year}
            for item in movie_gap_service.unmatched_items(session)
        ],
    }
