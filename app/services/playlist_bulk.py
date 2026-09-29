"""Making playlists in bulk: every franchise, collection or director, on one server or all.

On a real library that's hundreds of playlists per server -- 207 franchises, 409 collections and
148 directors on the developer's -- each a read of the server, a write, and a poster fetched from
TMDb, so it runs on a background thread with progress, like a scan, and can be stopped between
playlists. One bulk job at a time. A set whose titles on a server number fewer than two is
skipped there (michael's call): a playlist of one film isn't worth having. Each one joins the
Franchisarr playlist set (0.42.0), so it's kept current after that; one that already exists is
brought up to date in place, exactly as "Make a playlist" does.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone

from sqlmodel import Session

from app.models import ItemType

logger = logging.getLogger(__name__)

KINDS = ("franchises", "collections", "directors")
MIN_ITEMS = 2


@dataclass(frozen=True)
class BulkProgress:
    running: bool = False
    stopping: bool = False
    where: str = ""
    done: int = 0
    total: int = 0
    current: str = ""
    made: int = 0
    skipped: int = 0
    failed: int = 0
    errors: tuple[str, ...] = ()
    started_at: datetime | None = None
    finished_at: datetime | None = None

    @property
    def percent(self) -> int:
        return int(self.done * 100 / self.total) if self.total else 0


_lock = threading.Lock()
_state = BulkProgress()


def current() -> BulkProgress:
    with _lock:
        return _state


def _set(**changes) -> None:
    global _state
    with _lock:
        _state = replace(_state, **changes)


def stop() -> None:
    """Ask a running job to stop after the playlist it's on."""
    global _state
    with _lock:
        if _state.running:
            _state = replace(_state, stopping=True)


@dataclass
class PlaylistSet:
    kind: str
    name: str
    refs: list[tuple[str, int]] = field(default_factory=list)
    art: object = None
    #: The page it comes from: a Wikidata id, a collection id or a person id, as a string.
    ref: str = ""


def sets(session: Session, kinds: tuple[str, ...] | list[str], *, min_refs: int = MIN_ITEMS) -> list[PlaylistSet]:
    """Every set of the chosen kinds with at least `min_refs` owned titles, with the refs and
    poster artwork "Make a playlist" would use for it."""
    from app.services import director_service, franchise_service, movie_gap_service
    from app.services.playlist_service import art_from

    found: list[PlaylistSet] = []
    if "franchises" in kinds:
        for view in franchise_service.franchise_views(session):
            refs = [(t.item_type, t.tmdb_id) for t in view.owned_films + view.owned_shows]
            found.append(PlaylistSet("franchises", view.name, refs, art_from(view.backdrop_path, view.owned_films),
                                     str(view.wikidata_id)))
    if "collections" in kinds:
        for gap in movie_gap_service.collection_gaps(session):
            refs = [(ItemType.MOVIE.value, m.tmdb_id) for m in gap.owned]
            found.append(PlaylistSet("collections", gap.name, refs, art_from(getattr(gap, "backdrop_path", None), gap.owned),
                                     str(gap.collection_id)))
    if "directors" in kinds:
        for view in director_service.director_views(session):
            refs = [(ItemType.MOVIE.value, m.tmdb_id) for m in view.owned]
            found.append(PlaylistSet("directors", view.name, refs, art_from(None, view.owned), str(view.person_id)))
    return [s for s in found if len(s.refs) >= min_refs]


def counts(session: Session) -> dict[str, int]:
    """How many playlists each kind would make at most (per server), for the dialog."""
    return {kind: len(sets(session, (kind,))) for kind in KINDS}


def run(session: Session, kinds: list[str], server_id: int | None, where: str) -> None:
    from app.services import franchisarr_playlists
    from app.services.playlist_sync import _Run

    work = sets(session, kinds)
    servers = _Run(session)       # one listing per server for the whole job
    _set(total=len(work), where=where)
    for index, item in enumerate(work, start=1):
        if current().stopping:
            break
        _set(current=f"{item.name}", done=index - 1)
        try:
            result = franchisarr_playlists.make(session, item.kind, item.ref, item.name, item.refs, item.art,
                                                server_id=server_id, min_items=MIN_ITEMS, work=servers)
        except Exception as exc:  # noqa: BLE001 -- one set must not end the whole run
            logger.exception("Bulk playlist %r failed", item.name)
            state = current()
            _set(failed=state.failed + 1, errors=(state.errors + (f"{item.name}: {type(exc).__name__}",))[:5])
            continue
        state = current()
        made = sum(1 for s in result.servers if s.error is None)
        failures = [f"{item.name} on {s.server}: {s.error}" for s in result.servers if s.error]
        _set(made=state.made + made, skipped=state.skipped + result.skipped,
             failed=state.failed + len(failures), errors=(state.errors + tuple(failures))[:5])
        session.expire_all()   # a long job must not hold every row it has read
    _set(done=current().total if not current().stopping else current().done)


def run_in_background(kinds: list[str], server_id: int | None, where: str) -> bool:
    """Start a bulk job. False means one is already running."""
    global _state
    with _lock:
        if _state.running:
            return False
        _state = BulkProgress(running=True, where=where, started_at=datetime.now(timezone.utc))

    def _work() -> None:
        from app.db import get_engine

        try:
            with Session(get_engine()) as session:
                run(session, kinds, server_id, where)
        except Exception as exc:  # noqa: BLE001 -- the state must never stay "running"
            logger.exception("Bulk playlists failed")
            _set(errors=(current().errors + (type(exc).__name__,))[:5])
        finally:
            state = current()
            _set(running=False, finished_at=datetime.now(timezone.utc), current="")
            logger.info("Bulk playlists finished: %d made, %d skipped, %d failed%s", state.made,
                        state.skipped, state.failed, " (stopped)" if state.stopping else "")

    threading.Thread(target=_work, name="franchisarr-playlists", daemon=True).start()
    return True
