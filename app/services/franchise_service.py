"""One page per franchise, across both media.

Everything else in the app is per medium: collections for films, spin-offs for TV, and lately
the continuations that cross between them. A franchise is the thing a person actually thinks
in -- "Star Trek", not "the Star Trek: The Original Series film collection" -- and this is the
one view that answers "how much of it do I have, and what's missing?" in a single place.

It synthesises rather than computes. Missing films come from the collection gaps of the films
the user owns in the franchise; missing shows from spin-off and cross-media suggestions whose
source is in it; and a third source is new: every whole film or series Wikidata itself files
under the franchise, which is the only way to learn about Deep Space Nine from owning Voyager.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Iterable
from dataclasses import dataclass, field, replace
from datetime import date, datetime, timedelta

from sqlmodel import Session, col, delete, select

from app.clients.tmdb_client import TmdbAuthError, TmdbClient, TmdbError
from app.clients.wikidata_client import FranchiseGroup, FranchiseTitle, WikidataClient
from app.models import (
    DirectorFilm, DismissedItem, Franchise, FranchiseMember, ItemType, LibraryItem, TmdbCollectionMovie,
    TmdbMovie, TmdbShow, utcnow,
)
from app.services import cross_media_service, movie_gap_service, tv_spinoff_service
from app.services.movie_gap_service import MissingMovie

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Title:
    """A film or show on a franchise page, whichever list it came from."""

    item_type: str
    tmdb_id: int
    title: str
    year: int | None = None
    poster_path: str | None = None
    release_date: str | None = None
    #: Where the app learned this is missing: "collection", "spin-off", "continuation",
    #: "franchise". Shown so the user knows how much to trust it.
    via: str = ""
    note: str = ""
    #: For owned titles: which servers hold it, and whether it has been watched on any.
    servers: tuple[str, ...] = ()
    watched: bool | None = None
    #: Minutes, for owned films whose server reports it (0.72.0).
    runtime: int | None = None

    @property
    def where(self) -> str:
        return ", ".join(self.servers)

    @property
    def poster(self) -> str | None:
        from app.services.artwork import SMALL_CARD_SIZE, poster_url

        return poster_url(self.poster_path, SMALL_CARD_SIZE)


@dataclass
class FranchiseView:
    wikidata_id: str
    name: str
    kind: str | None
    owned_films: list[Title] = field(default_factory=list)
    owned_shows: list[Title] = field(default_factory=list)
    missing_films: list[Title] = field(default_factory=list)
    upcoming_films: list[Title] = field(default_factory=list)
    missing_shows: list[Title] = field(default_factory=list)
    #: TV films, specials and shorts on the roster, folded away unless the preference says
    #: otherwise. Never counted as missing.
    specials: list[Title] = field(default_factory=list)
    #: A poster for the card and a logo for the heading, borrowed from the collection that *is*
    #: this franchise -- same name, or most of its films (see _pick_art, 0.46.1). None when no
    #: collection is, and the card shows `mosaic` instead.
    poster_path: str | None = None
    backdrop_path: str | None = None
    logo_url: str | None = None

    @property
    def owned(self) -> int:
        return len(self.owned_films) + len(self.owned_shows)

    @property
    def missing(self) -> int:
        return len(self.missing_films) + len(self.missing_shows)

    @property
    def total(self) -> int:
        return self.owned + self.missing

    @property
    def spans_both(self) -> bool:
        return bool(self.owned_films or self.missing_films) and bool(self.owned_shows or self.missing_shows)

    @property
    def poster(self) -> str | None:
        from app.services.artwork import CARD_SIZE, poster_url

        return poster_url(self.poster_path, CARD_SIZE)

    @property
    def small_poster(self) -> str | None:
        """For the list card, where the poster is a thumbnail beside the text."""
        from app.services.artwork import SMALL_CARD_SIZE, poster_url

        return poster_url(self.poster_path, SMALL_CARD_SIZE)

    @property
    def mosaic(self) -> list[str]:
        """Four owned titles' posters, spread across the run, for a franchise no one collection
        stands for (the MCU is not the Iron Man Collection). Empty when it has a poster of its
        own, or fewer than four titles with posters."""
        if self.poster_path:
            return []
        from app.services.artwork import SMALL_CARD_SIZE, poster_url

        titles = sorted((t for t in self.owned_films + self.owned_shows if t.poster_path),
                        key=lambda t: (t.year or 9999, t.title.casefold()))
        if len(titles) < 4:
            return []
        picks = [titles[round(i * (len(titles) - 1) / 3)] for i in range(4)]
        return [poster_url(t.poster_path, SMALL_CARD_SIZE) for t in picks]

    @property
    def backdrop(self) -> str | None:
        from app.services.artwork import backdrop_url

        return backdrop_url(self.backdrop_path)

    @property
    def logo_image(self) -> str | None:
        from app.services.artwork import logo_url

        return logo_url(self.logo_url)


# ------------------------------------------------------------------ discovery (scan time)


def discover(
    session: Session, wikidata: WikidataClient, tmdb: TmdbClient | None,
    *, ttl: timedelta | None = None, progress=None,
) -> int:
    """Refresh the franchise tables from Wikidata. Returns the number of franchises kept.

    Gated on the cache TTL like collections are: this is the longest Wikidata step -- a roster
    query per franchise, two hundred of them on the test library -- and franchise membership
    changes on the scale of months. A scan inside the TTL leaves the tables alone; "Refresh
    everything" passes a zero TTL and rebuilds them.

    Groups with a single owned title are dropped: a franchise the user has one thing from is
    not a franchise they are collecting, and listing every film's "series" would bury the
    ones that matter. Membership is replaced wholesale, bulk-delete then insert, for the reason
    documented on every other cache in this codebase.
    """
    if ttl is not None and ttl > timedelta(0):
        newest = session.exec(
            select(Franchise.fetched_at).order_by(col(Franchise.fetched_at).desc()).limit(1)
        ).first()
        if newest is not None and _as_utc(newest) + ttl > utcnow():
            # Membership is fresh, but a title with no poster is filled on every scan: it costs
            # one TMDb request per such title, once, and waiting a week for the TTL left the
            # MCU's Incredible Hulk blank (0.46.1).
            fill_posters(session, tmdb)
            return len(session.exec(select(Franchise)).all())

    show_ids = sorted(tv_spinoff_service.owned_show_ids(session, all_servers=True))
    movie_ids = sorted(movie_gap_service.owned_tmdb_ids(session, all_servers=True))
    if progress:
        progress("Grouping into franchises", 0, len(show_ids) + len(movie_ids))

    groups, membership = wikidata.franchises_for(show_ids=show_ids, movie_ids=movie_ids)
    owned_count: dict[str, int] = {}
    for ids in membership.values():
        for qid in ids:
            owned_count[qid] = owned_count.get(qid, 0) + 1
    kept = [g for g in groups if owned_count.get(g.wikidata_id, 0) >= 2]

    # Existing display details survive across refreshes, so a title fetched from TMDb once is
    # not fetched again every scan.
    known: dict[tuple[str, int], FranchiseMember] = {
        (m.item_type, m.tmdb_id): m for m in session.exec(select(FranchiseMember)).all()
    }
    library_titles = {
        (row.item_type, row.tmdb_id): row
        for row in session.exec(select(LibraryItem).where(col(LibraryItem.tmdb_id).is_not(None)))
    }

    session.exec(delete(FranchiseMember))
    session.exec(delete(Franchise))
    session.flush()
    lookups = _PosterLookups(tmdb)

    now = utcnow()
    for index, group in enumerate(kept, start=1):
        if progress:
            progress("Grouping into franchises", index, len(kept))
        session.add(Franchise(wikidata_id=group.wikidata_id, name=group.name,
                              kind=group.kind, fetched_at=now))
        # One row per (medium, TMDb id), whatever Wikidata does. Owned titles filed under the
        # group but missing from the roster query (their statement sits on a sub-group) are
        # members too.
        roster: dict[tuple[str, int], FranchiseTitle] = {}
        for qid in (group.wikidata_id, *group.aliases):
            for t in wikidata.franchise_titles(qid):
                roster.setdefault((t.item_type, t.tmdb_id),
                                  FranchiseTitle(group.wikidata_id, t.item_type, t.tmdb_id, t.name, t.kind))
        for (item_type, tmdb_id), ids in membership.items():
            if group.wikidata_id in ids and (item_type, tmdb_id) not in roster:
                lib = library_titles.get((item_type, tmdb_id))
                roster[(item_type, tmdb_id)] = FranchiseTitle(
                    group.wikidata_id, item_type, tmdb_id,
                    lib.title if lib else f"TMDb {tmdb_id}")

        for key, t in roster.items():
            session.add(_member_for(session, t, known.get(key), library_titles.get(key), lookups))
    session.commit()
    logger.info("Franchises: %d kept of %d found", len(kept), len(groups))
    return len(kept)


def fill_posters(session: Session, tmdb: TmdbClient | None) -> int:
    """Give every roster row nobody has found a poster for one: from the caches, else TMDb.
    Returns how many got one."""
    lookups = _PosterLookups(tmdb)
    filled = 0
    for member in session.exec(select(FranchiseMember).where(col(FranchiseMember.poster_path).is_(None))).all():
        poster = _cached_poster(session, member.item_type, member.tmdb_id)
        if poster is None and (found := lookups.details(member.item_type, member.tmdb_id)) is not None:
            poster = found[2]
        if poster is not None:
            member.poster_path = poster
            session.add(member)
            filled += bool(poster)
    session.commit()
    if filled:
        logger.info("Franchises: found posters for %d title%s", filled, "" if filled == 1 else "s")
    return filled


class _PosterLookups:
    """TMDb asked once per title per refresh, whichever franchises it's in; and not again after
    a rejected key (see CLAUDE.md on dead keys)."""

    def __init__(self, tmdb: TmdbClient | None) -> None:
        self.tmdb = tmdb
        self.done: dict[tuple[str, int], tuple[str | None, int | None, str]] = {}
        #: The show details fetched, for the show cache.
        self.shows: dict[int, object] = {}

    def details(self, item_type: str, tmdb_id: int) -> tuple[str | None, int | None, str] | None:
        """(title, year, poster path -- "" for none) from TMDb, or None if it couldn't say."""
        key = (item_type, tmdb_id)
        if key in self.done:
            return self.done[key]
        if self.tmdb is None:
            return None
        try:
            if item_type == ItemType.MOVIE.value:
                d = self.tmdb.get_movie(tmdb_id)
                found = (d.title, d.year, d.poster_path or "")
            else:
                d = self.tmdb.get_show(tmdb_id)
                self.shows[tmdb_id] = d
                found = (d.name, d.year, d.poster_path or "")
        except TmdbAuthError:
            logger.warning("TMDb rejected the key; franchise posters stop here")
            self.tmdb = None
            return None
        except TmdbError as exc:
            logger.debug("No TMDb details for %s %s: %s", item_type, tmdb_id, exc)
            return None
        self.done[key] = found
        return found


