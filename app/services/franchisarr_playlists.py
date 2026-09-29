"""Franchisarr's own playlists, kept: "<name> (Franchisarr)" for a franchise, collection or
director, on the chosen servers, and kept current.

Decided with michael (0.42.0), replacing the "keep Franchisarr's playlists on every server"
switch and the build-once buttons:
- The set is the ones he makes: a page's playlist button adds that page, Add many adds many.
  The "(Franchisarr)" playlists already on the servers are taken in once, at the first sync after
  the upgrade.
- Each goes on the default servers (every one that's on, unless the Franchisarr playlists tab
  narrows it), or on the servers its buttons picked.
- Refreshed at every sync -- after each scan, on the schedule, on Sync now -- **in place**:
  titles added, removed and moved (media_server.edit_in_place), so the playlist keeps its id and
  poster. Nothing is deleted and remade, which is what lets a deletion be recognised at all.
- Deleted on any server by someone: deleted on every other one and dropped from the set. A server
  that's off or can't be reached is never read as a deletion, and a copy left on one is deleted
  when it's back (the row waits, `removed_at` set).
- A page that can't be found any more (a franchise Wikidata dropped, a director under the floor)
  leaves its playlists exactly as they are rather than emptying them: missing data is not a
  reason to delete someone's playlist.

Every write goes through a playlist's id, never its name -- see CLAUDE.md on replace_playlist.
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable

from sqlmodel import Session, col, select

from app.models import FranchisarrPlaylist, FranchisarrPlaylistCopy, ItemType, MediaServer
from app.services.playlist_service import SUFFIX, PlaylistResult, ServerResult, playlist_title

logger = logging.getLogger(__name__)

KIND_LABELS = {"franchises": "Franchise", "collections": "Collection", "directors": "Director"}
KIND_PATHS = {"franchises": "/franchises/", "collections": "/collections/", "directors": "/directors/"}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _quiet(name: str, by: int = 1) -> None:
    return None


# ------------------------------------------------------------------ which servers


def _ids(raw: str | None) -> set[int] | None:
    if not raw:
        return None
    try:
        return {int(i) for i in json.loads(raw)}
    except (ValueError, TypeError):
        return None


def default_servers(session: Session) -> set[int] | None:
    """The servers the set goes on unless an entry says otherwise; None for every one that's on."""
    from app.services.settings_service import SettingKey, get_setting

    return _ids(get_setting(session, SettingKey.FRANCHISARR_PLAYLIST_SERVERS))


def set_default_servers(session: Session, chosen: set[int]) -> None:
    """Save the default servers. Ticking every server that's on means "every server", new ones
    included; a server that's off but was chosen stays chosen."""
    from app.services import media_server_service
    from app.services.settings_service import SettingKey, set_setting

    enabled = {s.id for s in media_server_service.enabled_servers(session)}
    kept_off = {s for s in (default_servers(session) or set()) if s not in enabled}
    value = "" if chosen >= enabled else json.dumps(sorted((chosen & enabled) | kept_off))
    set_setting(session, SettingKey.FRANCHISARR_PLAYLIST_SERVERS, value)
    session.commit()


def servers_of(session: Session, entry: FranchisarrPlaylist, enabled: set[int],
               defaults: set[int] | None = None) -> set[int]:
    """The servers that's on that this playlist belongs on."""
    chosen = _ids(entry.servers)
    if chosen is None:
        chosen = defaults if defaults is not None else default_servers(session)
    return set(enabled) if chosen is None else chosen & enabled


# ------------------------------------------------------------------ the page


@dataclass
class EntryView:
    entry: FranchisarrPlaylist
    label: str
    path: str
    #: (server name, copy or None) for each server it belongs on, and any it's still on.
    copies: list[tuple[str, FranchisarrPlaylistCopy | None]]
    custom: bool
    #: A small poster (a director's photo) for the tab's list (0.46.0).
    poster: str | None = None

    @property
    def troubled(self) -> bool:
        return any(copy is not None and copy.status == "error" for _, copy in self.copies)


