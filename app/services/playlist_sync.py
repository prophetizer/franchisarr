"""Playlist sync: copy chosen playlists from their home server to every other server.

Decided with michael (0.38.0):
- Only the playlists someone switches on; one source per playlist, copied to every other server
  that's switched on. Edits to a copy are overwritten at the next sync.
- The account Franchisarr already uses on each server: the Plex token's owner, the Jellyfin/Emby
  "watched as" user.
- A title the target doesn't have is left out and reported. A same-named playlist that sync
  didn't make is never touched: that copy is reported as blocked.
- Same name, and the source's poster when it has one of its own. Plex smart playlists are copied
  as what they hold at each sync. Franchisarr's own "(Franchisarr)" playlists aren't offered:
  Make a playlist builds those per server already. Music and photo playlists aren't either.
- A source playlist that's gone takes its copies with it -- only copies sync made, known by id.
  A source that merely can't be reached never does: that's an error, not a deletion.
- Runs after each scan (when library matching is freshest) and on "Sync now"; notifies only on
  failure.

Two switches added after (0.39.0, michael): "sync every playlist" makes every eligible playlist a
source, new ones too, while any can still be switched off (a row with enabled=False remembers
that); and "keep Franchisarr's playlists on every server" builds a "(Franchisarr)" playlist on
the servers that lack it from their own libraries -- so each is complete for its server, not a
trimmed mirror -- and deletes it everywhere once it's deleted on a server it was on.

Titles are matched across servers by TMDb id through the library rows each scan keeps: a film
by its own id, an episode by its show's id plus season and episode number. A title in a
library Franchisarr doesn't scan can't be matched anywhere, and is reported as such.
"""

from __future__ import annotations

import hashlib
import json
import logging
import threading
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone

from sqlmodel import Session, col, select

from app.models import FranchisarrPlaylistPresence, LibraryItem, MediaServer, PlaylistCopy, PlaylistSync
from app.services.playlist_service import SUFFIX

logger = logging.getLogger(__name__)

#: How many unmatched titles each copy remembers for the page.
UNMATCHED_KEEP = 40


def eligible(info) -> bool:  # noqa: ANN001 - PlaylistInfo
    """Offered for sync: video playlists that aren't Franchisarr's own."""
    return info.video and not info.title.endswith(SUFFIX)


# ------------------------------------------------------------------ progress


@dataclass(frozen=True)
class SyncProgress:
    running: bool = False
    trigger: str = ""
    done: int = 0
    total: int = 0
    current: str = ""
    created: int = 0
    updated: int = 0
    unchanged: int = 0
    deleted: int = 0
    blocked: int = 0
    failed: int = 0
    errors: tuple[str, ...] = ()
    started_at: datetime | None = None
    finished_at: datetime | None = None


_lock = threading.Lock()
_state = SyncProgress()


def current() -> SyncProgress:
    with _lock:
        return _state


def _set(**changes) -> None:
    global _state
    with _lock:
        _state = replace(_state, **changes)


def _bump(name: str, by: int = 1) -> None:
    _set(**{name: getattr(current(), name) + by})


def _error(message: str) -> None:
    _set(failed=current().failed + 1, errors=(current().errors + (message,))[:8])


# ------------------------------------------------------------------ choosing what syncs


@dataclass
class PlaylistRow:
    id: str
    title: str
    count: int
    smart: bool
    sync: PlaylistSync | None = None
    copies: list[tuple[str, PlaylistCopy]] = field(default_factory=list)   # (server name, copy)
    #: Set when this playlist is itself a copy that sync made: (source title, source server).
    copy_of: tuple[str, str] | None = None
    #: "Sync every playlist" is on and this one has no row yet: it syncs at the next run.
    pending: bool = False

    @property
    def syncing(self) -> bool:
        return self.sync is not None and self.sync.enabled

    @property
    def excluded(self) -> bool:
        return self.sync is not None and not self.sync.enabled


@dataclass
class ServerPlaylists:
    server: MediaServer
    rows: list[PlaylistRow] = field(default_factory=list)
    error: str | None = None
    #: How many "(Franchisarr)" playlists it has, for the keep-them-everywhere summary.
    franchisarr: int = 0