def _member_for(
    session: Session, t: FranchiseTitle, previous: FranchiseMember | None,
    lib: LibraryItem | None, lookups: _PosterLookups,
) -> FranchiseMember:
    """A roster row with a title, year and poster. poster_path "" means TMDb was asked and has
    none; None means nobody has asked yet -- an owned title that isn't in any collection or
    director's films had no poster until 0.46.1 (the MCU's Incredible Hulk), so it's asked now."""
    if previous is not None:
        poster = previous.poster_path
        if poster is None:
            poster = _cached_poster(session, t.item_type, t.tmdb_id)
        if poster is None and (found := lookups.details(t.item_type, t.tmdb_id)) is not None:
            poster = found[2]
        return FranchiseMember(franchise_id=t.franchise_id, item_type=t.item_type,
                              tmdb_id=t.tmdb_id, title=previous.title, year=previous.year,
                              poster_path=poster, kind=t.kind or previous.kind)
    title, year, poster = t.name, None, None
    if lib is not None:
        # Owned: the library already knows the title and year, and the collection, director or
        # show cache usually has a poster; TMDb is asked only when none does.
        title, year = lib.title, lib.year
        poster = _cached_poster(session, t.item_type, t.tmdb_id)
        if poster is None and (found := lookups.details(t.item_type, t.tmdb_id)) is not None:
            poster = found[2]
        return FranchiseMember(franchise_id=t.franchise_id, item_type=t.item_type,
                              tmdb_id=t.tmdb_id, title=title, year=year, poster_path=poster,
                              kind=t.kind)
    if t.item_type == ItemType.MOVIE.value:
        cached = session.get(TmdbMovie, t.tmdb_id)
        if cached is not None:
            title, year = cached.title, cached.release_year
    if (found := lookups.details(t.item_type, t.tmdb_id)) is not None:
        title, year, poster = found[0] or title, found[1] or year, found[2]
        if t.item_type == ItemType.SHOW.value and t.tmdb_id in lookups.shows:
            # Into the show cache too: that is where a TVDB id lives, and Sonarr's import
            # list needs one for every show it is handed.
            tv_spinoff_service.cache_show(session, lookups.shows.pop(t.tmdb_id))
    return FranchiseMember(franchise_id=t.franchise_id, item_type=t.item_type,
                          tmdb_id=t.tmdb_id, title=title, year=year, poster_path=poster,
                          kind=t.kind)


