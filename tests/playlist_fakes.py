"""An in-memory media server's playlists, as franchisarr_playlists and edit_in_place see them
through a client: playlists are lists of (entry id, item key), items are their own keys."""

from __future__ import annotations

from datetime import date

from app.clients.media_server import PlaylistEntry, PlaylistInfo, PlaylistItemRef


class FakeMediaServer:
    def __init__(self, films: dict[str, date | None] | None = None,
                 episodes: dict[str, list[tuple[int, int, str, date | None]]] | None = None) -> None:
        #: film key -> release date; show key -> [(season, episode, key, aired)]
        self.films = dict(films or {})
        self.episodes = dict(episodes or {})
        self.playlists: dict[str, dict] = {}
        self.log: list[tuple] = []
        self.posters: dict[str, bytes] = {}
        self.down = False
        self._ids = 100
        self._entries = 1000

    # ---- setting up

    def _entry(self) -> str:
        self._entries += 1
        return f"e{self._entries}"

    def add(self, pid: str, title: str, keys: list[str]) -> None:
        self.playlists[pid] = {"title": title, "entries": [(self._entry(), k) for k in keys]}

    def keys(self, pid: str) -> list[str]:
        return [k for _, k in self.playlists[pid]["entries"]]

    def titled(self, title: str) -> list[str]:
        return [pid for pid, p in self.playlists.items() if p["title"] == title]

    # ---- the client

    def _check(self) -> None:
        if self.down:
            raise ConnectionError("down")

    def list_playlists(self) -> list[PlaylistInfo]:
        self._check()
        return [PlaylistInfo(pid, p["title"], count=len(p["entries"])) for pid, p in self.playlists.items()]

    def playlist_entries(self, films: list[str], shows: list[str]) -> list[PlaylistEntry]:
        self._check()
        self.log.append(("entries", tuple(films), tuple(shows)))
        out = [PlaylistEntry(raw=k, aired=self.films[k], key=k) for k in films if k in self.films]
        for show in shows:
            out += [PlaylistEntry(raw=k, aired=aired, show_key=show, season=s, episode=e, key=k)
                    for s, e, k, aired in self.episodes.get(show, [])]
        return out

    def playlist_items(self, pid: str) -> list[PlaylistItemRef]:
        self._check()
        return [PlaylistItemRef("movie", key, key, entry_id=entry) for entry, key in self.playlists[pid]["entries"]]

    def create_playlist(self, title: str, raws: list) -> str:  # noqa: ANN001
        self._check()
        self._ids += 1
        pid = f"p{self._ids}"
        self.add(pid, title, [str(r) for r in raws])
        self.log.append(("create", title))
        return pid

    def delete_playlist_id(self, pid: str) -> None:
        self._check()
        self.playlists.pop(pid, None)
        self.log.append(("delete", pid))

    def remove_playlist_entries(self, pid: str, entry_ids: list[str]) -> None:
        self.playlists[pid]["entries"] = [e for e in self.playlists[pid]["entries"] if e[0] not in entry_ids]
        self.log.append(("remove", pid, len(entry_ids)))

    def append_to_playlist(self, pid: str, raws: list) -> None:  # noqa: ANN001
        self.playlists[pid]["entries"] += [(self._entry(), str(r)) for r in raws]
        self.log.append(("append", pid, len(raws)))

    def move_playlist_entry(self, pid: str, entry_id: str, index: int, after: str | None) -> None:
        entries = self.playlists[pid]["entries"]
        entry = next(e for e in entries if e[0] == entry_id)
        entries.remove(entry)
        # Plex places after `after`; Jellyfin at `index`. Both must agree.
        where = 0 if after is None else next(i for i, e in enumerate(entries) if e[0] == after) + 1
        assert where == index, "after and index point at the same place"
        entries.insert(where, entry)
        self.log.append(("move", pid))

    def set_playlist_poster_id(self, pid: str, image: bytes) -> bool:
        self.posters[pid] = image
        return True

    def edits(self) -> list[str]:
        """What was done, without the reads."""
        return [op[0] for op in self.log if op[0] != "entries"]