def sync_all(session: Session) -> bool:
    from app.services.settings_service import SettingKey, get_bool_setting

    return get_bool_setting(session, SettingKey.PLAYLIST_SYNC_ALL, False)


def keep_franchisarr(session: Session) -> bool:
    from app.services.settings_service import SettingKey, get_bool_setting

    return get_bool_setting(session, SettingKey.PLAYLIST_SYNC_FRANCHISARR, False)


def set_switches(session: Session, *, every: bool, franchisarr: bool) -> None:
    """Save the two switches. Turning "sync every playlist" off drops what it added and the
    switch-offs it was remembering; their copies stay, as with Stop syncing."""
    from sqlmodel import delete as sql_delete

    from app.services.settings_service import SettingKey, set_setting

    if sync_all(session) and not every:
        session.exec(sql_delete(PlaylistSync).where(
            (col(PlaylistSync.auto) == True) | (col(PlaylistSync.enabled) == False)))  # noqa: E712
    set_setting(session, SettingKey.PLAYLIST_SYNC_ALL, "true" if every else "false")
    set_setting(session, SettingKey.PLAYLIST_SYNC_FRANCHISARR, "true" if franchisarr else "false")
    session.commit()


def page(session: Session) -> list[ServerPlaylists]:
    """Every eligible playlist on every server that's on, with what's syncing and what's a copy."""
    from app.services import media_server_service

    servers = media_server_service.enabled_servers(session)
    names = {s.id: s.name for s in media_server_service.list_servers(session)}
    syncs = {(s.source_server_id, s.source_playlist_id): s for s in session.exec(select(PlaylistSync)).all()}
    copies = session.exec(select(PlaylistCopy)).all()
    by_sync: dict[int, list[PlaylistCopy]] = {}
    copy_index: dict[tuple[int, str], PlaylistCopy] = {}
    for copy in copies:
        by_sync.setdefault(copy.sync_id, []).append(copy)
        if copy.target_playlist_id:
            copy_index[(copy.target_server_id, copy.target_playlist_id)] = copy
    sync_by_id = {s.id: s for s in syncs.values()}
    every = sync_all(session)

    found = []
    for server in servers:
        entry = ServerPlaylists(server=server)
        try:
            listing = media_server_service.client_for(server).list_playlists()
        except Exception as exc:  # noqa: BLE001 -- shown on the page, logged in full
            logger.exception("Couldn't list playlists on %s", server.name)
            entry.error = f"Couldn't be reached ({type(exc).__name__})."
            found.append(entry)
            continue
        entry.franchisarr = sum(1 for i in listing if i.video and i.title.endswith(SUFFIX))
        for info in sorted((i for i in listing if eligible(i)), key=lambda i: i.title.casefold()):
            row = PlaylistRow(info.id, info.title, info.count, info.smart)
            copy = copy_index.get((server.id, info.id))
            if copy is not None and copy.sync_id in sync_by_id:
                source = sync_by_id[copy.sync_id]
                row.copy_of = (source.title, names.get(source.source_server_id, "?"))
            else:
                row.sync = syncs.get((server.id, info.id))
                if row.sync is not None:
                    row.copies = [(names.get(c.target_server_id, "?"), c) for c in by_sync.get(row.sync.id, [])]
                else:
                    row.pending = every
            entry.rows.append(row)
        found.append(entry)
    return found


def enable(session: Session, server_id: int, playlist_id: str, title: str) -> PlaylistSync:
    """Start syncing a playlist. A playlist that is itself a sync copy can't be a source: that
    would copy the copy back."""
    existing = session.exec(select(PlaylistSync).where(
        col(PlaylistSync.source_server_id) == server_id, col(PlaylistSync.source_playlist_id) == playlist_id)).first()
    if existing is not None:
        if not existing.enabled:
            existing.enabled = True
            session.add(existing)
            session.commit()
        return existing
    if session.exec(select(PlaylistCopy.id).where(
            col(PlaylistCopy.target_server_id) == server_id, col(PlaylistCopy.target_playlist_id) == playlist_id)).first():
        raise ValueError("That playlist is a copy made by sync; turn sync on for its source instead.")
    sync = PlaylistSync(source_server_id=server_id, source_playlist_id=playlist_id, title=title)
    session.add(sync)
    session.commit()
    session.refresh(sync)
    logger.info("Playlist sync on for %r", title)
    return sync