def _cached_poster(session: Session, item_type: str, tmdb_id: int) -> str | None:
    if item_type == ItemType.MOVIE.value:
        row = session.exec(
            select(TmdbCollectionMovie.poster_path)
            .where(col(TmdbCollectionMovie.tmdb_movie_id) == tmdb_id)
            .where(col(TmdbCollectionMovie.poster_path).is_not(None))
            .limit(1)
        ).first()
        if row is None:
            row = session.exec(select(DirectorFilm.poster_path).where(
                col(DirectorFilm.tmdb_movie_id) == tmdb_id, col(DirectorFilm.poster_path).is_not(None)).limit(1)).first()
        return row
    show = session.get(TmdbShow, tmdb_id)
    return show.poster_path if show else None


def _as_utc(value: datetime) -> datetime:
    from datetime import timezone

    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


# ------------------------------------------------------------------ views (read time)


def include_tv_films(session: Session) -> bool:
    from app.services.settings_service import SettingKey, get_setting

    return (get_setting(session, SettingKey.FRANCHISE_INCLUDE_TV_FILMS) or "false").lower() == "true"


def _is_minor(kind: str | None) -> bool:
    from app.clients.wikidata_client import MINOR_KINDS

    return bool(kind) and any(word in kind for word in MINOR_KINDS)


