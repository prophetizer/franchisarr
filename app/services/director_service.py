"""Director completion: "you own 11 Nolan films; missing Following and Insomnia".

The same shape as collections -- a set you own most of, and what would finish it -- on a
different key. TMDb's collections are a curator's grouping; a director's filmography is a fact,
and on the real library it is a rich one: 148 directors with five or more owned films, and the
missing lists are Schindler's List, Fargo, Black Hawk Down.

Two fetches, both cached. Who directed each owned film comes from that film's credits, once,
and never again -- credits do not change. A qualifying director's filmography comes from their
credits and is refreshed on the cache TTL, because it grows.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field, replace
from datetime import date, datetime, timedelta, timezone

from sqlmodel import Session, col, delete, select

from app.clients.tmdb_client import TmdbAuthError, TmdbClient, TmdbError, TmdbNotFound
from app.models import DirectorFilm, DismissedItem, ItemType, MovieDirector, utcnow
from app.services import movie_gap_service
from app.services.movie_gap_service import MIN_VOTES_FOR_A_RATING

logger = logging.getLogger(__name__)

PROGRESS_EVERY = 25

#: Under this many minutes a film is a short. The Academy's line is 40; TMDb's credits carry no
#: runtime, so it is learned per film afterwards, and an unknown runtime is never a short.
SHORT_RUNTIME_MINUTES = 40


@dataclass(frozen=True)
class DirectorTitle:
    tmdb_id: int
    title: str
    release_date: str | None
    poster_path: str | None
    vote_average: float | None
    vote_count: int | None
    is_documentary: bool = False
    runtime: int | None = None
    #: For owned films: which servers hold it, and whether it has been watched on any.
    servers: tuple[str, ...] = ()
    watched: bool | None = None

    @property
    def where(self) -> str:
        return ", ".join(self.servers)

    @property
    def is_short(self) -> bool:
        return self.runtime is not None and self.runtime < SHORT_RUNTIME_MINUTES

    @property
    def year(self) -> int | None:
        return int(self.release_date[:4]) if self.release_date and self.release_date[:4].isdigit() else None

    @property
    def rating(self) -> float | None:
        if self.vote_average is None or (self.vote_count or 0) < MIN_VOTES_FOR_A_RATING:
            return None
        return round(self.vote_average, 1)

    @property
    def poster(self) -> str | None:
        from app.services.artwork import SMALL_CARD_SIZE, poster_url

        return poster_url(self.poster_path, SMALL_CARD_SIZE)

    def is_released(self, today: date) -> bool:
        if not self.release_date:
            return False
        try:
            return date.fromisoformat(self.release_date) <= today
        except ValueError:
            return False

    def falls_below(self, threshold: float) -> bool:
        return self.rating is not None and self.rating < threshold


@dataclass
class DirectorView:
    person_id: int
    name: str
    profile_path: str | None = None
    owned: list[DirectorTitle] = field(default_factory=list)
    missing: list[DirectorTitle] = field(default_factory=list)
    upcoming: list[DirectorTitle] = field(default_factory=list)
    hidden: list[DirectorTitle] = field(default_factory=list)
    documentaries: list[DirectorTitle] = field(default_factory=list)
    #: Under forty minutes. Folded away unless the preference says otherwise.
    shorts: list[DirectorTitle] = field(default_factory=list)
    @property
    def photo(self) -> str | None:
        from app.services.artwork import profile_url

        return profile_url(self.profile_path)

    @property
    def photo_large(self) -> str | None:
        from app.services.artwork import PROFILE_LARGE_SIZE, profile_url

        return profile_url(self.profile_path, PROFILE_LARGE_SIZE)

    #: True until the filmography has been fetched at least once.
    pending: bool = False

    @property
    def total(self) -> int:
        return (len(self.owned) + len(self.missing) + len(self.hidden)
                + len(self.documentaries) + len(self.shorts))

    @property
    def best_rating(self) -> float:
        rated = [t.rating for t in self.missing if t.rating is not None]
        return max(rated) if rated else -1.0

    @property
    def top_missing(self) -> list[DirectorTitle]:
        """Missing films, best-rated first, unrated last. Sorting on `rating` directly compares
        None with a float and crashes the page for any director with both."""
        return sorted(self.missing, key=lambda t: (t.rating is None, -(t.rating or 0), t.title.casefold()))


def min_director_films(session: Session) -> int:
    from app.services.settings_service import SettingKey, get_setting

    raw = get_setting(session, SettingKey.MIN_DIRECTOR_FILMS) or "5"
    try:
        return max(2, min(50, int(raw)))
    except ValueError:
        return 5


def include_shorts(session: Session) -> bool:
    from app.services.settings_service import SettingKey, get_setting

    return (get_setting(session, SettingKey.DIRECTOR_INCLUDE_SHORTS) or "false").lower() == "true"


def _backfill_photos(session: Session, tmdb: TmdbClient, qualifying: list[int], progress=None) -> int:
    """Photos for directors credited before 0.14 kept them. One /person request each, once:
    a person with no photo is recorded as "" so they are not asked about again."""
    rows = session.exec(
        select(MovieDirector).where(col(MovieDirector.person_id).in_(qualifying),
                                    col(MovieDirector.profile_path).is_(None))
    ).all()
    todo = sorted({row.person_id for row in rows})
    for index, pid in enumerate(todo, start=1):
        if progress and index % PROGRESS_EVERY == 0:
            progress("Reading director photos", index, len(todo))
        try:
            person = tmdb.get_person(pid)
        except TmdbNotFound:
            person = None
        except TmdbAuthError:
            raise
        except TmdbError as exc:
            logger.debug("Person %s unavailable: %s", pid, exc)
            continue
        path = (person.profile_path if person else None) or ""
        for row in rows:
            if row.person_id == pid:
                row.profile_path = path
                session.add(row)
    session.commit()
    return len(todo)


def _as_utc(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


# ------------------------------------------------------------------ discovery (scan time)


def discover(
    session: Session, tmdb: TmdbClient, *, ttl: timedelta, progress=None
) -> tuple[int, int]:
    """Learn who directed each owned film, then fetch the filmography of every director who
    clears the floor. Returns (films credited, filmographies fetched).

    Credits are fetched only for films that have none recorded -- 3,400 requests once on the
    test library, then only for new arrivals. Filmographies honour the TTL like collections do.
    """
    owned = movie_gap_service.owned_tmdb_ids(session)
    credited = {row.tmdb_movie_id for row in session.exec(select(MovieDirector))}
    # Films fetched and found to have no director credit are recorded with person_id 0 so they
    # are not asked about on every scan.
    todo = sorted(owned - credited)

    fetched = 0
    for index, tmdb_id in enumerate(todo, start=1):
        if progress and index % PROGRESS_EVERY == 0:
            progress("Reading film credits", index, len(todo))
        try:
            people = tmdb.get_movie_directors(tmdb_id)
        except TmdbNotFound:
            people = []
        except TmdbAuthError:
            raise
        except TmdbError as exc:
            logger.debug("Credits unavailable for %s: %s", tmdb_id, exc)
            continue
        if not people:
            session.add(MovieDirector(tmdb_movie_id=tmdb_id, person_id=0, name=""))
        for person in people:
            session.add(MovieDirector(tmdb_movie_id=tmdb_id, person_id=person.person_id,
                                      name=person.name, profile_path=person.profile_path or ""))
        fetched += 1
        if index % 100 == 0:
            session.commit()
    session.commit()

    floor = min_director_films(session)
    counts: dict[int, int] = {}
    for row in session.exec(select(MovieDirector).where(col(MovieDirector.person_id) != 0)):
        if row.tmdb_movie_id in owned:
            counts[row.person_id] = counts.get(row.person_id, 0) + 1
    qualifying = sorted(pid for pid, n in counts.items() if n >= floor)

    _backfill_photos(session, tmdb, qualifying, progress)

    fresh_until = utcnow() - ttl
    stale: list[int] = []
    for pid in qualifying:
        newest = session.exec(
            select(DirectorFilm.fetched_at).where(col(DirectorFilm.person_id) == pid)
            .order_by(col(DirectorFilm.fetched_at).desc()).limit(1)
        ).first()
        if newest is None or _as_utc(newest) < _as_utc(fresh_until):
            stale.append(pid)

    refreshed = 0
    for index, pid in enumerate(stale, start=1):
        if progress:
            progress("Reading filmographies", index, len(stale))
        try:
            films = tmdb.get_directed_films(pid)
        except TmdbNotFound:
            films = []
        except TmdbAuthError:
            raise
        except TmdbError as exc:
            logger.debug("Filmography unavailable for %s: %s", pid, exc)
            continue
        # Bulk delete then insert, for the reason documented on every other cache here.
        session.exec(delete(DirectorFilm).where(col(DirectorFilm.person_id) == pid))
        session.flush()
        now = utcnow()
        for f in films:
            session.add(DirectorFilm(person_id=pid, tmdb_movie_id=f.tmdb_id, title=f.title,
                                     release_date=f.release_date, poster_path=f.poster_path,
                                     vote_average=f.vote_average, vote_count=f.vote_count,
                                     is_documentary=f.is_documentary, fetched_at=now))
        session.commit()
        refreshed += 1

    # Runtimes, for the shorts preference. The credits payload has none, so each unowned film
    # in a qualifying filmography is looked up once; an owned film needs no runtime because it
    # is never a candidate to hide. On the test library that is ~1,500 requests, once.
    need_runtime = session.exec(
        select(DirectorFilm).where(
            col(DirectorFilm.person_id).in_(qualifying), col(DirectorFilm.runtime).is_(None))
    ).all()
    need_runtime = [row for row in need_runtime if row.tmdb_movie_id not in owned]
    for index, row in enumerate(need_runtime, start=1):
        if progress and index % PROGRESS_EVERY == 0:
            progress("Reading runtimes", index, len(need_runtime))
        try:
            details = tmdb.get_movie(row.tmdb_movie_id)
        except TmdbNotFound:
            details = None
        except TmdbAuthError:
            raise
        except TmdbError as exc:
            logger.debug("Runtime unavailable for %s: %s", row.tmdb_movie_id, exc)
            continue
        # 0 from TMDb means "not recorded"; store 0 so it is not asked for nightly, and treat it
        # as unknown at read time.
        for same in session.exec(select(DirectorFilm).where(col(DirectorFilm.tmdb_movie_id) == row.tmdb_movie_id)):
            same.runtime = (details.runtime if details and details.runtime else 0)
            session.add(same)
        if index % 100 == 0:
            session.commit()
    session.commit()

    logger.info("Directors: %d film(s) credited, %d filmograph(ies) refreshed, %d qualify",
                fetched, refreshed, len(qualifying))
    return fetched, refreshed


# ------------------------------------------------------------------ views (read time)


def director_views(
    session: Session, user_id: int | None = None, *, today: date | None = None,
    sort: str = "owned", only: int | None = None,
) -> list[DirectorView]:
    """Every director who clears the floor, with what of theirs is owned and missing. `only`
    narrows to one person for the detail page."""
    today = today or date.today()
    owned = movie_gap_service.owned_tmdb_ids(session)
    from app.services.ownership_service import owned_details

    details = owned_details(session, ItemType.MOVIE.value)
    in_radarr = movie_gap_service.radarr_known_ids(session)
    threshold = movie_gap_service.min_gap_rating(session)
    floor = min_director_films(session)
    show_shorts = include_shorts(session)
    dismissed = {
        row.tmdb_id for row in session.exec(select(DismissedItem).where(
            col(DismissedItem.user_id) == user_id,
            col(DismissedItem.item_type) == ItemType.MOVIE.value))
    } if user_id is not None else set()

    names: dict[int, str] = {}
    photos: dict[int, str] = {}
    owned_by: dict[int, set[int]] = {}
    # Column tuples, not ORM rows: 20,000 credits and as many filmography rows as objects
    # were most of this page at scale (scripts/loadtest.py).
    for tmdb_movie_id, person_id, name, profile_path in session.exec(
        select(MovieDirector.tmdb_movie_id, MovieDirector.person_id, MovieDirector.name,
               MovieDirector.profile_path).where(col(MovieDirector.person_id) != 0)
    ):
        if tmdb_movie_id in owned:
            owned_by.setdefault(person_id, set()).add(tmdb_movie_id)
            names[person_id] = name
            if profile_path:
                photos[person_id] = profile_path

    if only is not None:
        owned_by = {only: owned_by[only]} if only in owned_by else {}
    films_query = select(DirectorFilm.person_id, DirectorFilm.tmdb_movie_id, DirectorFilm.title,
                         DirectorFilm.release_date, DirectorFilm.poster_path, DirectorFilm.vote_average,
                         DirectorFilm.vote_count, DirectorFilm.is_documentary, DirectorFilm.runtime)
    if only is not None:
        films_query = films_query.where(col(DirectorFilm.person_id) == only)
    films_by: dict[int, list[tuple]] = {}
    for row in session.exec(films_query):
        films_by.setdefault(row[0], []).append(row)

    views: list[DirectorView] = []
    for pid, owned_ids in owned_by.items():
        if len(owned_ids) < floor:
            continue
        view = DirectorView(person_id=pid, name=names[pid], profile_path=photos.get(pid))
        rows = films_by.get(pid)
        if rows is None:
            view.pending = True
            views.append(view)
            continue
        seen: set[int] = set()
        for (_, tmdb_movie_id, title, release_date, poster_path, vote_average, vote_count,
             is_documentary, runtime) in rows:
            if tmdb_movie_id in seen:
                continue
            seen.add(tmdb_movie_id)
            t = DirectorTitle(tmdb_movie_id, title, release_date, poster_path,
                              vote_average, vote_count, is_documentary, runtime or None)
            if t.tmdb_id in owned_ids or t.tmdb_id in owned:
                info = details.get(t.tmdb_id)
                view.owned.append(replace(t, servers=info.servers, watched=info.watched) if info else t)
            elif t.tmdb_id in in_radarr or t.tmdb_id in dismissed:
                continue
            elif not t.is_released(today):
                view.upcoming.append(t)
            elif t.is_short and not show_shorts:
                view.shorts.append(t)
            elif t.is_documentary:
                view.documentaries.append(t)
            elif t.falls_below(threshold):
                view.hidden.append(t)
            else:
                view.missing.append(t)
        # An owned film TMDb's filmography somehow omits still counts as owned.
        listed = {t.tmdb_id for t in view.owned}
        for tmdb_id in owned_ids - listed:
            cached = session.get(movie_gap_service.TmdbMovie, tmdb_id)
            view.owned.append(DirectorTitle(tmdb_id, cached.title if cached else f"TMDb {tmdb_id}",
                                            f"{cached.release_year}-01-01" if cached and cached.release_year else None,
                                            None, None, None))
        for lst in (view.owned, view.missing, view.upcoming, view.hidden, view.documentaries,
                    view.shorts):
            lst.sort(key=lambda t: (t.year or 9999, t.title.casefold()))
        views.append(view)

    if sort == "name":
        views.sort(key=lambda v: v.name.casefold())
    elif sort == "rating":
        views.sort(key=lambda v: (-v.best_rating, -len(v.owned), v.name.casefold()))
    else:
        views.sort(key=lambda v: (-len(v.owned), v.name.casefold()))
    return views


def director_view(session: Session, person_id: int, user_id: int | None = None) -> DirectorView | None:
    for view in director_views(session, user_id, only=person_id):
        if view.person_id == person_id:
            return view
    return None