def disable(session: Session, sync_id: int) -> None:
    """Stop syncing. The copies stay, as ordinary playlists nobody syncs any more. While "sync
    every playlist" is on the row is kept, switched off, or the next run would adopt it again."""
    sync = session.get(PlaylistSync, sync_id)
    if sync is None:
        return
    if sync_all(session):
        sync.enabled = False
        session.add(sync)
    else:
        session.delete(sync)
    session.commit()
    logger.info("Playlist sync off for %r", sync.title)


def exclude(session: Session, server_id: int, playlist_id: str, title: str) -> None:
    """"Don't sync" for a playlist "sync every playlist" hasn't adopted yet."""
    existing = session.exec(select(PlaylistSync).where(
        col(PlaylistSync.source_server_id) == server_id, col(PlaylistSync.source_playlist_id) == playlist_id)).first()
    if existing is None:
        session.add(PlaylistSync(source_server_id=server_id, source_playlist_id=playlist_id, title=title,
                                 enabled=False))
    else:
        existing.enabled = False
        session.add(existing)
    session.commit()


# ------------------------------------------------------------------ syncing


def _fingerprint(title: str, keys: list[str]) -> str:
    return hashlib.sha1(("\n".join([title, *keys])).encode()).hexdigest()


class _Run:
    """What one sync run looks up once and reuses: clients, listings and library maps."""

    def __init__(self, session: Session) -> None:
        from app.services import media_server_service

        self.session = session
        self.servers = {s.id: s for s in media_server_service.enabled_servers(session)}
        self._clients: dict[int, object] = {}
        self._listings: dict[int, list] = {}
        self._keys: dict[int, dict[str, tuple[str, int]]] = {}
        self._by_tmdb: dict[int, dict[tuple[str, int], str]] = {}
        self._films: dict[int, dict[str, object]] = {}
        self._episodes: dict[tuple[int, str], dict[tuple[int, int], object]] = {}

    def client(self, server_id: int):  # noqa: ANN201
        from app.services import media_server_service

        if server_id not in self._clients:
            self._clients[server_id] = media_server_service.client_for(self.servers[server_id])
        return self._clients[server_id]

    def listing(self, server_id: int) -> list:
        if server_id not in self._listings:
            self._listings[server_id] = list(self.client(server_id).list_playlists())
        return self._listings[server_id]

    def _library(self, server_id: int) -> None:
        if server_id in self._keys:
            return
        rows = self.session.exec(select(LibraryItem.item_key, LibraryItem.item_type, LibraryItem.tmdb_id).where(
            col(LibraryItem.server_id) == server_id, col(LibraryItem.tmdb_id).is_not(None))).all()
        self._keys[server_id] = {key: (kind, tmdb) for key, kind, tmdb in rows}
        self._by_tmdb[server_id] = {(kind, tmdb): key for key, kind, tmdb in rows}

    def source_ids(self, server_id: int, ref) -> tuple[str, int] | None:  # noqa: ANN001
        """(item type, TMDb id) of a source playlist entry: the film's, or the episode's show's."""
        self._library(server_id)
        key = ref.key if ref.item_type == "movie" else ref.show_key
        return self._keys[server_id].get(key or "")

    def target_key(self, server_id: int, kind: str, tmdb_id: int) -> str | None:
        self._library(server_id)
        return self._by_tmdb[server_id].get((kind, tmdb_id))

    def films(self, server_id: int, keys: list[str]) -> dict[str, object]:
        known = self._films.setdefault(server_id, {})
        wanted = [k for k in dict.fromkeys(keys) if k not in known]
        if wanted:
            for entry in self.client(server_id).playlist_entries(wanted, []):
                known[entry.key] = entry.raw
        return known

    def episodes(self, server_id: int, show_key: str) -> dict[tuple[int, int], object]:
        cache_key = (server_id, show_key)
        if cache_key not in self._episodes:
            self._episodes[cache_key] = {
                (e.season, e.episode): e for e in self.client(server_id).playlist_entries([], [show_key])}
        return self._episodes[cache_key]