def _posters(session: Session, entries: list[FranchisarrPlaylist]) -> dict[tuple[str, str], str | None]:
    """A thumbnail per entry from what's stored, three queries in all: a collection's own
    poster, a franchise's earliest member with one, a director's photo."""
    from app.models import FranchiseMember, MovieDirector, TmdbCollection
    from app.services.artwork import SMALL_CARD_SIZE, poster_url, profile_url

    refs = {kind: [e.ref for e in entries if e.kind == kind] for kind in KIND_LABELS}
    found: dict[tuple[str, str], str | None] = {}
    collections = [int(r) for r in refs["collections"] if r.isdigit()]
    for cid, path in session.exec(select(TmdbCollection.tmdb_collection_id, TmdbCollection.poster_path)
                                  .where(col(TmdbCollection.tmdb_collection_id).in_(collections))).all():
        found[("collections", str(cid))] = poster_url(path, SMALL_CARD_SIZE)
    for fid, path in session.exec(select(FranchiseMember.franchise_id, FranchiseMember.poster_path)
                                  .where(col(FranchiseMember.franchise_id).in_(refs["franchises"]),
                                         col(FranchiseMember.poster_path).is_not(None))
                                  .order_by(col(FranchiseMember.year))).all():
        found.setdefault(("franchises", fid), poster_url(path, SMALL_CARD_SIZE))
    people = [int(r) for r in refs["directors"] if r.isdigit()]
    for pid, path in session.exec(select(MovieDirector.person_id, MovieDirector.profile_path)
                                  .where(col(MovieDirector.person_id).in_(people))).all():
        if path:
            found.setdefault(("directors", str(pid)), profile_url(path))
    return found


def page(session: Session) -> list[EntryView]:
    """The set, for the Franchisarr playlists tab: nothing here calls a server."""
    from app.services import media_server_service

    servers = media_server_service.list_servers(session)
    names = {s.id: s.name for s in servers}
    enabled = {s.id for s in servers if s.enabled}
    defaults = default_servers(session)
    copies: dict[int, dict[int, FranchisarrPlaylistCopy]] = {}
    for copy in session.exec(select(FranchisarrPlaylistCopy)).all():
        copies.setdefault(copy.playlist_id, {})[copy.server_id] = copy
    views = []
    entries = session.exec(select(FranchisarrPlaylist).where(col(FranchisarrPlaylist.removed_at).is_(None))
                           .order_by(col(FranchisarrPlaylist.name))).all()
    posters = _posters(session, entries)
    for entry in entries:
        mine = copies.get(entry.id, {})
        wanted = servers_of(session, entry, enabled, defaults)
        shown = sorted(wanted | {s for s, c in mine.items() if c.server_playlist_id and s in enabled},
                       key=lambda s: names.get(s, "").casefold())
        views.append(EntryView(entry, KIND_LABELS.get(entry.kind, entry.kind),
                               KIND_PATHS.get(entry.kind, "/") + entry.ref,
                               [(names.get(s, "?"), mine.get(s)) for s in shown], entry.servers is not None,
                               posters.get((entry.kind, entry.ref))))
    return views


def count(session: Session) -> int:
    return len(session.exec(select(FranchisarrPlaylist.id).where(col(FranchisarrPlaylist.removed_at).is_(None))).all())


def kept_on(session: Session, kind: str, ref: str) -> list[str]:
    """The servers a page's playlist is kept on, by name, for its banner: none if it isn't kept."""
    entry = entry_for(session, kind, ref)
    if entry is None:
        return []
    names = {s.id: s.name for s in session.exec(select(MediaServer)).all() if s.enabled}
    return sorted((names[c.server_id] for c in _copies(session, entry).values()
                   if c.server_playlist_id and c.server_id in names), key=str.casefold)


