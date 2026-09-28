"""Search everything Franchisarr knows: collections, franchises, directors, films and shows.

Local only -- no TMDb call per keystroke. A film is found wherever the app has met it: in a
cached collection, a franchise, a director's filmography, or the library itself; one result per
film, carrying every page it belongs to. Its status is worked out the way the lists do it: in
the library (on a server that's switched on), already in Radarr/Sonarr or requested in Seerr,
hidden by this person, not out yet, or missing.

Matching ignores case, accents and punctuation, so "spiderman", "spider man" and "Spider-Man"
all find the same film, and "amelie" finds "Amélie". Titles are read as column tuples, never
ORM rows (scripts/loadtest.py: at 20,000 films rows cost ten times as much).
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date
from functools import lru_cache

from sqlmodel import Session, col, select

from app.models import (
    CollectionExclude, DirectorFilm, DismissedItem, Franchise, FranchiseMember, ItemType, LibraryItem,
    MovieDirector, SpinoffMapping, TmdbCollection, TmdbCollectionMovie, TmdbMovie, TmdbShow,
)

MIN_QUERY = 2
#: Per group. A search is for finding one thing; past this, typing more is quicker than scrolling.
LIMITS = {"collections": 8, "franchises": 8, "directors": 8, "films": 40, "shows": 24}

_SEPARATORS = re.compile(r"[\W_]+", re.UNICODE)


@lru_cache(maxsize=200_000)
def normalise(text: str) -> str:
    """Casefolded, accents stripped, everything but letters and digits removed. Cached: the same
    titles are compared on every keystroke, and a library's worth fits comfortably."""
    decomposed = unicodedata.normalize("NFKD", text or "")
    plain = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return _SEPARATORS.sub("", plain.casefold())


@dataclass
class Link:
    label: str
    path: str


@dataclass
class TitleResult:
    item_type: str
    tmdb_id: int
    title: str
    year: int | None = None
    poster_path: str | None = None
    #: "owned", "in_arr", "dismissed", "upcoming" or "missing".
    status: str = "missing"
    servers: tuple[str, ...] = ()
    links: list[Link] = field(default_factory=list)

    @property
    def poster(self) -> str | None:
        from app.services.artwork import SMALL_CARD_SIZE, poster_url

        return poster_url(self.poster_path, SMALL_CARD_SIZE)

    @property
    def can_add(self) -> bool:
        return self.status in ("missing", "upcoming", "dismissed")


@dataclass
class GroupResult:
    """A collection, franchise or director."""

    kind: str
    name: str
    path: str
    detail: str = ""
    image_path: str | None = None

    @property
    def image(self) -> str | None:
        from app.services.artwork import SMALL_CARD_SIZE, poster_url, profile_url

        if self.kind == "director":
            return profile_url(self.image_path)
        return poster_url(self.image_path, SMALL_CARD_SIZE)


@dataclass
class SearchResults:
    query: str
    collections: list[GroupResult] = field(default_factory=list)
    franchises: list[GroupResult] = field(default_factory=list)
    directors: list[GroupResult] = field(default_factory=list)
    films: list[TitleResult] = field(default_factory=list)
    shows: list[TitleResult] = field(default_factory=list)
    #: How many each group had before LIMITS cut it.
    totals: dict[str, int] = field(default_factory=dict)

    @property
    def empty(self) -> bool:
        return not any((self.collections, self.franchises, self.directors, self.films, self.shows))

    @property
    def too_short(self) -> bool:
        return len(normalise(self.query)) < MIN_QUERY


def _rank(name: str, needle: str) -> tuple[int, str]:
    """Titles starting with the query first, then the rest, each alphabetically."""
    key = normalise(name)
    return (0 if key.startswith(needle) else 1, name.casefold())


def _cut(results: SearchResults, group: str, items: list) -> list:
    results.totals[group] = len(items)
    return items[:LIMITS[group]]