def run(session: Session) -> SyncProgress:
    """Sync every playlist that's switched on. Progress and totals go to `current()`."""
    work = _Run(session)
    if sync_all(session):
        _adopt_all(work)
    syncs = session.exec(select(PlaylistSync).where(col(PlaylistSync.enabled) == True)  # noqa: E712
                         .order_by(col(PlaylistSync.title))).all()
    _set(total=len(syncs))
    for index, sync in enumerate(syncs, start=1):
        _set(current=sync.title, done=index - 1)
        try:
            _sync_one(work, sync)
        except Exception as exc:  # noqa: BLE001 -- one playlist must not stop the rest
            logger.exception("Syncing %r failed", sync.title)
            _error(f"{sync.title}: {type(exc).__name__}")
        session.commit()
    _set(done=len(syncs), current="")
    if keep_franchisarr(session):
        _set(current="Franchisarr's playlists")
        try:
            _franchisarr(work)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Keeping Franchisarr's playlists in step failed")
            _error(f"Franchisarr's playlists: {type(exc).__name__}")
        _set(current="")
    return current()


def _adopt_all(work: _Run) -> None:
    """"Sync every playlist": each eligible playlist without a row becomes a source. Copies sync
    made are never adopted -- that would copy them back."""
    session = work.session
    known = {(r.source_server_id, r.source_playlist_id) for r in session.exec(select(PlaylistSync)).all()}
    copies = {(c.target_server_id, c.target_playlist_id) for c in session.exec(select(PlaylistCopy)).all()
              if c.target_playlist_id}
    for server_id in work.servers:
        try:
            listing = work.listing(server_id)
        except Exception:  # noqa: BLE001 -- reported when its playlists are synced
            continue
        for info in listing:
            if eligible(info) and (server_id, info.id) not in known and (server_id, info.id) not in copies:
                session.add(PlaylistSync(source_server_id=server_id, source_playlist_id=info.id, title=info.title,
                                         auto=True))
    session.commit()


def _franchisarr(work: _Run) -> None:
    """Keep each "(Franchisarr)" playlist on every server that's on: build it where it's missing
    from that server's own library (as Make a playlist would), and delete it everywhere once it's
    gone from a server it was on. A server that can't be reached takes no part either way."""
    from app.services import playlist_bulk, playlist_service

    session = work.session
    reachable: dict[int, list] = {}
    for server_id, server in work.servers.items():
        try:
            reachable[server_id] = work.listing(server_id)
        except Exception as exc:  # noqa: BLE001
            _error(f"Franchisarr's playlists: {server.name} couldn't be reached ({type(exc).__name__})")
    present: dict[str, set[int]] = {}
    ids: dict[tuple[str, int], list[str]] = {}
    for server_id, listing in reachable.items():
        for p in listing:
            if p.video and p.title.endswith(SUFFIX):
                present.setdefault(p.title, set()).add(server_id)
                ids.setdefault((p.title, server_id), []).append(p.id)
    records = {r.title: r for r in session.exec(select(FranchisarrPlaylistPresence)).all()}
    sets_by_name = None
    for title in sorted(set(present) | set(records)):
        now = set(present.get(title, set()))
        record = records.get(title)
        before = set(json.loads(record.server_ids)) if record else set()
        if {s for s in before if s in reachable} - now:
            # Deleted on a server it was on: delete it everywhere.
            for server_id in now:
                for playlist_id in ids.get((title, server_id), []):
                    work.client(server_id).delete_playlist_id(playlist_id)
                    _bump("deleted")
            if record is not None:
                session.delete(record)
            continue
        missing = [s for s in reachable if s not in now]
        if missing and now:
            if sets_by_name is None:
                sets_by_name = {s.name: s for s in reversed(playlist_bulk.sets(session, playlist_bulk.KINDS))}
            item = sets_by_name.get(title[: -len(SUFFIX)])
            for server_id in missing if item is not None else []:
                result = playlist_service.build(session, item.name, item.refs, item.art, server_id=server_id,
                                                min_items=playlist_bulk.MIN_ITEMS)
                if any(s.error is None for s in result.servers):
                    now.add(server_id)
                    _bump("created")
                for s in result.servers:
                    if s.error:
                        _error(f"{title} on {s.server}: {s.error}")
        record = record or FranchisarrPlaylistPresence(title=title)
        unreachable_before = {s for s in before if s not in reachable}
        record.server_ids = json.dumps(sorted(now | unreachable_before))
        record.updated_at = datetime.now(timezone.utc)
        session.add(record)
    session.commit()


