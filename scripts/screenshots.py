"""Regenerate the README screenshots from a synthetic library.

    python scripts/screenshots.py            # writes docs/screenshots/*.jpg

The data is seeded into a throwaway database from TMDb (needs TMDB_API_KEY): a fixed set of
well-known collections, shows and one director, with which titles the "library" owns pinned in
this file so the gaps come out the same every run. No media server, no *arr, no account of
anyone's -- nothing from the maintainer's library. The app is started in-process with uvicorn
and the pages captured with Playwright at 1600px wide.

CI runs this on every change under app/templates or app/static and commits the result, so the
README never shows a layout the app no longer has. Run it locally after a visual change to see
what CI will produce.
"""

from __future__ import annotations

import os
import pathlib
import sys
import tempfile
import threading
import time
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "screenshots"
PORT = 8765
PASSWORD = "screenshots-only"

# (file, path, viewport height)
PAGES = [
    ("collections", "/collections", 1000),
    ("collection-detail", "/collections/8864", 1150),
    ("franchises", "/franchises", 1000),
    ("franchise-star-wars", "/franchises/Q462", 1300),
    ("spinoffs", "/shows", 1000),
    ("upcoming", "/upcoming", 900),
    ("directors", "/directors", 1000),
    ("servers", "/media-servers", 700),
]


# Real, well-known sets, fetched from TMDb at run time so posters, dates and ratings are right.
# Which ones the "library" owns is fixed below, so the gaps are stable from run to run.
COLLECTIONS = {   # collection id -> positions owned (0-based), watched positions
    8864: ([0, 1, 2, 3, 4], [0, 1]),      # Final Destination: all five, Bloodlines missing
    8091: ([0, 1, 2], [0, 1]),            # Alien
    86311: ([0, 1], [0]),                 # Beverly Hills Cop
    10: ([0, 1, 2, 3, 4, 5, 6], [0]),     # Star Wars (film collection)
    1241: ([0, 1, 2, 3, 4], [0, 1, 2]),   # Harry Potter
    645: ([0, 2, 4, 6, 8], []),           # James Bond: every other one
    2344: ([0, 1], [0]),                  # The Matrix
    9485: ([0, 1, 2, 3], [0, 1]),         # The Fast and the Furious
    263: ([0, 1], [1]),                   # The Dark Knight
    328: ([0, 1, 2], [0, 1, 2]),          # Jurassic Park
    1575: ([0, 1, 2, 3], []),             # Rocky
    87359: ([0, 1, 2, 3, 4], [0]),        # Mission: Impossible
}
SHOWS = [  # (tmdb id, owned, spin-off of -> (source id, wikidata relation))
    (4614, True, None), (17610, False, (4614, "P2512")), (61387, False, None),
    (1396, True, None), (60059, False, (1396, "P155")),
    (73586, True, None), (157744, False, (73586, "P155")), (118357, False, (73586, "P155")),
    (1434, True, None), (1433, False, (1434, "P2512")),
    (1668, True, None), (1466, False, (1668, "P2512")),                  # Friends -> Joey
]
STAR_WARS = {"films_owned": [11, 1891, 1892, 140607], "films_missing": [1893, 1894, 1895, 12180, 330459],
             "shows_owned": [82856], "shows_missing": [114461, 92830, 83867]}
NOLAN = 525
NOLAN_OWNED = {155, 27205, 157336, 872585, 374720, 49026, 1124}


