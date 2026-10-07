"""The home page's poster rows (0.45.0, michael's pick): the collections closest to complete,
what's coming out in the next 90 days, and what's just arrived in the library from the sets
being collected. Each is a short list of cards; the pages they link to have the rest."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from sqlmodel import Session, col, select

from app.models import DirectorFilm, FranchiseMember, LibraryItem, TmdbCollectionMovie, TmdbShow

#: Showcase's poster wall (0.56.0): three rows behind the home heading, wide enough to pan.
WALL = 72

#: Cards per row: enough to fill a wide screen, few enough to stay a glance.
ROW = 12
#: On a fresh install the first scan brings in the whole library at once. That isn't "just added",
#: so anything first seen within this long of the very first title is left out.
FIRST_SCAN = timedelta(days=1)


@dataclass(frozen=True)
class Card:
    title: str
    detail: str
    poster: str | None
    path: str


def closest_to_complete(gaps: list, limit: int = ROW) -> list[Card]:  # noqa: ANN001 - CollectionGap
    """Collections with the smallest share missing: one film away first."""
    ranked = sorted((g for g in gaps if g.missing),
                    key=lambda g: (-len(g.owned) / (len(g.owned) + len(g.missing)), len(g.missing), g.name.casefold()))
    return [Card(g.name, f"{len(g.missing)} missing · {len(g.owned)} of {len(g.owned) + len(g.missing)}",
                 g.small_poster, f"/collections/{g.collection_id}") for g in ranked[:limit]]


def up_next(gaps: list, limit: int = ROW) -> list[Card]:  # noqa: ANN001 - CollectionGap, every one
    """Up next (0.72.0, michael's pick): for each collection you've started watching, the first film
    you own and haven't watched, in release order. Furthest along first. Only where a server
    reports watched state; a set with nothing watched yet isn't "started"."""
    picks = []
    for g in gaps:
        owned = sorted(g.owned, key=lambda m: (m.release_date or f"{m.release_year or 9999}", m.title.casefold()))
        watched = sum(1 for m in owned if m.watched)
        unwatched = [m for m in owned if m.watched is False]
        if not watched or not unwatched:
            continue
        film = unwatched[0]
        picks.append((watched / len(owned), Card(film.title, f"{g.name} · {watched} of {len(owned)} watched",
                                                 film.poster, f"/collections/{g.collection_id}")))
    picks.sort(key=lambda p: (-p[0], p[1].title.casefold()))
    return [card for _, card in picks[:limit]]


def on_this_day(session: Session, today: date, limit: int = ROW) -> list[Card]:
    """On this day (0.72.0, michael's pick): films you own released on today's date in an earlier
    year, oldest anniversary first. Exact dates are known for films in collections and in
    directors' filmographies; the rest only have a year, so can't take part."""
    from urllib.parse import quote

    from app.services.artwork import SMALL_CARD_SIZE, poster_url
    from app.services.movie_gap_service import owned_tmdb_ids

    owned = owned_tmdb_ids(session)
    if not owned:
        return []
    day = today.strftime("-%m-%d")
    found: dict[int, tuple] = {}
    for tmdb_id, title, released, poster, collection_id in session.exec(
            select(TmdbCollectionMovie.tmdb_movie_id, TmdbCollectionMovie.title, TmdbCollectionMovie.release_date,
                   TmdbCollectionMovie.poster_path, TmdbCollectionMovie.collection_id)
            .where(col(TmdbCollectionMovie.tmdb_movie_id).in_(owned), col(TmdbCollectionMovie.release_date).like(f"%{day}"))):
        found.setdefault(tmdb_id, (title, released, poster, f"/collections/{collection_id}"))
    for tmdb_id, title, released, poster in session.exec(
            select(DirectorFilm.tmdb_movie_id, DirectorFilm.title, DirectorFilm.release_date, DirectorFilm.poster_path)
            .where(col(DirectorFilm.tmdb_movie_id).in_(owned), col(DirectorFilm.release_date).like(f"%{day}"))):
        found.setdefault(tmdb_id, (title, released, poster, f"/search?q={quote(title)}"))
    cards = []
    for title, released, poster, path in found.values():
        try:
            year = int(released[:4])
        except (TypeError, ValueError):
            continue
        if year >= today.year:
            continue
        ago = today.year - year
        cards.append((year, Card(title, f"{year} · {ago} year{'' if ago == 1 else 's'} ago today",
                                 poster_url(poster, SMALL_CARD_SIZE), path)))
    cards.sort(key=lambda pair: (pair[0], pair[1].title.casefold()))
    return [card for _, card in cards[:limit]]


@dataclass(frozen=True)
class Slide:
    """One slide of Showcase's spotlight (0.48.0): a collection nearly done, big."""

    title: str
    detail: str
    backdrop: str | None
    logo: str | None
    poster: str | None
    path: str
    owned: int
    total: int
    #: The film that would finish it -- the earliest missing -- for the ▶ Trailer (0.54.0).
    next_id: int | None = None
    next_title: str = ""


def spotlight(gaps: list, limit: int = 5) -> list[Slide]:  # noqa: ANN001 - CollectionGap
    """Collections with a backdrop to fill a screen, one or two films from done, best-known first
    -- the most TMDb votes across their films -- then the rest by how close they are (michael,
    0.49.1). Bigger-first (0.49.0) changed nothing on his library, whose one-away sets top out
    at six films; what separated Star Trek from Frosty the Snowman was how well-known they are."""
    def fame(g) -> int:  # noqa: ANN001
        return sum(getattr(m, "vote_count", 0) or 0 for m in (*g.owned, *g.missing))

    candidates = [g for g in gaps if g.missing and g.backdrop]
    near = sorted((g for g in candidates if len(g.missing) <= 2),
                  key=lambda g: (-fame(g), len(g.missing), g.name.casefold()))
    rest = sorted((g for g in candidates if len(g.missing) > 2),
                  key=lambda g: (-len(g.owned) / (len(g.owned) + len(g.missing)), g.name.casefold()))
    ranked = near + rest
    slides = []
    for g in ranked[:limit]:
        owned, total = len(g.owned), len(g.owned) + len(g.missing)
        left = len(g.missing)
        first = min(g.missing, key=lambda m: (getattr(m, "release_date", None) or "9999", str(getattr(m, "title", ""))))
        slides.append(Slide(g.name, f"You have {owned} of {total} — {left} to go" if left > 1 else
                            f"You have {owned} of {total} — one film away",
                            g.backdrop, g.logo_image, g.poster, f"/collections/{g.collection_id}", owned, total,
                            getattr(first, "tmdb_id", None), getattr(first, "title", "")))
    return slides


def coming_soon(films: list, today: date, days: int = 90, limit: int = ROW) -> list[Card]:  # noqa: ANN001
    """Announced films in owned franchises due in the next `days`, soonest first."""
    due = sorted((f for f in films if (d := f.days_until(today)) is not None and 0 <= d <= days),
                 key=lambda f: (f.days_until(today), f.title.casefold()))
    cards = []
    for film in due[:limit]:
        left = film.days_until(today)
        when = "today" if left == 0 else ("tomorrow" if left == 1 else f"in {left} days")
        cards.append(Card(film.title, f"{film.release_date} · {when}", film.poster, f"/collections/{film.collection_id}"))
    return cards


def just_added(session: Session, limit: int = ROW) -> list[Card]:
    """Titles new to the library that belong to something being collected -- a collection, a
    franchise or a director's films -- newest first. Only titles first seen by a scan since
    0.45.0 count (earlier ones have no date), and on a fresh install not the first scan's."""
    from app.services.artwork import SMALL_CARD_SIZE, poster_url
    from app.services.ownership_service import on_enabled_server

    dated = (col(LibraryItem.first_seen_at).is_not(None)) & (col(LibraryItem.tmdb_id).is_not(None)) & on_enabled_server()
    undated = session.exec(select(LibraryItem.id).where(col(LibraryItem.first_seen_at).is_(None)).limit(1)).first()
    if undated is None:
        first = session.exec(select(LibraryItem.first_seen_at).where(dated).order_by(col(LibraryItem.first_seen_at))).first()
        if first is None:
            return []
        dated = dated & (col(LibraryItem.first_seen_at) > first + FIRST_SCAN)
    rows = session.exec(select(LibraryItem.item_type, LibraryItem.tmdb_id, LibraryItem.title, LibraryItem.first_seen_at)
                        .where(dated).order_by(col(LibraryItem.first_seen_at).desc()).limit(limit * 10)).all()
    seen: set[tuple[str, int]] = set()
    picks = []
    for kind, tmdb_id, title, when in rows:
        if (kind, tmdb_id) not in seen:
            seen.add((kind, tmdb_id))
            picks.append((kind, tmdb_id, title, when))
    films = [t for k, t, _, _ in picks if k == "movie"]
    shows = [t for k, t, _, _ in picks if k == "show"]
    # Where each belongs, and a poster: a collection first, then a franchise, then a director.
    homes: dict[tuple[str, int], tuple[str, str | None]] = {}
    for tmdb_id, collection_id, poster in session.exec(select(
            TmdbCollectionMovie.tmdb_movie_id, TmdbCollectionMovie.collection_id, TmdbCollectionMovie.poster_path)
            .where(col(TmdbCollectionMovie.tmdb_movie_id).in_(films))).all():
        homes.setdefault(("movie", tmdb_id), (f"/collections/{collection_id}", poster))
    for kind, tmdb_id, franchise_id, poster in session.exec(select(
            FranchiseMember.item_type, FranchiseMember.tmdb_id, FranchiseMember.franchise_id, FranchiseMember.poster_path)
            .where(col(FranchiseMember.tmdb_id).in_(films + shows))).all():
        homes.setdefault((kind, tmdb_id), (f"/franchises/{franchise_id}", poster))
    for tmdb_id, person_id, poster in session.exec(select(
            DirectorFilm.tmdb_movie_id, DirectorFilm.person_id, DirectorFilm.poster_path)
            .where(col(DirectorFilm.tmdb_movie_id).in_(films))).all():
        homes.setdefault(("movie", tmdb_id), (f"/directors/{person_id}", poster))
    show_posters = dict(session.exec(select(TmdbShow.tmdb_id, TmdbShow.poster_path)
                                     .where(col(TmdbShow.tmdb_id).in_(shows))).all())
    now = datetime.now(timezone.utc)
    cards = []
    for kind, tmdb_id, title, when in picks:
        home = homes.get((kind, tmdb_id))
        if home is None:
            continue                     # not part of anything being collected
        path, poster = home
        poster = poster or (show_posters.get(tmdb_id) if kind == "show" else None)
        cards.append(Card(title, _ago(when, now), poster_url(poster, SMALL_CARD_SIZE), path))
        if len(cards) == limit:
            break
    return cards


def _ago(when: datetime, now: datetime) -> str:
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    days = (now - when).days
    return "today" if days < 1 else ("yesterday" if days == 1 else f"{days} days ago")


#: The day's wall, kept an hour: drawing it reads the library (380ms on 3,400 films), and the
#: draw is the same all day anyway.
_walls: dict[tuple[date, int], tuple[float, list[str]]] = {}
WALL_FOR = 3600.0


def poster_wall(session: Session, today: date, limit: int = WALL) -> list[str]:
    """Posters of films in the library, for the wall behind Showcase's home heading (0.56.0):
    a different draw each day, the same all day. Small copies -- they're dimmed and drifting."""
    import time

    kept = _walls.get((today, limit))
    if kept and time.monotonic() - kept[0] < WALL_FOR:
        return kept[1]
    wall = _draw_wall(session, today, limit)
    _walls.clear()
    _walls[(today, limit)] = (time.monotonic(), wall)
    return wall


def _draw_wall(session: Session, today: date, limit: int) -> list[str]:
    import random

    from app.services.artwork import poster_url
    from app.services.movie_gap_service import owned_tmdb_ids

    owned = owned_tmdb_ids(session)
    if not owned:
        return []
    paths = {tmdb_id: path for tmdb_id, path in session.exec(
        select(TmdbCollectionMovie.tmdb_movie_id, TmdbCollectionMovie.poster_path)
        .where(col(TmdbCollectionMovie.poster_path).is_not(None))).all() if tmdb_id in owned}
    for tmdb_id, path in session.exec(select(DirectorFilm.tmdb_movie_id, DirectorFilm.poster_path)
                                      .where(col(DirectorFilm.poster_path).is_not(None))).all():
        if tmdb_id in owned:
            paths.setdefault(tmdb_id, path)
    chosen = random.Random(today.toordinal()).sample(sorted(paths.values()), min(limit, len(paths)))
    return [url for url in (poster_url(p, "w92") for p in chosen) if url]