def entry_for(session: Session, kind: str, ref: str) -> FranchisarrPlaylist | None:
    return session.exec(select(FranchisarrPlaylist).where(
        col(FranchisarrPlaylist.kind) == kind, col(FranchisarrPlaylist.ref) == str(ref),
        col(FranchisarrPlaylist.removed_at).is_(None))).first()


# ------------------------------------------------------------------ making one


def make(session: Session, kind: str, ref: str, name: str, refs: list[tuple[str, int]], art,  # noqa: ANN001
         *, server_id: int | None = None, min_items: int = 1, work=None) -> PlaylistResult:  # noqa: ANN001
    """A page's playlist button (and each set of Add many): add it to the set and build it now,
    on `server_id` or on every server it belongs on. Pressing it again refreshes it."""
    from app.services import media_server_service
    from app.services.playlist_sync import _Run

    work = work or _Run(session)
    entry = session.exec(select(FranchisarrPlaylist).where(
        col(FranchisarrPlaylist.kind) == kind, col(FranchisarrPlaylist.ref) == str(ref))).first()
    if entry is None:
        entry = FranchisarrPlaylist(kind=kind, ref=str(ref), name=name, min_items=min_items)
    elif entry.removed_at is not None:
        entry.removed_at, entry.servers, entry.min_items = None, None, min_items
    else:
        entry.min_items = min(entry.min_items, min_items)
    enabled = {s.id for s in media_server_service.enabled_servers(session)}
    if server_id is None:
        entry.servers = None          # "On every server": the default servers, new ones too
    else:
        # "On Plex": Plex joins this playlist's servers. Following the defaults already covers
        # it unless the defaults leave Plex out, and then the list is spelled out.
        chosen = _ids(entry.servers)
        if chosen is None:
            defaults = default_servers(session)
            if defaults is not None and server_id not in defaults:
                entry.servers = json.dumps(sorted(defaults | {server_id}))
        elif server_id not in chosen:
            entry.servers = json.dumps(sorted(chosen | {server_id}))
    session.add(entry)
    session.commit()
    session.refresh(entry)

    result = PlaylistResult(title=playlist_title(entry.name))
    if server_id is not None:
        server = session.get(MediaServer, server_id)
        result.only = server.name if server else None
        targets = {server_id} & enabled
    else:
        targets = servers_of(session, entry, enabled)
    _build(work, entry, refs, art, targets, result=result)
    session.commit()
    return result


# ------------------------------------------------------------------ keeping them


def _fingerprint(keys: list[str]) -> str:
    return hashlib.sha1("\n".join(keys).encode()).hexdigest()


def _copies(session: Session, entry: FranchisarrPlaylist) -> dict[int, FranchisarrPlaylistCopy]:
    return {c.server_id: c for c in session.exec(
        select(FranchisarrPlaylistCopy).where(col(FranchisarrPlaylistCopy.playlist_id) == entry.id)).all()}