def seed(db_path: str) -> None:
    os.environ.update({"DB_PATH": db_path, "LOG_LEVEL": "WARNING", "BASE_URL": "/",
                       "ADMIN_USERNAME": "demo", "ADMIN_PASSWORD": PASSWORD})
    sys.path.insert(0, str(ROOT))
    from sqlmodel import Session

    from app.clients.tmdb_client import TmdbClient
    from app.db import get_engine, run_migrations
    from app.models import (
        DirectorFilm, Franchise, FranchiseMember, IncludedLibrary, LibraryItem, MediaServer,
        MovieDirector, SpinoffMapping, TmdbCollection, TmdbCollectionMovie, TmdbMovie, TmdbShow,
    )

    key = os.environ.get("TMDB_API_KEY")
    if not key:
        raise SystemExit("TMDB_API_KEY is needed to fetch the sample data")
    tmdb = TmdbClient(key)

    run_migrations()
    with Session(get_engine()) as s:
        server = MediaServer(name="Plex", kind="plex", url="http://plex:32400",
                             credential="screenshot-only-token-xxxxxxxx", machine_identifier="demo")
        s.add(server); s.commit(); s.refresh(server)
        s.add(IncludedLibrary(server_id=server.id, library_key="1", library_name="Movies", library_type="movie"))
        s.add(IncludedLibrary(server_id=server.id, library_key="2", library_name="TV Shows", library_type="show"))
        owned_films: set[int] = set()

        def own(tmdb_id, title, year, item_type="movie", watched=False):
            if item_type == "movie":
                if tmdb_id in owned_films:
                    return
                owned_films.add(tmdb_id)
            s.add(LibraryItem(server_id=server.id, library_key="1" if item_type == "movie" else "2",
                              item_key=f"{item_type[0]}{tmdb_id}", item_type=item_type, title=title,
                              year=year, tmdb_id=tmdb_id, match_source="guid", watched=watched))

        for cid, (owned_pos, watched_pos) in COLLECTIONS.items():
            c = tmdb.get_collection(cid)
            s.add(TmdbCollection(tmdb_collection_id=cid, name=c.name, poster_path=c.poster_path,
                                 backdrop_path=c.backdrop_path))
            for pos, m in enumerate(c.movies):
                year = int(m.release_date[:4]) if m.release_date else None
                s.add(TmdbCollectionMovie(collection_id=cid, tmdb_movie_id=m.tmdb_id, title=m.title,
                                          release_year=year, release_date=m.release_date, poster_path=m.poster_path,
                                          vote_average=m.vote_average, vote_count=m.vote_count, position=pos))
                if pos in owned_pos:
                    s.add(TmdbMovie(tmdb_id=m.tmdb_id, title=m.title, release_year=year, collection_id=cid))
                    own(m.tmdb_id, m.title, year, watched=pos in watched_pos)
            print("collection", c.name, file=sys.stderr)

        for tid, owned, spin in SHOWS:
            sh = tmdb.get_show(tid)
            year = int(sh.first_air_date[:4]) if sh.first_air_date else None
            s.add(TmdbShow(tmdb_id=tid, name=sh.name, first_air_year=year, poster_path=sh.poster_path,
                           imdb_id=sh.imdb_id, tvdb_id=sh.tvdb_id, network=sh.network))
            if owned:
                own(tid, sh.name, year, item_type="show", watched=True)
            if spin:
                s.add(SpinoffMapping(source_show_tmdb_id=spin[0], spinoff_show_tmdb_id=tid, source="wikidata",
                                     confidence="confirmed", origin_ref=spin[1]))
        # one mapping the "user" added by hand, so that section of the page has an entry
        s.add(SpinoffMapping(source_show_tmdb_id=4614, spinoff_show_tmdb_id=61387, source="local",
                             confidence="confirmed", origin_ref="P2512"))

        s.add(Franchise(wikidata_id="Q462", name="Star Wars", kind="media franchise"))
        for fid in STAR_WARS["films_owned"] + STAR_WARS["films_missing"]:
            m = tmdb.get_movie(fid)
            year = int(m.release_date[:4]) if m.release_date else None
            s.add(FranchiseMember(franchise_id="Q462", item_type="movie", tmdb_id=fid, title=m.title, year=year,
                                  poster_path=m.poster_path))
            if fid in STAR_WARS["films_owned"]:
                if not s.get(TmdbMovie, fid):
                    s.add(TmdbMovie(tmdb_id=fid, title=m.title, release_year=year))
                own(fid, m.title, year, watched=True)
        for sid in STAR_WARS["shows_owned"] + STAR_WARS["shows_missing"]:
            sh = tmdb.get_show(sid)
            year = int(sh.first_air_date[:4]) if sh.first_air_date else None
            s.add(FranchiseMember(franchise_id="Q462", item_type="show", tmdb_id=sid, title=sh.name, year=year,
                                  poster_path=sh.poster_path))
            if not s.get(TmdbShow, sid):
                s.add(TmdbShow(tmdb_id=sid, name=sh.name, first_air_year=year, poster_path=sh.poster_path,
                               imdb_id=sh.imdb_id, tvdb_id=sh.tvdb_id))
            if sid in STAR_WARS["shows_owned"]:
                own(sid, sh.name, year, item_type="show")

        person = tmdb.get_person(NOLAN)
        for f in tmdb.get_directed_films(NOLAN):
            s.add(DirectorFilm(person_id=NOLAN, tmdb_movie_id=f.tmdb_id, title=f.title, release_date=f.release_date,
                               poster_path=f.poster_path, vote_average=f.vote_average, vote_count=f.vote_count,
                               is_documentary=f.is_documentary))
            if f.tmdb_id in NOLAN_OWNED:
                year = int(f.release_date[:4]) if f.release_date else None
                s.add(MovieDirector(tmdb_movie_id=f.tmdb_id, person_id=NOLAN, name=person.name,
                                    profile_path=person.profile_path))
                if not s.get(TmdbMovie, f.tmdb_id):
                    s.add(TmdbMovie(tmdb_id=f.tmdb_id, title=f.title, release_year=year))
                own(f.tmdb_id, f.title, year, watched=True)
        s.commit()

        from app.auth.local_admin import create_local_admin
        from app.services.settings_service import SettingKey, set_setting

        create_local_admin(s, "demo", PASSWORD)
        set_setting(s, SettingKey.MIN_DIRECTOR_FILMS, "3")
        s.commit()


def serve() -> threading.Thread:
    import uvicorn

    from app.main import app

    config = uvicorn.Config(app, host="127.0.0.1", port=PORT, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    for _ in range(50):
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{PORT}/health", timeout=1)
            return thread
        except Exception:
            time.sleep(0.2)
    raise SystemExit("app did not start")


def capture(out: pathlib.Path) -> None:
    from playwright.sync_api import sync_playwright

    out.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=os.environ.get("PLAYWRIGHT_CHROMIUM") or None)
        ctx = browser.new_context(viewport={"width": 1600, "height": 1000}, device_scale_factor=1.25,
                                  color_scheme="dark")
        page = ctx.new_page()
        page.goto(f"http://127.0.0.1:{PORT}/login")
        page.screenshot(path=str(out / "login.jpg"), type="jpeg", quality=82)
        page.fill("input[name=username]", "demo")
        page.fill("input[name=password]", PASSWORD)
        page.click("button[type=submit]")
        page.wait_for_load_state("networkidle")
        for name, path, height in PAGES:
            page.set_viewport_size({"width": 1600, "height": height})
            page.goto(f"http://127.0.0.1:{PORT}{path}")
            try:
                page.wait_for_load_state("networkidle", timeout=20000)
            except Exception:
                pass
            page.wait_for_timeout(800)
            page.screenshot(path=str(out / f"{name}.jpg"), type="jpeg", quality=82)
            print(name, page.title(), file=sys.stderr)
        browser.close()


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        seed(os.path.join(tmp, "screenshots.db"))
        serve()
        capture(OUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