def search(session: Session, query: str, user_id: int | None, *, today: date | None = None) -> SearchResults:
    from app.services import director_service, movie_gap_service, tv_spinoff_service
    from app.services.ownership_service import owned_details

    results = SearchResults(query=query.strip())
    needle = normalise(results.query)
    if len(needle) < MIN_QUERY:
        return results
    today = today or date.today()

    def hit(text: str | None) -> bool:
        return bool(text) and needle in normalise(text)

    # ------------------------------------------------------------------ what's owned, and where
    owned_films = movie_gap_service.owned_tmdb_ids(session)
    owned_shows = tv_spinoff_service.owned_show_ids(session)
    film_details = owned_details(session, ItemType.MOVIE.value)
    show_details = owned_details(session, ItemType.SHOW.value)
    in_radarr = movie_gap_service.radarr_known_ids(session)
    in_sonarr = tv_spinoff_service.sonarr_known_ids(session)
    dismissed = set(session.exec(
        select(DismissedItem.item_type, DismissedItem.tmdb_id).where(col(DismissedItem.user_id) == user_id)
    ).all()) if user_id is not None else set()

    # ------------------------------------------------------------------ collections
    collection_names = dict(session.exec(select(TmdbCollection.tmdb_collection_id, TmdbCollection.name)).all())
    collection_posters = dict(session.exec(select(TmdbCollection.tmdb_collection_id, TmdbCollection.poster_path)).all())
    excluded = set(session.exec(select(CollectionExclude.tmdb_collection_id, CollectionExclude.tmdb_movie_id)).all())
    members: dict[int, list[int]] = {}
    film_rows = session.exec(select(
        TmdbCollectionMovie.collection_id, TmdbCollectionMovie.tmdb_movie_id, TmdbCollectionMovie.title,
        TmdbCollectionMovie.release_year, TmdbCollectionMovie.release_date, TmdbCollectionMovie.poster_path,
    )).all()
    for cid, tmdb_id, *_ in film_rows:
        if (cid, tmdb_id) not in excluded:
            members.setdefault(cid, []).append(tmdb_id)
    collections = []
    for cid, name in collection_names.items():
        ids = members.get(cid, [])
        owned = sum(1 for i in ids if i in owned_films)
        if owned and hit(name):
            collections.append(GroupResult("collection", name, f"/collections/{cid}",
                                           f"{owned} of {len(ids)} owned", collection_posters.get(cid)))
    collections.sort(key=lambda g: _rank(g.name, needle))
    results.collections = _cut(results, "collections", collections)

    # ------------------------------------------------------------------ franchises
    franchise_names = dict(session.exec(select(Franchise.wikidata_id, Franchise.name)).all())
    franchise_rows = session.exec(select(
        FranchiseMember.franchise_id, FranchiseMember.item_type, FranchiseMember.tmdb_id,
        FranchiseMember.title, FranchiseMember.year, FranchiseMember.poster_path,
    )).all()
    franchise_counts: dict[str, list[int]] = {}
    # The card's picture, as the Franchises page chooses it: the collection poster of an owned
    # film, else any member's own poster.
    film_collection = dict(session.exec(
        select(TmdbMovie.tmdb_id, TmdbMovie.collection_id).where(col(TmdbMovie.collection_id).is_not(None))).all())
    franchise_posters: dict[str, str] = {}
    member_posters: dict[str, str] = {}
    for qid, item_type, tmdb_id, _title, _year, poster in franchise_rows:
        is_film = item_type == ItemType.MOVIE.value
        owned = tmdb_id in (owned_films if is_film else owned_shows)
        counts = franchise_counts.setdefault(qid, [0, 0])
        counts[0 if owned else 1] += 1
        if owned and is_film and qid not in franchise_posters and collection_posters.get(film_collection.get(tmdb_id)):
            franchise_posters[qid] = collection_posters[film_collection[tmdb_id]]
        if poster and qid not in member_posters:
            member_posters[qid] = poster
    franchises = [
        GroupResult("franchise", name, f"/franchises/{qid}",
                    f"{franchise_counts.get(qid, [0, 0])[0]} owned, {franchise_counts.get(qid, [0, 0])[1]} missing",
                    franchise_posters.get(qid) or member_posters.get(qid))
        for qid, name in franchise_names.items() if hit(name)
    ]
    franchises.sort(key=lambda g: _rank(g.name, needle))
    results.franchises = _cut(results, "franchises", franchises)

    # ------------------------------------------------------------------ directors (with a page)
    floor = director_service.min_director_films(session)
    director_names: dict[int, str] = {}
    director_photos: dict[int, str | None] = {}
    director_owned: dict[int, set[int]] = {}
    for tmdb_id, person_id, name, profile in session.exec(select(
            MovieDirector.tmdb_movie_id, MovieDirector.person_id, MovieDirector.name,
            MovieDirector.profile_path).where(col(MovieDirector.person_id) != 0)):
        if tmdb_id in owned_films:
            director_owned.setdefault(person_id, set()).add(tmdb_id)
            director_names[person_id] = name
            if profile:
                director_photos[person_id] = profile
    with_page = {pid for pid, films in director_owned.items() if len(films) >= floor}
    directors = [
        GroupResult("director", director_names[pid], f"/directors/{pid}",
                    f"{len(director_owned[pid])} films owned", director_photos.get(pid))
        for pid in with_page if hit(director_names[pid])
    ]
    directors.sort(key=lambda g: _rank(g.name, needle))
    results.directors = _cut(results, "directors", directors)

    # ------------------------------------------------------------------ films, from everywhere
    films: dict[int, TitleResult] = {}

    def film(tmdb_id: int, title: str, year: int | None, poster: str | None) -> TitleResult:
        found = films.get(tmdb_id)
        if found is None:
            found = films[tmdb_id] = TitleResult(ItemType.MOVIE.value, tmdb_id, title, year, poster)
        found.year = found.year or year
        found.poster_path = found.poster_path or poster
        return found

    release_dates: dict[int, str | None] = {}
    for cid, tmdb_id, title, year, release_date, poster in film_rows:
        if (cid, tmdb_id) in excluded or not hit(title):
            continue
        result = film(tmdb_id, title, year, poster)
        release_dates.setdefault(tmdb_id, release_date)
        if cid in collection_names and any(i in owned_films for i in members.get(cid, [])):
            result.links.append(Link(collection_names[cid], f"/collections/{cid}"))
    for qid, item_type, tmdb_id, title, year, poster in franchise_rows:
        if item_type == ItemType.MOVIE.value and hit(title):
            film(tmdb_id, title, year, poster).links.append(Link(franchise_names.get(qid, qid), f"/franchises/{qid}"))
    for person_id, tmdb_id, title, release_date, poster in session.exec(select(
            DirectorFilm.person_id, DirectorFilm.tmdb_movie_id, DirectorFilm.title,
            DirectorFilm.release_date, DirectorFilm.poster_path).where(col(DirectorFilm.person_id).in_(with_page))):
        if not hit(title):
            continue
        year = int(release_date[:4]) if release_date and release_date[:4].isdigit() else None
        result = film(tmdb_id, title, year, poster)
        release_dates.setdefault(tmdb_id, release_date)
        result.links.append(Link(director_names[person_id], f"/directors/{person_id}"))
    for tmdb_id, title, year in session.exec(select(LibraryItem.tmdb_id, LibraryItem.title, LibraryItem.year).where(
            col(LibraryItem.item_type) == ItemType.MOVIE.value, col(LibraryItem.tmdb_id).is_not(None))):
        if tmdb_id in owned_films and hit(title):
            film(tmdb_id, title, year, None)

    for result in films.values():
        result.status = _status(ItemType.MOVIE.value, result.tmdb_id, owned_films, in_radarr, dismissed,
                                release_dates.get(result.tmdb_id), result.year, today)
        if result.status == "owned" and result.tmdb_id in film_details:
            result.servers = film_details[result.tmdb_id].servers
        result.links = _unique(result.links)
    ordered = sorted(films.values(), key=lambda r: (*_rank(r.title, needle), r.year or 0))
    results.films = _cut(results, "films", ordered)

    # ------------------------------------------------------------------ shows
    shows: dict[int, TitleResult] = {}

    def show(tmdb_id: int, title: str, year: int | None, poster: str | None) -> TitleResult:
        found = shows.get(tmdb_id)
        if found is None:
            found = shows[tmdb_id] = TitleResult(ItemType.SHOW.value, tmdb_id, title, year, poster)
        found.poster_path = found.poster_path or poster
        return found

    show_cache = {tid: (name, year, poster) for tid, name, year, poster in session.exec(
        select(TmdbShow.tmdb_id, TmdbShow.name, TmdbShow.first_air_year, TmdbShow.poster_path))}
    for tmdb_id, title, year in session.exec(select(LibraryItem.tmdb_id, LibraryItem.title, LibraryItem.year).where(
            col(LibraryItem.item_type) == ItemType.SHOW.value, col(LibraryItem.tmdb_id).is_not(None))):
        if tmdb_id in owned_shows and hit(title):
            cached = show_cache.get(tmdb_id)
            show(tmdb_id, title, year, cached[2] if cached else None)
    for qid, item_type, tmdb_id, title, year, poster in franchise_rows:
        if item_type == ItemType.SHOW.value and hit(title):
            show(tmdb_id, title, year, poster).links.append(Link(franchise_names.get(qid, qid), f"/franchises/{qid}"))
    for spinoff_id in session.exec(select(SpinoffMapping.spinoff_show_tmdb_id).distinct()).all():
        cached = show_cache.get(spinoff_id)
        if cached and hit(cached[0]):
            show(spinoff_id, cached[0], cached[1], cached[2]).links.append(Link("Spin-offs", "/shows"))

    for result in shows.values():
        result.status = _status(ItemType.SHOW.value, result.tmdb_id, owned_shows, in_sonarr, dismissed,
                                None, None, today)
        if result.status == "owned" and result.tmdb_id in show_details:
            result.servers = show_details[result.tmdb_id].servers
        result.links = _unique(result.links)
    ordered_shows = sorted(shows.values(), key=lambda r: (*_rank(r.title, needle), r.year or 0))
    results.shows = _cut(results, "shows", ordered_shows)
    return results


def _status(item_type: str, tmdb_id: int, owned: set[int], in_arr: set[int], dismissed: set,
            release_date: str | None, year: int | None, today: date) -> str:
    if tmdb_id in owned:
        return "owned"
    if tmdb_id in in_arr:
        return "in_arr"
    if (item_type, tmdb_id) in dismissed:
        return "dismissed"
    if item_type == ItemType.MOVIE.value:
        try:
            released = date.fromisoformat(release_date) <= today if release_date else None
        except ValueError:
            released = None
        if released is False or (released is None and (year is None or year > today.year)):
            return "upcoming"
    return "missing"


def _unique(links: list[Link]) -> list[Link]:
    seen: set[str] = set()
    out = []
    for link in links:
        if link.path not in seen:
            seen.add(link.path)
            out.append(link)
    return out