def _build(work, entry: FranchisarrPlaylist, refs: list[tuple[str, int]], art, targets: set[int],  # noqa: ANN001, C901
           *, result: PlaylistResult | None = None, bump: Callable = _quiet, error: Callable = _quiet) -> None:
    """Put `entry` on each server in `targets` holding at least its minimum of `refs`, creating
    it where it's missing and editing it in place where it's out of date."""
    from app.clients.media_server import edit_in_place
    from app.services.playlist_service import _owned_items, order_entries

    session = work.session
    title = playlist_title(entry.name)
    copies = _copies(session, entry)
    owned = _owned_items(session, refs)
    for server_id in sorted(targets):
        server = work.servers.get(server_id)
        if server is None:
            continue
        items = owned.get(server_id, [])
        copy = copies.get(server_id) or FranchisarrPlaylistCopy(playlist_id=entry.id, server_id=server_id)
        session.add(copy)
        copies[server_id] = copy
        outcome = ServerResult(server=server.name)
        try:
            listing = work.listing(server_id)
            present = {p.id: p for p in listing}
            if len(items) < entry.min_items:
                if copy.server_playlist_id and copy.server_playlist_id in present:
                    work.client(server_id).delete_playlist_id(copy.server_playlist_id)
                    listing[:] = [p for p in listing if p.id != copy.server_playlist_id]
                    bump("deleted")
                copy.server_playlist_id, copy.fingerprint, copy.items = None, None, 0
                copy.status = "small"
                copy.message = (f"None of it is on {server.name}." if not items else
                                f"Only {len(items)} of it on {server.name}; it takes {entry.min_items}.")
                if result is not None:
                    result.skipped += 1
                continue
            if result is not None:
                result.servers.append(outcome)
            films = [i.item_key for i in items if i.item_type == ItemType.MOVIE.value]
            shows = [i.item_key for i in items if i.item_type == ItemType.SHOW.value]
            basis = _fingerprint(sorted(films) + ["|"] + sorted(shows))
            existing = present.get(copy.server_playlist_id or "")
            if existing is None:
                # Never made, or made before the set kept ids: take a same-named one of ours.
                existing = next((p for p in listing if p.title == title), None)
                copy.server_playlist_id = existing.id if existing else None
            if (existing is not None and not shows and copy.fingerprint == basis
                    and existing.count == copy.items and copy.status == "ok"):
                bump("unchanged")
                outcome.films = copy.items
                continue
            client = work.client(server_id)
            entries = order_entries(client.playlist_entries(films, shows))
            if not entries:
                outcome.error = "None of these titles could be found on the server any more."
                copy.status, copy.message = "error", outcome.error
                continue
            wanted = [(e.key or "", e.raw) for e in entries]
            if existing is None:
                new_id = client.create_playlist(title, [raw for _, raw in wanted])
                listing.append(_info(new_id, title, len(entries)))
                copy.server_playlist_id = new_id
                changed = True
                bump("created")
            else:
                changed = edit_in_place(client, existing.id, wanted)
                bump("updated" if changed else "unchanged")
            outcome.films = sum(1 for e in entries if e.show_key is None)
            outcome.episodes = len(entries) - outcome.films
            outcome.shows = len({e.show_key for e in entries if e.show_key is not None})
            if changed and art is not None:
                outcome.poster = _poster(client, copy.server_playlist_id, entry.name, outcome, art)
            copy.fingerprint, copy.items = basis, len(entries)
            copy.status, copy.message = "ok", None
        except Exception as exc:  # noqa: BLE001 -- reported on the page and in the run, logged in full
            logger.exception("Couldn't build playlist %r on %s", title, server.name)
            outcome.error = f"The server refused or couldn't be reached ({type(exc).__name__})."
            copy.status, copy.message = "error", outcome.error
            error(f"{title} on {server.name}: {type(exc).__name__}")
            if result is not None and outcome not in result.servers:
                result.servers.append(outcome)
        finally:
            copy.refreshed_at = _now()
    entry.refreshed_at = _now()
    session.add(entry)


def _info(playlist_id: str, title: str, count: int):  # noqa: ANN202
    from app.clients.media_server import PlaylistInfo

    return PlaylistInfo(id=playlist_id, title=title, count=count)


def _poster(client, playlist_id: str | None, name: str, outcome: ServerResult, art) -> bool:  # noqa: ANN001
    """Render the poster with the new counts and put it on by id. Never raises."""
    from app.services import playlist_poster

    if not playlist_id:
        return False
    image = playlist_poster.render(name, films=outcome.films, episodes=outcome.episodes, shows=outcome.shows,
                                   backdrop_url=art.backdrop_url, poster_urls=list(art.poster_urls))
    if image is None:
        return False
    try:
        return bool(client.set_playlist_poster_id(playlist_id, image))
    except Exception:  # noqa: BLE001
        logger.warning("Couldn't upload the poster for %r", name, exc_info=True)
        return False


