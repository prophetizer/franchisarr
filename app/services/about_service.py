"""What's on the back of a flipped poster in Showcase (0.51.0): a title's plot, genres, score
and running time. A collection's films carry their plot from the scan (0033); anything else --
a franchise's shows, a director's films -- is asked of TMDb the first time someone flips it, and
remembered for as long as the app runs."""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from threading import Lock

from sqlmodel import Session, col, select

from app.clients.tmdb_client import HORROR_GENRE, TmdbClient, TmdbError
from app.models import TmdbCollectionMovie

#: TMDb's film genres (GET /genre/movie/list), which change about once a decade: a collection
#: film is stored with ids, and naming them shouldn't cost a request.
GENRES = {
    28: "Action", 12: "Adventure", 16: "Animation", 35: "Comedy", 80: "Crime", 99: "Documentary",
    18: "Drama", 10751: "Family", 14: "Fantasy", 36: "History", 27: "Horror", 10402: "Music",
    9648: "Mystery", 10749: "Romance", 878: "Science Fiction", 10770: "TV Movie", 53: "Thriller",
    10752: "War", 37: "Western",
}
#: Titles remembered from TMDb. Each is a few hundred bytes; a household flips a few dozen.
REMEMBERED = 500


@dataclass(frozen=True)
class About:
    overview: str | None
    genres: tuple[str, ...] = ()
    rating: float | None = None
    runtime: int | None = None


_remembered: OrderedDict[tuple[str, int], About] = OrderedDict()
_lock = Lock()


def tmdb_for(session: Session) -> TmdbClient | None:
    from app.services.settings_service import SettingKey, get_setting

    key = get_setting(session, SettingKey.TMDB_API_KEY)
    return TmdbClient(key) if key else None


def genre_ids(raw: str | None) -> list[int]:
    return [int(g) for g in (raw or "").split(",") if g.strip().isdigit()]


def about(session: Session, kind: str, tmdb_id: int, tmdb: TmdbClient | None) -> About | None:
    """What's known about a film ("movie") or show; None when there's nothing to say."""
    if kind == "movie":
        row = session.exec(select(TmdbCollectionMovie.overview, TmdbCollectionMovie.genre_ids,
                                  TmdbCollectionMovie.vote_average)
                           .where(col(TmdbCollectionMovie.tmdb_movie_id) == tmdb_id,
                                  col(TmdbCollectionMovie.overview).is_not(None))).first()
        if row is not None:
            overview, genres, rating = row
            return About(overview, tuple(GENRES[g] for g in genre_ids(genres) if g in GENRES), rating)
    key = (kind, tmdb_id)
    with _lock:
        if key in _remembered:
            _remembered.move_to_end(key)
            return _remembered[key]
    if tmdb is None:
        return None
    try:
        details = tmdb.get_movie(tmdb_id) if kind == "movie" else tmdb.get_show(tmdb_id)
    except TmdbError:
        return None
    found = About(details.overview, details.genres, details.vote_average, getattr(details, "runtime", None))
    with _lock:
        _remembered[key] = found
        while len(_remembered) > REMEMBERED:
            _remembered.popitem(last=False)
    return found


def is_horror(session: Session, *, collection_id: int | None = None, film_ids: list[int] | tuple[int, ...] = ()) -> bool:
    """Whether most of a collection's -- or a franchise's -- films are horror, for Showcase's
    October touch. Only films whose genres are known count; with none known, it isn't."""
    query = select(TmdbCollectionMovie.tmdb_movie_id, TmdbCollectionMovie.genre_ids).where(
        col(TmdbCollectionMovie.genre_ids).is_not(None))
    if collection_id is not None:
        query = query.where(col(TmdbCollectionMovie.collection_id) == collection_id)
    elif film_ids:
        query = query.where(col(TmdbCollectionMovie.tmdb_movie_id).in_(list(film_ids)))
    else:
        return False
    genres = {tmdb_id: genre_ids(raw) for tmdb_id, raw in session.exec(query).all()}
    return bool(genres) and sum(HORROR_GENRE in g for g in genres.values()) * 2 > len(genres)


_trailers: OrderedDict[tuple[str, int], str | None] = OrderedDict()


def trailer(kind: str, tmdb_id: int, tmdb: TmdbClient | None) -> str | None:
    """A film's or show's YouTube trailer key (0.54.0), asked of TMDb once and remembered --
    "none" included, so a film without one isn't asked about on every press."""
    key = (kind, tmdb_id)
    with _lock:
        if key in _trailers:
            _trailers.move_to_end(key)
            return _trailers[key]
    if tmdb is None:
        return None
    try:
        found = tmdb.get_trailer(tmdb_id, "tv" if kind == "show" else "movie")
    except TmdbError:
        return None                      # not remembered: TMDb may be back in a minute
    with _lock:
        _trailers[key] = found
        while len(_trailers) > REMEMBERED:
            _trailers.popitem(last=False)
    return found