def _dismissed(session: Session, user_id: int | None) -> set[tuple[str, int]]:
    if user_id is None:
        return set()
    return {
        (row.item_type, row.tmdb_id)
        for row in session.exec(select(DismissedItem).where(col(DismissedItem.user_id) == user_id))
    }


def franchise_views(
    session: Session, user_id: int | None = None, *, today: date | None = None,
    only: str | None = None,
) -> list[FranchiseView]:
    """Every franchise, assembled. Sorted by how much of it the user has, most first. `only`
    narrows to one Wikidata id for the detail page; the shared inputs (collection gaps,
    spin-offs, continuations) are what cost, and those are computed once either way."""
    owned_films = movie_gap_service.owned_tmdb_ids(session)
    owned_shows = tv_spinoff_service.owned_show_ids(session)
    in_radarr = movie_gap_service.radarr_known_ids(session)
    in_sonarr = tv_spinoff_service.sonarr_known_ids(session)
    dismissed = _dismissed(session, user_id)
    from app.services.ownership_service import owned_details

    film_details = owned_details(session, ItemType.MOVIE.value)
    show_details = owned_details(session, ItemType.SHOW.value)

    def with_ownership(t: Title) -> Title:
        info = (film_details if t.item_type == ItemType.MOVIE.value else show_details).get(t.tmdb_id)
        return replace(t, servers=info.servers, watched=info.watched, runtime=info.runtime) if info else t

    include_minor = include_tv_films(session)

    gaps = movie_gap_service.collection_gaps(session, user_id, today=today)
    gap_by_film: dict[int, movie_gap_service.CollectionGap] = {}
    for gap in gaps:
        for m in gap.owned:
            gap_by_film[m.tmdb_id] = gap
    spinoffs = tv_spinoff_service.missing_spinoffs(session, user_id)
    cross_shows = cross_media_service.suggestions(session, ItemType.SHOW.value, user_id)
    cross_films = cross_media_service.suggestions(session, ItemType.MOVIE.value, user_id)

    members = session.exec(select(FranchiseMember)).all()
    by_franchise: dict[str, list[FranchiseMember]] = {}
    for m in members:
        by_franchise.setdefault(m.franchise_id, []).append(m)

    franchise_query = select(Franchise)
    if only is not None:
        franchise_query = franchise_query.where(col(Franchise.wikidata_id) == only)

    views: list[FranchiseView] = []
    for franchise in session.exec(franchise_query).all():
        view = FranchiseView(wikidata_id=franchise.wikidata_id, name=franchise.name,
                             kind=franchise.kind)
        film_ids: set[int] = set()
        show_ids: set[int] = set()
        seen_missing: set[tuple[str, int]] = set()

        def add_missing(t: Title) -> None:
            key = (t.item_type, t.tmdb_id)
            if key in seen_missing or key in dismissed:
                return
            if t.item_type == ItemType.MOVIE.value and (t.tmdb_id in owned_films or t.tmdb_id in in_radarr):
                return
            if t.item_type == ItemType.SHOW.value and (t.tmdb_id in owned_shows or t.tmdb_id in in_sonarr):
                return
            seen_missing.add(key)
            (view.missing_films if t.item_type == ItemType.MOVIE.value else view.missing_shows).append(t)

        for m in by_franchise.get(franchise.wikidata_id, []):
            t = Title(item_type=m.item_type, tmdb_id=m.tmdb_id, title=m.title, year=m.year,
                      poster_path=m.poster_path, via="franchise",
                      note=f"Wikidata files it under {franchise.name}")
            if m.item_type == ItemType.MOVIE.value and m.tmdb_id in owned_films:
                view.owned_films.append(with_ownership(t)); film_ids.add(m.tmdb_id)
            elif m.item_type == ItemType.SHOW.value and m.tmdb_id in owned_shows:
                view.owned_shows.append(with_ownership(t)); show_ids.add(m.tmdb_id)

        # Collections the owned films belong to: their gaps and upcoming films, and artwork.
        seen_gaps: set[int] = set()
        held: dict[int, int] = {}
        for fid in film_ids:
            if (g := gap_by_film.get(fid)) is not None:
                held[g.collection_id] = held.get(g.collection_id, 0) + 1
        candidates = []
        for fid in sorted(film_ids):
            gap = gap_by_film.get(fid)
            if gap is None or gap.collection_id in seen_gaps:
                continue
            seen_gaps.add(gap.collection_id)
            candidates.append((gap, held.get(gap.collection_id, 0)))
            for mm in gap.missing:
                add_missing(_from_missing(mm, "collection", gap.name))
            for mm in gap.upcoming:
                key = (ItemType.MOVIE.value, mm.tmdb_id)
                if key not in seen_missing and key not in dismissed:
                    seen_missing.add(key)
                    view.upcoming_films.append(_from_missing(mm, "collection", gap.name))

        for s in spinoffs:
            if s.source_show_tmdb_id in show_ids:
                add_missing(Title(ItemType.SHOW.value, s.spinoff_tmdb_id, s.spinoff_name,
                                  s.first_air_year, s.poster_path, via="spin-off",
                                  note=s.relationships))
        for s in cross_shows:
            if s.source_tmdb_id in film_ids:
                add_missing(Title(ItemType.SHOW.value, s.target_tmdb_id, s.target_title,
                                  s.target_year, s.target_poster_path, via="continuation",
                                  note=s.relationships))
        for s in cross_films:
            if s.source_tmdb_id in show_ids:
                add_missing(Title(ItemType.MOVIE.value, s.target_tmdb_id, s.target_title,
                                  s.target_year, s.target_poster_path, via="continuation",
                                  note=s.relationships))
        # Last, the franchise's own roster -- lowest trust, so it never outranks a collection.
        # TV films, specials and shorts are folded away unless the preference says otherwise.
        for m in by_franchise.get(franchise.wikidata_id, []):
            t = Title(m.item_type, m.tmdb_id, m.title, m.year, m.poster_path,
                      via="franchise", note=(m.kind or f"Wikidata files it under {franchise.name}"))
            if _is_minor(m.kind) and not include_minor:
                key = (m.item_type, m.tmdb_id)
                owned_it = (m.tmdb_id in owned_films) if m.item_type == ItemType.MOVIE.value else (m.tmdb_id in owned_shows)
                if key not in seen_missing and key not in dismissed and not owned_it:
                    seen_missing.add(key)
                    view.specials.append(t)
                continue
            add_missing(t)

        for lst in (view.owned_films, view.owned_shows, view.missing_films,
                    view.missing_shows, view.upcoming_films, view.specials):
            lst.sort(key=lambda t: (t.year or 9999, t.title.casefold()))
        _pick_art(view, candidates, len(film_ids))
        views.append(view)

    views.sort(key=lambda v: (-v.owned, v.name.casefold()))
    return views