def refresh(work, *, bump: Callable = _quiet, error: Callable = _quiet,  # noqa: ANN001, C901
            progress: Callable[[str], None] | None = None) -> None:
    """Keep the whole set: take in existing playlists once, act on deletions, then bring every
    entry up to date on every server it belongs on. Called by every playlist sync run."""
    from app.services import playlist_bulk
    from app.services.settings_service import SettingKey, get_bool_setting

    session = work.session
    if (session.exec(select(FranchisarrPlaylist.id).limit(1)).first() is None
            and not get_bool_setting(session, SettingKey.FRANCHISARR_PLAYLISTS_TO_ADOPT, False)):
        return                    # nothing kept, nothing to take in: don't even ask the servers
    reachable: dict[int, list] = {}
    for server_id, server in work.servers.items():
        try:
            reachable[server_id] = work.listing(server_id)
        except Exception as exc:  # noqa: BLE001
            error(f"Franchisarr's playlists: {server.name} couldn't be reached ({type(exc).__name__})")
    _adopt_once(work, reachable)

    entries = session.exec(select(FranchisarrPlaylist)).all()
    live: list[FranchisarrPlaylist] = []
    for entry in entries:
        copies = _copies(session, entry)
        if entry.removed_at is None:
            gone = [s for s, c in copies.items() if s in reachable and c.server_playlist_id
                    and all(p.id != c.server_playlist_id for p in reachable[s])]
            if not gone:
                live.append(entry)
                continue
            logger.info("Playlist %r was deleted on %s; deleting it everywhere", playlist_title(entry.name),
                        ", ".join(work.servers[s].name for s in gone))
            entry.removed_at = _now()
            for server_id in gone:
                session.delete(copies.pop(server_id))
        _remove_copies(work, entry, copies, reachable, bump=bump, error=error)
    session.commit()
    if not live:
        return

    kinds = sorted({e.kind for e in live})
    index = {(s.kind, s.ref): s for s in playlist_bulk.sets(session, kinds, min_refs=1)}
    enabled = set(work.servers)
    defaults = default_servers(session)
    for entry in live:
        found = index.get((entry.kind, entry.ref))
        if progress:
            progress(playlist_title(entry.name))
        if found is None:
            continue              # its page is gone: leave the playlists as they are
        copies = _copies(session, entry)
        wanted = servers_of(session, entry, enabled, defaults) & set(reachable)
        # A server taken off this playlist (or off the defaults): delete it there.
        leaving = {s: c for s, c in copies.items() if s in reachable and s not in wanted}
        _remove_copies(work, entry, leaving, reachable, bump=bump, error=error, keep_entry=True)
        try:
            _build(work, entry, found.refs, found.art, wanted, bump=bump, error=error)
        except Exception as exc:  # noqa: BLE001 -- one playlist must not stop the rest
            logger.exception("Refreshing %r failed", entry.name)
            error(f"{playlist_title(entry.name)}: {type(exc).__name__}")
        session.commit()


def _remove_copies(work, entry: FranchisarrPlaylist, copies: dict[int, FranchisarrPlaylistCopy],  # noqa: ANN001
                   reachable: dict[int, list], *, bump: Callable = _quiet, error: Callable = _quiet,
                   keep_entry: bool = False) -> None:
    """Delete these copies where the server can be reached; the entry itself goes once none is
    left (unless `keep_entry`)."""
    session = work.session
    for server_id, copy in list(copies.items()):
        if server_id not in reachable:
            continue
        if copy.server_playlist_id and any(p.id == copy.server_playlist_id for p in reachable[server_id]):
            try:
                work.client(server_id).delete_playlist_id(copy.server_playlist_id)
                reachable[server_id][:] = [p for p in reachable[server_id] if p.id != copy.server_playlist_id]
                bump("deleted")
            except Exception as exc:  # noqa: BLE001
                error(f"{playlist_title(entry.name)}: couldn't delete it on {work.servers[server_id].name} "
                      f"({type(exc).__name__})")
                continue
        session.delete(copy)
        del copies[server_id]
    if not keep_entry and not copies:
        session.flush()        # the copies' DELETEs first: the entry's own would cascade to them
        session.delete(entry)


