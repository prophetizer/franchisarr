"""How Franchisarr holds up on a library much bigger than the developer's.

    python scripts/loadtest.py --films 20000 --shows 2000

Every external client is a fake that answers instantly, so what's measured is ours: the matcher,
the database, the read-time services and the page renders. Numbers from the real 3,400-film
library are the baseline (docs/DESIGN.md; CHANGELOG); this is for the person who shows up with
20,000 films the week after the announcement. Nothing here touches the network.

The synthetic library is regular on purpose, so the shape is known: every 6 films form a
collection, every third collection is missing two films (one of them undated), every director made
~13 films, every fourth show has a spin-off, and 300 franchises hold ten titles
each. That is a heavier gap load per film than a real library -- 3,400 real films gave 108
collections with gaps; this gives ~1,100 for 20,000 -- which is the point.
"""

from __future__ import annotations

import argparse
import os
import pathlib
import sys
import tempfile
import time
from contextlib import contextmanager
from datetime import date, timedelta

ROOT = pathlib.Path(__file__).resolve().parent.parent
PASSWORD = "loadtest-only"


@contextmanager
def timed(label: str):
    start = time.perf_counter()
    yield
    print(f"{label:<44} {time.perf_counter() - start:8.2f}s", flush=True)


# ------------------------------------------------------------------ fakes