def _sync_one(work: _Run, sync: PlaylistSync) -> None:
    session = work.session
    copies = {c.target_server_id: c for c in session.exec(
        select(PlaylistCopy).where(col(PlaylistCopy.sync_id) == sync.id)).all()}
    if sync.source_server_id not in work.servers:
        return          # its home server is turned off: leave everything as it is
    try:
        source_listing = work.listing(sync.source_server_id)
    except Exception as exc:  # noqa: BLE001
        _error(f"{sync.title}: {work.servers[sync.source_server_id].name} couldn't be reached ({type(exc).__name__})")
        return
    info = next((p for p in source_listing if p.id == sync.source_playlist_id), None)
    if info is None:
        _source_gone(work, sync, copies)
        return
    sync.title = info.title
    refs = work.client(sync.source_server_id).playlist_items(info.id)
    poster: bytes | None | bool = False      # fetched once, only if a copy is being written

    for server_id in work.servers:
        if server_id == sync.source_server_id:
            continue
        copy = copies.get(server_id) or PlaylistCopy(sync_id=sync.id, target_server_id=server_id)
        session.add(copy)
        target_name = work.servers[server_id].name
        try:
            listing = work.listing(server_id)
            if any(p.title == info.title and p.id != copy.target_playlist_id for p in listing):
                copy.status, copy.message = "blocked", f"{target_name} already has a playlist called “{info.title}” that sync didn't make."
                _bump("blocked")
                continue
            raws, keys, missing = _resolve(work, sync.source_server_id, server_id, refs, target_name)
            copy.matched, copy.unmatched = len(raws), len(missing)
            copy.unmatched_titles = json.dumps(missing[:UNMATCHED_KEEP]) if missing else None
            exists = copy.target_playlist_id is not None and any(p.id == copy.target_playlist_id for p in listing)
            if not raws:
                if exists:
                    work.client(server_id).delete_playlist_id(copy.target_playlist_id)
                    listing[:] = [p for p in listing if p.id != copy.target_playlist_id]
                copy.target_playlist_id, copy.fingerprint = None, None
                copy.status, copy.message = "empty", f"None of its titles are on {target_name}."
                continue
            fingerprint = _fingerprint(info.title, keys)
            if exists and copy.fingerprint == fingerprint:
                copy.status, copy.message = "ok", None
                _bump("unchanged")
                continue
            client = work.client(server_id)
            if exists:
                client.delete_playlist_id(copy.target_playlist_id)
                listing[:] = [p for p in listing if p.id != copy.target_playlist_id]
            new_id = client.create_playlist(info.title, raws)
            listing.append(replace(info, id=new_id))
            _bump("updated" if exists else "created")
            copy.target_playlist_id, copy.fingerprint = new_id, fingerprint
            copy.status, copy.message = "ok", None
            if poster is False:
                poster = _poster(work, sync.source_server_id, info.id)
            if poster:
                try:
                    client.set_playlist_poster_id(new_id, poster)
                except Exception:  # noqa: BLE001 -- a copy without the poster is still a copy
                    logger.warning("Couldn't copy the poster of %r to %s", info.title, target_name, exc_info=True)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Syncing %r to %s failed", info.title, target_name)
            copy.status, copy.message = "error", f"{target_name} refused or couldn't be reached ({type(exc).__name__})."
            _error(f"{info.title} → {target_name}: {type(exc).__name__}")
        finally:
            copy.synced_at = datetime.now(timezone.utc)
    sync.last_synced_at = datetime.now(timezone.utc)


def _poster(work: _Run, server_id: int, playlist_id: str) -> bytes | None:
    try:
        return work.client(server_id).playlist_poster(playlist_id)
    except Exception:  # noqa: BLE001
        logger.warning("Couldn't read the poster of playlist %s", playlist_id, exc_info=True)
        return None