def _adopt_once(work, reachable: dict[int, list]) -> None:  # noqa: ANN001
    """The first sync after 0.42.0 (migration 0029 marks it due): every "(Franchisarr)" playlist
    already on a server joins the set, if its name is still a franchise, collection or director
    here. Once only -- after that, the set is what's been made, and a stray is never taken for
    one of ours."""
    from app.services import playlist_bulk
    from app.services.settings_service import SettingKey, get_bool_setting, set_setting

    session = work.session
    if not get_bool_setting(session, SettingKey.FRANCHISARR_PLAYLISTS_TO_ADOPT, False) or not reachable:
        return
    found: dict[str, dict[int, str]] = {}
    for server_id, listing in reachable.items():
        for p in listing:
            if p.video and p.title.endswith(SUFFIX):
                found.setdefault(p.title[: -len(SUFFIX)], {}).setdefault(server_id, p.id)
    if found:
        by_name: dict[str, playlist_bulk.PlaylistSet] = {}
        # Same order as the poster lookup: a franchise, then a collection, then a director.
        for item in reversed(playlist_bulk.sets(session, playlist_bulk.KINDS, min_refs=1)):
            by_name[item.name] = item
        for name, where in sorted(found.items()):
            item = by_name.get(name)
            if item is None or entry_for(session, item.kind, item.ref) is not None:
                continue
            entry = FranchisarrPlaylist(kind=item.kind, ref=item.ref, name=name)
            session.add(entry)
            session.flush()
            for server_id, playlist_id in where.items():
                session.add(FranchisarrPlaylistCopy(playlist_id=entry.id, server_id=server_id,
                                                    server_playlist_id=playlist_id))
            logger.info("Took %r into the Franchisarr playlist set", playlist_title(name))
    set_setting(session, SettingKey.FRANCHISARR_PLAYLISTS_TO_ADOPT, "false")
    session.commit()


def remove(session: Session, entry_id: int) -> str | None:
    """The tab's Remove: delete it on every server and drop it from the set. A copy on a server
    that's off waits until it's back. Returns an error to show, or None."""
    from app.services.playlist_sync import _Run

    entry = session.get(FranchisarrPlaylist, entry_id)
    if entry is None:
        return None
    work = _Run(session)
    problems: list[str] = []
    reachable = {}
    for server_id, server in work.servers.items():
        try:
            reachable[server_id] = work.listing(server_id)
        except Exception as exc:  # noqa: BLE001
            problems.append(f"{server.name} couldn't be reached ({type(exc).__name__})")
    entry.removed_at = _now()
    session.add(entry)
    _remove_copies(work, entry, _copies(session, entry), reachable, error=problems.append)
    session.commit()
    logger.info("Removed %r from the Franchisarr playlist set", playlist_title(entry.name))
    return "; ".join(problems) or None


def forget_server(session: Session, server_id: int | None) -> None:
    """Clean up deleted Franchisarr's playlists on one server (or every server, None): that's
    not someone deleting one playlist, so it mustn't spread. On one server, that server comes
    off the default servers and off any playlist's own list; on every server, the set is
    emptied."""
    from app.services.settings_service import SettingKey, set_setting

    entries = session.exec(select(FranchisarrPlaylist)).all()
    for entry in entries:
        copies = _copies(session, entry)
        for copy in copies.values():
            if server_id is None or copy.server_id == server_id:
                session.delete(copy)
        if server_id is None:
            session.delete(entry)
            continue
        chosen = _ids(entry.servers)
        if chosen is not None and server_id in chosen:
            entry.servers = json.dumps(sorted(chosen - {server_id}))
            session.add(entry)
    if server_id is not None:
        from app.services import media_server_service

        defaults = default_servers(session)
        if defaults is None:
            defaults = {s.id for s in media_server_service.list_servers(session)}
        set_setting(session, SettingKey.FRANCHISARR_PLAYLIST_SERVERS, json.dumps(sorted(defaults - {server_id})))
    session.commit()
