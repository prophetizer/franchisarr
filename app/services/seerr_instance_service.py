"""Seerr instances: CRUD, the request cache, and what it means for the lists.

Mirrors instance_service for Radarr, minus the defaults -- Seerr has no profile or folder to
choose, it decides those itself. What it adds is the notion of a request that exists but has
not been fulfilled: pending approval, or approved and on its way. Either is "handled", so the
title leaves the gap lists the way a queued Radarr add does.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from sqlmodel import Session, col, delete, select

from app.clients.seerr_client import SeerrClient, SeerrError
from app.models import ItemType, SeerrInstance, SeerrKind, SeerrRequest, utcnow

logger = logging.getLogger(__name__)

LABELS = {
    SeerrKind.SEERR.value: "Seerr",
    SeerrKind.OVERSEERR.value: "Overseerr",
    SeerrKind.JELLYSEERR.value: "Jellyseerr",
}


@dataclass(frozen=True)
class SeerrRefresh:
    instance_id: int
    name: str
    requests: int = 0
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None


def label(instance: SeerrInstance) -> str:
    return LABELS.get(instance.kind, "Seerr")


def list_seerr(session: Session) -> list[SeerrInstance]:
    return list(session.exec(select(SeerrInstance).order_by(col(SeerrInstance.name))).all())


def get_seerr(session: Session, instance_id: int) -> SeerrInstance | None:
    return session.get(SeerrInstance, instance_id)


def client_for(instance: SeerrInstance) -> SeerrClient:
    return SeerrClient(instance.url, instance.api_key, label=label(instance))


def create_seerr(session: Session, **fields) -> SeerrInstance:
    instance = SeerrInstance(**fields)
    if not list_seerr(session):
        instance.is_default = True
    session.add(instance)
    session.commit()
    session.refresh(instance)
    return instance


def set_default(session: Session, instance_id: int) -> None:
    for instance in list_seerr(session):
        instance.is_default = instance.id == instance_id
        session.add(instance)
    session.commit()


def delete_seerr(session: Session, instance_id: int) -> None:
    instance = session.get(SeerrInstance, instance_id)
    if instance is None:
        return
    was_default = instance.is_default
    session.delete(instance)
    session.commit()
    if was_default:
        remaining = list_seerr(session)
        if remaining:
            set_default(session, remaining[0].id)


def refresh_instance_cache(session: Session, instance: SeerrInstance) -> SeerrRefresh:
    """Re-read the open requests. An unreachable instance keeps its previous cache, for the
    reason instance_service gives: "couldn't ask" must not become "has nothing"."""
    try:
        requests = client_for(instance).list_requests()
    except SeerrError as exc:
        logger.warning("Could not refresh %s instance %r: %s", label(instance), instance.name, exc)
        return SeerrRefresh(instance.id, instance.name, error=str(exc))

    # Bulk delete plus flush, so the DELETE reaches the database before the INSERTs
    # (see instance_service.refresh_instance_cache).
    session.exec(delete(SeerrRequest).where(col(SeerrRequest.instance_id) == instance.id))
    session.flush()
    seen: set[tuple[str, int]] = set()
    for request in requests:
        media_type = ItemType.SHOW.value if request.media_type == "tv" else ItemType.MOVIE.value
        if (media_type, request.tmdb_id) in seen:
            continue
        seen.add((media_type, request.tmdb_id))
        session.add(SeerrRequest(instance_id=instance.id, media_type=media_type, tmdb_id=request.tmdb_id,
                                 status=request.status, fetched_at=utcnow()))
    session.commit()
    return SeerrRefresh(instance.id, instance.name, requests=len(seen))


def refresh_all(session: Session) -> list[SeerrRefresh]:
    return [refresh_instance_cache(session, instance) for instance in list_seerr(session)]


def requested_ids(session: Session, item_type: str) -> set[int]:
    """TMDb ids with an open request on any Seerr instance. Handled, so not a gap."""
    return {
        tmdb_id for tmdb_id in session.exec(
            select(SeerrRequest.tmdb_id).where(col(SeerrRequest.media_type) == item_type)
        ).all()
    }


def record_request(session: Session, instance: SeerrInstance, item_type: str, tmdb_id: int, status: int) -> None:
    """Reflect a request just made, so the title leaves the lists without waiting for a scan."""
    existing = session.exec(
        select(SeerrRequest).where(col(SeerrRequest.instance_id) == instance.id,
                                   col(SeerrRequest.media_type) == item_type,
                                   col(SeerrRequest.tmdb_id) == tmdb_id)
    ).first()
    if existing is None:
        session.add(SeerrRequest(instance_id=instance.id, media_type=item_type, tmdb_id=tmdb_id, status=status))
    else:
        existing.status = status
        existing.fetched_at = utcnow()
        session.add(existing)
    session.commit()