def _resolve(work: _Run, source_id: int, target_id: int, refs: list, target_name: str
             ) -> tuple[list, list[str], list[str]]:
    """The target's items for `refs`, in order: (raw items, their keys, titles not matched)."""
    missing: list[str] = []
    plan: list[tuple[str, object]] = []      # ("film", key) or ("episode", (show_key, season, episode))
    for ref in refs:
        if ref.item_type == "other":
            missing.append(f"{ref.title} (not a film or episode)")
            continue
        ids = work.source_ids(source_id, ref)
        if ids is None:
            missing.append(f"{ref.title} (not in a library Franchisarr scans)")
            continue
        kind, tmdb_id = ids
        key = work.target_key(target_id, kind, tmdb_id)
        if key is None:
            missing.append(f"{ref.title} (not on {target_name})")
            continue
        plan.append(("film", key) if ref.item_type == "movie" else ("episode", (key, ref.season, ref.episode, ref.title)))

    films = work.films(target_id, [k for kind, k in plan if kind == "film"])
    raws, keys = [], []
    for kind, value in plan:
        if kind == "film":
            raw = films.get(value)
            if raw is None:
                missing.append(f"{value} (no longer on {target_name})")
                continue
            raws.append(raw)
            keys.append(value)
        else:
            show_key, season, number, title = value
            entry = work.episodes(target_id, show_key).get((season, number))
            if entry is None:
                missing.append(f"{title} (episode not on {target_name})")
                continue
            raws.append(entry.raw)
            keys.append(entry.key or "")
    return raws, keys, missing


def _source_gone(work: _Run, sync: PlaylistSync, copies: dict[int, PlaylistCopy]) -> None:
    """The source playlist was deleted: delete its copies (only those sync made, by id). A copy
    on a server that's off can't be reached; the sync is kept until it can."""
    session = work.session
    for server_id, copy in list(copies.items()):
        if server_id not in work.servers:
            continue
        if copy.target_playlist_id:
            try:
                work.client(server_id).delete_playlist_id(copy.target_playlist_id)
                _bump("deleted")
            except Exception as exc:  # noqa: BLE001
                _error(f"{sync.title}: couldn't delete the copy on {work.servers[server_id].name} ({type(exc).__name__})")
                continue
        session.delete(copy)
        del copies[server_id]
    if not copies:
        logger.info("Playlist %r was deleted at its source; its copies are gone and sync is off", sync.title)
        session.delete(sync)


def run_in_background(trigger: str) -> bool:
    """Start a sync on its own thread. False: one is already running, or nothing is switched on."""
    global _state
    from app.db import get_engine

    with Session(get_engine()) as session:
        if (session.exec(select(PlaylistSync.id).limit(1)).first() is None
                and not sync_all(session) and not keep_franchisarr(session)):
            return False
    with _lock:
        if _state.running:
            return False
        _state = SyncProgress(running=True, trigger=trigger, started_at=datetime.now(timezone.utc))

    def _work() -> None:
        try:
            with Session(get_engine()) as session:
                run(session)
        except Exception as exc:  # noqa: BLE001 -- the state must never stay "running"
            logger.exception("Playlist sync failed")
            _error(type(exc).__name__)
        finally:
            _set(running=False, finished_at=datetime.now(timezone.utc), current="")
            state = current()
            logger.info("Playlist sync (%s): %d created, %d updated, %d unchanged, %d deleted, %d blocked, %d failed",
                        trigger, state.created, state.updated, state.unchanged, state.deleted, state.blocked, state.failed)
            if state.failed:
                _notify(state)

    threading.Thread(target=_work, name="franchisarr-playlist-sync", daemon=True).start()
    return True


def _notify(state: SyncProgress, session: Session | None = None) -> None:
    """Only on failure (michael's call): through the same webhook the scans use."""
    from app.db import get_engine
    from app.services import notifier
    from app.services.settings_service import SettingKey, get_setting

    with (session if session is not None else Session(get_engine())) as db:
        url = get_setting(db, SettingKey.WEBHOOK_URL)
        fmt = get_setting(db, SettingKey.WEBHOOK_FORMAT) or "generic"
    if url:
        notifier.send_message(url, f"Franchisarr: playlist sync had {state.failed} problem{'' if state.failed == 1 else 's'}",
                              list(state.errors), fmt)