def build_fakes(n_films: int, n_shows: int):
    from app.clients.media_server import MediaLibrary, MediaMovie, MediaShow
    from app.clients.plex_guid import ExternalIds
    from app.clients.tmdb_client import (
        TmdbCollectionDetails, TmdbDirectedFilm, TmdbMovieDetails, TmdbMovieSummary, TmdbPerson,
        TmdbShowSummary,
    )
    from app.clients.wikidata_client import (
        CrossMediaRelation, FranchiseGroup, FranchiseTitle, SpinoffRelation,
    )

    MISSING_BASE = 10_000_000       # ids of films the library does not own
    SPINOFF_BASE = 5_000_000
    DIRECTORS = max(1, n_films // 13)   # every director made ~13 films, as the real top ones do
    FRANCHISES = 300
    today = date(2026, 9, 22)

    def collection_of(film_id: int) -> int:
        return (film_id - 1) // 6 + 1

    def films_in(cid: int) -> list[int]:
        owned = [cid * 6 - 5 + i for i in range(6) if cid * 6 - 5 + i <= n_films]
        missing = [MISSING_BASE + cid * 2, MISSING_BASE + cid * 2 + 1] if cid % 3 == 0 else []
        return owned + missing

    def release_for(film_id: int) -> str | None:
        if film_id >= MISSING_BASE:
            # The first missing film of a collection is released (a real gap); the second is
            # announced -- dated or not -- and lands on Upcoming, as the app's own rule says.
            if film_id % 2 == 0:
                return (date(1990, 1, 1) + timedelta(days=film_id % 10000)).isoformat()
            if film_id % 4 == 1:
                return None
            return (today + timedelta(days=30 + film_id % 400)).isoformat()
        return (date(1970, 1, 1) + timedelta(days=(film_id * 37) % 20000)).isoformat()

    def summary(film_id: int) -> TmdbMovieSummary:
        return TmdbMovieSummary(tmdb_id=film_id, title=f"Film {film_id}", release_date=release_for(film_id),
                                poster_path=f"/p{film_id}.jpg", vote_average=5.0 + film_id % 50 / 10,
                                vote_count=100 + film_id % 5000)

    class FakeServer:
        kind = "plex"

        def test_connection(self):
            return "ok"

        def list_libraries(self):
            return [MediaLibrary(key="1", title="Movies", library_type="movie", agent="tv.plex.agents.movie"),
                    MediaLibrary(key="2", title="TV Shows", library_type="show", agent="tv.plex.agents.series")]

        def iter_movies(self, library_key):
            for i in range(1, n_films + 1):
                yield MediaMovie(item_key=f"m{i}", title=f"Film {i}", year=int(release_for(i)[:4]),
                                 external_ids=ExternalIds(tmdb_id=i), guids=(f"tmdb://{i}",), watched=i % 2 == 0)

        def iter_shows(self, library_key):
            for i in range(1, n_shows + 1):
                yield MediaShow(item_key=f"s{i}", title=f"Show {i}", year=1990 + i % 35,
                                external_ids=ExternalIds(tmdb_id=i, tvdb_id=100000 + i), guids=(f"tmdb://{i}",),
                                watched=i % 3 == 0)

    class FakeTmdb:
        calls = 0

        def _hit(self):
            FakeTmdb.calls += 1

        def validate_key(self):
            pass

        def get_movie(self, tmdb_id):
            self._hit()
            cid = collection_of(tmdb_id) if tmdb_id < MISSING_BASE else (tmdb_id - MISSING_BASE) // 2
            return TmdbMovieDetails(tmdb_id=tmdb_id, title=f"Film {tmdb_id}", release_date=release_for(tmdb_id),
                                    collection_id=cid, collection_name=f"Collection {cid}",
                                    poster_path=f"/p{tmdb_id}.jpg")

        def get_collection(self, collection_id):
            self._hit()
            return TmdbCollectionDetails(tmdb_collection_id=collection_id, name=f"Collection {collection_id}",
                                         poster_path=f"/c{collection_id}.jpg",
                                         movies=tuple(summary(f) for f in films_in(collection_id)))

        def get_movie_directors(self, tmdb_id):
            self._hit()
            p = (tmdb_id - 1) % DIRECTORS + 1
            return [TmdbPerson(person_id=p, name=f"Director {p}", profile_path=f"/d{p}.jpg")]

        def get_person(self, person_id):
            self._hit()
            return TmdbPerson(person_id=person_id, name=f"Director {person_id}", profile_path=f"/d{person_id}.jpg")

        def get_directed_films(self, person_id):
            self._hit()
            ids = list(range(person_id, n_films + 1, DIRECTORS)) + [MISSING_BASE + 900_000 + person_id]
            return [TmdbDirectedFilm(tmdb_id=f, title=f"Film {f}", release_date=release_for(f),
                                     poster_path=f"/p{f}.jpg", vote_average=6.5, vote_count=300) for f in ids]

        def get_show(self, tmdb_id):
            self._hit()
            return TmdbShowSummary(tmdb_id=tmdb_id, name=f"Show {tmdb_id}", first_air_date="2005-01-01",
                                   network="Net", poster_path=f"/s{tmdb_id}.jpg", tvdb_id=100000 + tmdb_id)

        def find_by_external_id(self, external_id, source):
            self._hit()
            return None

        def find_show_by_external_id(self, external_id, source):
            self._hit()
            return None

        def search_movies(self, title, year=None):
            self._hit()
            return []

        def search_shows(self, name, year=None):
            self._hit()
            return []

    class FakeWikidata:
        def spinoffs_for(self, tmdb_ids):
            return [SpinoffRelation(source_tmdb_id=s, spinoff_tmdb_id=SPINOFF_BASE + s, spinoff_name=f"Show {s}: Spin-off",
                                    relation="P2512", wikidata_id=f"Q{s}") for s in tmdb_ids if s % 4 == 0]

        def cross_media_for(self, *, show_ids, movie_ids):
            return [CrossMediaRelation(source_type="show", source_tmdb_id=s, target_type="movie",
                                       target_tmdb_id=MISSING_BASE + 800_000 + s, target_name=f"Show {s}: The Movie",
                                       relation="P4969") for s in show_ids if s % 25 == 0]

        def franchises_for(self, *, show_ids, movie_ids):
            groups = [FranchiseGroup(wikidata_id=f"Q{100000 + g}", name=f"Franchise {g}", kind="media franchise")
                      for g in range(1, FRANCHISES + 1)]
            membership: dict[tuple[str, int], set[str]] = {}
            for f in movie_ids:
                if f % 40 == 0:
                    membership[("movie", f)] = {f"Q{100000 + (f // 40 - 1) % FRANCHISES + 1}"}
            for s in show_ids:
                if s % 8 == 0:
                    membership[("show", s)] = {f"Q{100000 + (s // 8 - 1) % FRANCHISES + 1}"}
            return groups, membership

        def franchise_titles(self, franchise_id):
            g = int(franchise_id[1:]) - 100000
            titles = []
            for k in range(10):
                f = g * 40 + k * FRANCHISES * 40
                if f <= n_films:
                    titles.append(FranchiseTitle(franchise_id=franchise_id, item_type="movie", tmdb_id=f,
                                                 name=f"Film {f}", kind="film"))
            titles.append(FranchiseTitle(franchise_id=franchise_id, item_type="movie",
                                         tmdb_id=MISSING_BASE + 700_000 + g, name=f"Franchise {g}: Lost Film", kind="film"))
            titles.append(FranchiseTitle(franchise_id=franchise_id, item_type="show",
                                         tmdb_id=SPINOFF_BASE + 700_000 + g, name=f"Franchise {g}: The Series", kind="television series"))
            return titles

    return FakeServer, FakeTmdb, FakeWikidata


# ------------------------------------------------------------------ run

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--films", type=int, default=20000)
    parser.add_argument("--shows", type=int, default=2000)
    parser.add_argument("--keep", help="write the database here instead of a temp dir")
    args = parser.parse_args()

    workdir = args.keep or tempfile.mkdtemp(prefix="franchisarr-loadtest-")
    db_path = os.path.join(workdir, "loadtest.db")
    os.environ.update({"DB_PATH": db_path, "LOG_LEVEL": "WARNING", "BASE_URL": "/",
                       "ADMIN_USERNAME": "demo", "ADMIN_PASSWORD": PASSWORD})
    sys.path.insert(0, str(ROOT))

    from fastapi.testclient import TestClient
    from sqlmodel import Session

    from app.auth.api_keys import generate_api_key
    from app.auth.local_admin import create_local_admin
    from app.db import get_engine, run_migrations
    from app.models import MediaServer
    from app.services import scan_job, scan_service, settings_service
    from app.services.settings_service import SettingKey

    FakeServer, FakeTmdb, FakeWikidata = build_fakes(args.films, args.shows)

    run_migrations()
    with Session(get_engine()) as s:
        server = MediaServer(name="Plex", kind="plex", url="http://plex:32400",
                             credential="loadtest-only-token-xxxxxxxx", machine_identifier="loadtest")
        s.add(server); s.commit(); s.refresh(server)
        from app.models import IncludedLibrary
        s.add(IncludedLibrary(server_id=server.id, library_key="1", library_name="Movies", library_type="movie"))
        s.add(IncludedLibrary(server_id=server.id, library_key="2", library_name="TV Shows", library_type="show"))
        settings_service.set_setting(s, SettingKey.TMDB_API_KEY, "loadtest-only-key-xxxxxxxxxx")
        user = create_local_admin(s, "demo", PASSWORD)
        api_key = generate_api_key(s, user)
        s.commit()
        server_id = server.id

    # Swap the real clients for the fakes at the one place the job builds them.
    def fake_clients(session):
        server = session.get(MediaServer, server_id)
        return [scan_service.ScanSource(server, FakeServer())], FakeTmdb(), None, []

    scan_job._clients = fake_clients
    scan_job.WikidataClient = FakeWikidata

    print(f"library: {args.films:,} films, {args.shows:,} shows  (db: {db_path})")
    phases: list[tuple[str, float]] = []
    last = [time.perf_counter(), ""]

    def progress(phase, processed, total):
        now = time.perf_counter()
        if phase != last[1]:
            if last[1]:
                phases.append((last[1], now - last[0]))
            last[0], last[1] = now, phase

    with Session(get_engine()) as s:
        with timed("scan 1 (first run: library + collections)"):
            r = scan_job.run(s, notify=False, progress=progress)
        assert not r.errors, r.errors
        phases.append((last[1], time.perf_counter() - last[0])); last[1] = ""
        with timed("scan 2 (enrichment: directors, spin-offs, franchises)"):
            r = scan_job.run(s, notify=False, progress=progress)
        assert not r.errors, r.errors
        phases.append((last[1], time.perf_counter() - last[0]))
        with timed("scan 3 (steady state, everything cached)"):
            r = scan_job.run(s, notify=False)
        assert not r.errors, r.errors
    print(f"  tmdb calls (fake): {FakeTmdb.calls:,}")
    for phase, secs in phases:
        if secs > 1:
            print(f"    {phase:<40} {secs:7.1f}s")

    from app.main import app

    with TestClient(app) as client:
        client.post("/login", data={"username": "demo", "password": PASSWORD})
        pages = ["/", "/collections", "/collections?filter=started", "/collections/3", "/franchises",
                 "/franchises/Q100001", "/shows", "/upcoming", "/directors", "/directors/1", "/settings",
                 "/activity", "/libraries", "/settings/diagnostics",
                 f"/api/lists/collections.json?api_key={api_key}", f"/api/lists/shows.json?api_key={api_key}",
                 f"/api/lists/upcoming.ics?api_key={api_key}", "/api/collections/gaps", "/api/spinoffs"]
        print("\npages (first hit / second hit):")
        for path in pages:
            label = path.split("?api_key")[0]
            t0 = time.perf_counter(); r1 = client.get(path); t1 = time.perf_counter(); r2 = client.get(path); t2 = time.perf_counter()
            size = len(r1.content) // 1024
            flag = "" if r1.status_code == 200 else f"  <-- HTTP {r1.status_code}"
            print(f"  {label:<38} {t1 - t0:7.2f}s {t2 - t1:7.2f}s  {size:6,} KB{flag}")

    if not args.keep:
        import shutil
        shutil.rmtree(workdir, ignore_errors=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