_NAME_NOISE = re.compile(r"^the |\b(collection|franchise|film series|series|saga|universe)\b|[^a-z0-9]+")


def _same_name(a: str, b: str) -> bool:
    """"Star Wars" and "Star Wars Collection", "Alien franchise" and "Alien Collection"."""
    def norm(name: str) -> str:
        return _NAME_NOISE.sub("", name.casefold())
    return bool(norm(a)) and norm(a) == norm(b)


def _pick_art(view: FranchiseView, candidates: list, owned_films: int) -> None:  # noqa: ANN001
    """Borrow a collection's artwork only when that collection is the franchise (michael,
    0.46.1: the MCU's page read "Iron Man" because the Iron Man Collection came first). The
    logo, which names it, needs the same name; the poster and backdrop also go with a collection
    holding most of the franchise's films. Otherwise: no logo, the mosaic for a poster, and the
    backdrop of the biggest collection -- a picture, not a claim."""
    if candidates:
        named = next((gap for gap, _ in candidates if _same_name(gap.name, view.name)), None)
        biggest, count = max(candidates, key=lambda pair: pair[1])
        if named is not None:
            view.poster_path, view.backdrop_path, view.logo_url = named.poster_path, named.backdrop_path, named.logo
        elif count * 2 > owned_films:
            view.poster_path, view.backdrop_path = biggest.poster_path, biggest.backdrop_path
        else:
            view.backdrop_path = biggest.backdrop_path
    if not view.poster_path and not view.mosaic:
        # Too few posters for a mosaic (or no collection at all -- Arrowverse, Cloverfield): its
        # earliest title's own poster, which names a film of the franchise rather than claiming
        # a collection is it.
        first = next((t for t in view.owned_films + view.owned_shows if t.poster_path), None)
        if first is not None:
            view.poster_path = first.poster_path


def _from_missing(mm: MissingMovie, via: str, collection_name: str) -> Title:
    return Title(item_type=ItemType.MOVIE.value, tmdb_id=mm.tmdb_id, title=mm.title,
                 year=mm.release_year, poster_path=mm.poster_path,
                 release_date=mm.release_date, via=via, note=collection_name)


def franchise_view(session: Session, wikidata_id: str, user_id: int | None = None) -> FranchiseView | None:
    for view in franchise_views(session, user_id, only=wikidata_id):
        if view.wikidata_id == wikidata_id:
            return view
    return None
