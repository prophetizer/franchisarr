"""Scan and gap-diff logic, over cached data only.

Covers the three separate reasons a film can be hidden -- owned, excluded, dismissed -- because
conflating them is the easy mistake, and each has different scope: owned is a fact, an exclusion
is shared data-quality, a dismissal is one person's preference.
"""

from __future__ import annotations

from datetime import timedelta

import responses
from sqlmodel import Session, select

from app.clients.plex_client import PlexClient
from app.clients.tmdb_client import TMDB_BASE_URL, TmdbClient
from app.models import (
    CollectionExclude,
    DismissedItem,
    IncludedLibrary,
    ItemType,
    LibraryItem,
    MatchSource,
    TmdbCollection,
    TmdbCollectionMovie,
    TmdbMovie,
    User,
)
from app.services import movie_gap_service, scan_service

COLLECTION = 85861


def _own(session: Session, tmdb_id: int, title: str, **kwargs) -> LibraryItem:
    fields = {
        "library_key": "1",
        "item_key": str(tmdb_id),
        "item_type": ItemType.MOVIE.value,
        "title": title,
        "year": 1984,
        "tmdb_id": tmdb_id,
        "match_source": MatchSource.GUID.value,
        **kwargs,
    }
    item = LibraryItem(**fields)
    session.add(item)
    session.add(TmdbMovie(tmdb_id=tmdb_id, title=title, collection_id=COLLECTION))
    session.commit()
    return item


def _collection(session: Session, *members: tuple[int, str], release_date: str | None = None) -> None:
    """Members default to a long-past release date, i.e. films that actually exist."""
    session.add(TmdbCollection(tmdb_collection_id=COLLECTION, name="Beverly Hills Cop Collection"))
    for position, (tmdb_id, title) in enumerate(members):
        session.add(
            TmdbCollectionMovie(
                collection_id=COLLECTION,
                tmdb_movie_id=tmdb_id,
                title=title,
                release_year=1984 + position,
                release_date=release_date or f"{1984 + position}-06-01",
                position=position,
            )
        )
    session.commit()


def _user(session: Session) -> User:
    user = User(local_username="admin", is_admin=True)
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


# ------------------------------------------------------------------ the core diff


def test_a_partly_owned_collection_reports_what_is_missing(session: Session) -> None:
    _collection(session, (90, "Beverly Hills Cop"), (96, "Beverly Hills Cop II"),
                (306, "Beverly Hills Cop III"))
    _own(session, 90, "Beverly Hills Cop")
    _own(session, 96, "Beverly Hills Cop II")

    gaps = movie_gap_service.collections_with_gaps(session)

    assert len(gaps) == 1
    assert [m.tmdb_id for m in gaps[0].missing] == [306]
    assert len(gaps[0].owned) == 2


def test_a_complete_collection_is_not_reported_as_a_gap(session: Session) -> None:
    _collection(session, (90, "Beverly Hills Cop"), (96, "Beverly Hills Cop II"))
    _own(session, 90, "Beverly Hills Cop")
    _own(session, 96, "Beverly Hills Cop II")

    assert movie_gap_service.collections_with_gaps(session) == []
    assert len(movie_gap_service.collection_gaps(session)) == 1, "still listed when asked for all"


def test_collections_you_own_nothing_from_are_not_suggested(session: Session) -> None:
    """Otherwise this becomes "every franchise on TMDb" rather than gaps in your own library."""
    _collection(session, (90, "Beverly Hills Cop"), (96, "Beverly Hills Cop II"))

    assert movie_gap_service.collection_gaps(session) == []


# ------------------------------------------------------------------ the three ways to hide


def test_a_collection_exclude_hides_a_film_for_everyone(session: Session) -> None:
    """A TMDb data-quality correction: a re-release listed as a separate film."""
    _collection(session, (90, "Beverly Hills Cop"), (306, "Beverly Hills Cop III"))
    _own(session, 90, "Beverly Hills Cop")
    session.add(CollectionExclude(tmdb_collection_id=COLLECTION, tmdb_movie_id=306))
    session.commit()

    assert movie_gap_service.collections_with_gaps(session) == []


def test_a_dismissal_hides_a_film_only_for_that_user(session: Session) -> None:
    _collection(session, (90, "Beverly Hills Cop"), (306, "Beverly Hills Cop III"))
    _own(session, 90, "Beverly Hills Cop")
    user = _user(session)
    session.add(
        DismissedItem(user_id=user.id, item_type=ItemType.MOVIE.value, tmdb_id=306)
    )
    session.commit()

    assert movie_gap_service.collections_with_gaps(session, user.id) == []
    assert movie_gap_service.collections_with_gaps(session, user_id=None), (
        "another user should still see the gap"
    )


def test_an_exclusion_survives_a_collection_refresh(session: Session) -> None:
    """Technical challenge #13: re-fetching the collection must not resurrect an exclusion."""
    _collection(session, (90, "Beverly Hills Cop"), (306, "Beverly Hills Cop III"))
    _own(session, 90, "Beverly Hills Cop")
    session.add(CollectionExclude(tmdb_collection_id=COLLECTION, tmdb_movie_id=306))
    session.commit()

    # Simulate the refresh: members are replaced wholesale, exactly as _cache_collection does.
    for row in session.exec(select(TmdbCollectionMovie)).all():
        session.delete(row)
    session.delete(session.get(TmdbCollection, COLLECTION))
    session.commit()
    _collection(session, (90, "Beverly Hills Cop"), (306, "Beverly Hills Cop III"))

    assert movie_gap_service.collections_with_gaps(session) == []


# ------------------------------------------------------------------ unreleased films


def test_an_unreleased_sequel_is_not_reported_as_a_gap(session: Session) -> None:
    """On a real library, 155 of 382 reported gaps were films that don't exist yet, and 126 of
    239 collections had no released film missing at all. Reporting "Untitled Beetlejuice 3" as
    something to go and get is noise, not a gap."""
    _collection(session, (90, "Beverly Hills Cop"))
    session.add(
        TmdbCollectionMovie(
            collection_id=COLLECTION, tmdb_movie_id=9999, title="Beverly Hills Cop IV",
            release_year=2099, release_date="2099-01-01", position=1,
        )
    )
    session.commit()
    _own(session, 90, "Beverly Hills Cop")

    assert movie_gap_service.collections_with_gaps(session) == []

    everything = movie_gap_service.collection_gaps(session)
    assert [m.title for m in everything[0].upcoming] == ["Beverly Hills Cop IV"]
    assert everything[0].missing == ()


def test_a_film_with_no_release_date_counts_as_upcoming(session: Session) -> None:
    """TMDb carries announced-but-unscheduled entries. A film it cannot date is certainly not
    one you can obtain."""
    _collection(session, (90, "Beverly Hills Cop"))
    session.add(
        TmdbCollectionMovie(
            collection_id=COLLECTION, tmdb_movie_id=9999, title="Untitled Sequel",
            release_year=None, release_date=None, position=1,
        )
    )
    session.commit()
    _own(session, 90, "Beverly Hills Cop")

    assert movie_gap_service.collections_with_gaps(session) == []
    assert len(movie_gap_service.collection_gaps(session)[0].upcoming) == 1


def test_a_released_film_is_still_reported_alongside_upcoming_ones(session: Session) -> None:
    _collection(session, (90, "Beverly Hills Cop"), (306, "Beverly Hills Cop III"))
    session.add(
        TmdbCollectionMovie(
            collection_id=COLLECTION, tmdb_movie_id=9999, title="Beverly Hills Cop IV",
            release_year=2099, release_date="2099-01-01", position=2,
        )
    )
    session.commit()
    _own(session, 90, "Beverly Hills Cop")

    gap = movie_gap_service.collections_with_gaps(session)[0]

    assert [m.title for m in gap.missing] == ["Beverly Hills Cop III"]
    assert [m.title for m in gap.upcoming] == ["Beverly Hills Cop IV"]
    assert gap.total == 3


def test_a_film_released_today_counts_as_available(session: Session) -> None:
    import datetime

    today = datetime.date(2026, 6, 1)
    _collection(session, (90, "Beverly Hills Cop"))
    session.add(
        TmdbCollectionMovie(
            collection_id=COLLECTION, tmdb_movie_id=9999, title="Out Today",
            release_year=2026, release_date="2026-06-01", position=1,
        )
    )
    session.commit()
    _own(session, 90, "Beverly Hills Cop")

    gap = movie_gap_service.collections_with_gaps(session, today=today)[0]

    assert [m.title for m in gap.missing] == ["Out Today"]


# ------------------------------------------------------------------ unconfirmed matches


def test_an_unconfirmed_match_does_not_count_as_owned(session: Session) -> None:
    """A guess must not be able to hide a real gap by pretending you own something."""
    _collection(session, (90, "Beverly Hills Cop"), (96, "Beverly Hills Cop II"))
    _own(session, 90, "Beverly Hills Cop")
    _own(session, 96, "Beverly Hills Cop II", needs_review=True,
         match_source=MatchSource.TITLE.value, match_confidence=0.7)

    gaps = movie_gap_service.collections_with_gaps(session)

    assert [m.tmdb_id for m in gaps[0].missing] == [96]


def test_items_needing_review_are_listed_rather_than_silently_dropped(session: Session) -> None:
    _own(session, 90, "Beverly Hills Cop", needs_review=True,
         match_source=MatchSource.TITLE.value, match_confidence=0.7)

    assert [i.title for i in movie_gap_service.items_needing_review(session)] == [
        "Beverly Hills Cop"
    ]


def test_unmatched_items_are_listed(session: Session) -> None:
    session.add(
        LibraryItem(library_key="1", item_key="x", title="Christmas 2019",
                    item_type=ItemType.MOVIE.value)
    )
    session.commit()

    assert [i.title for i in movie_gap_service.unmatched_items(session)] == ["Christmas 2019"]


# ------------------------------------------------------------------ scanning


@responses.activate
def test_a_scan_populates_the_snapshot_and_the_cache(
    session: Session, fixtures_dir, monkeypatch
) -> None:
    """End to end over recorded Plex XML and TMDb JSON, with no live network."""
    plex_dir = fixtures_dir / "plex"
    for name, url in [
        ("root.xml", "http://plex.test:32400/"),
        ("library.xml", "http://plex.test:32400/library"),
        ("library_sections.xml", "http://plex.test:32400/library/sections"),
        ("section_1_movies.xml", "http://plex.test:32400/library/sections/1/all"),
    ]:
        responses.add(responses.GET, url, body=(plex_dir / name).read_text(),
                      content_type="application/xml")

    responses.add(responses.GET, f"{TMDB_BASE_URL}/movie/90", json={
        "id": 90, "title": "Beverly Hills Cop", "release_date": "1984-12-05",
        "belongs_to_collection": {"id": COLLECTION, "name": "Beverly Hills Cop Collection"}})
    responses.add(responses.GET, f"{TMDB_BASE_URL}/movie/96", json={
        "id": 96, "title": "Beverly Hills Cop II", "release_date": "1987-05-18",
        "belongs_to_collection": {"id": COLLECTION, "name": "Beverly Hills Cop Collection"}})
    responses.add(responses.GET, f"{TMDB_BASE_URL}/search/movie", json={"results": []})
    responses.add(responses.GET, f"{TMDB_BASE_URL}/collection/{COLLECTION}", json={
        "id": COLLECTION, "name": "Beverly Hills Cop Collection",
        "parts": [
            {"id": 90, "title": "Beverly Hills Cop", "release_date": "1984-12-05"},
            {"id": 96, "title": "Beverly Hills Cop II", "release_date": "1987-05-18"},
            {"id": 306, "title": "Beverly Hills Cop III", "release_date": "1994-05-24"},
        ]})

    session.add(IncludedLibrary(library_key="1", library_name="Movies",
                                library_type="movie", enabled=True))
    session.commit()

    summary = scan_service.scan_movie_libraries(
        session,
        PlexClient("http://plex.test:32400", "token"),
        TmdbClient("k" * 32, max_requests_per_second=10_000),
    )

    assert summary.items_seen == 3
    assert summary.matched == 2
    assert summary.unmatched == 1, "the fixture's unmatched film has no ids and no search hit"
    assert summary.collections_found == 1

    gaps = movie_gap_service.collections_with_gaps(session)
    assert [m.title for m in gaps[0].missing] == ["Beverly Hills Cop III"]


@responses.activate
def test_a_rejected_tmdb_key_stops_the_scan_instead_of_retrying_every_film(
    session: Session, fixtures_dir
) -> None:
    """A rejected key will be rejected for every remaining film.

    Carrying on meant one failing request per film: measured against a real 3,428-film library
    that was 130 seconds of pointless waiting and thousands of identical errors, to be told one
    thing that was knowable at the first call.
    """
    plex_dir = fixtures_dir / "plex"
    for name, url in [
        ("root.xml", "http://plex.test:32400/"),
        ("library.xml", "http://plex.test:32400/library"),
        ("library_sections.xml", "http://plex.test:32400/library/sections"),
        ("section_1_movies.xml", "http://plex.test:32400/library/sections/1/all"),
    ]:
        responses.add(responses.GET, url, body=(plex_dir / name).read_text(),
                      content_type="application/xml")

    # Every TMDb movie lookup is rejected. There are two matched films in the fixture, so a
    # non-aborting scan would make two calls; aborting makes one.
    responses.add(responses.GET, f"{TMDB_BASE_URL}/movie/90", status=401)
    responses.add(responses.GET, f"{TMDB_BASE_URL}/movie/96", status=401)
    responses.add(responses.GET, f"{TMDB_BASE_URL}/search/movie", json={"results": []})

    session.add(IncludedLibrary(library_key="1", library_name="Movies",
                                library_type="movie", enabled=True))
    session.commit()

    summary = scan_service.scan_movie_libraries(
        session,
        PlexClient("http://plex.test:32400", "token"),
        TmdbClient("k" * 32, max_requests_per_second=10_000),
    )

    movie_calls = [c for c in responses.calls if "/movie/" in c.request.url]
    assert len(movie_calls) == 1, "the second film must not be attempted with a dead key"
    assert summary.errors, "the failure must be reported, not swallowed"
    assert summary.collections_found == 0

    # The library snapshot is still useful: matching succeeded, only enrichment stopped.
    assert summary.matched == 2


def test_scanning_with_no_enabled_libraries_says_so(session: Session) -> None:
    summary = scan_service.scan_movie_libraries(
        session, PlexClient("http://plex.test:32400", "t"), TmdbClient("k" * 32)
    )

    assert summary.ok is False
    assert "No movie libraries are enabled" in summary.errors[0]


# ------------------------------------------------------------------ fanart enrichment


def _tmdb_collection_response(collection_id: int = COLLECTION) -> dict:
    return {
        "id": collection_id,
        "name": "Beverly Hills Cop Collection",
        "poster_path": "/collection.jpg",
        "backdrop_path": "/backdrop.jpg",
        "parts": [
            {"id": 90, "title": "Beverly Hills Cop", "release_date": "1984-12-05"},
            {"id": 9836, "title": "Beverly Hills Cop II", "release_date": "1987-05-20"},
        ],
    }


def _fanart_client(**kwargs):
    from app.clients.fanart_client import FanartClient

    return FanartClient("0123456789abcdef0123456789abcdef", max_requests_per_second=10_000,
                        **kwargs)


@responses.activate
def test_a_collection_takes_its_logo_from_the_earliest_film(session: Session) -> None:
    """fanart.tv has no collection endpoint, so the franchise wordmark comes from the film that
    established it. Measured on 70 real collections: the anchor film had a logo every time."""
    from app.clients.fanart_client import FANART_BASE_URL

    _own(session, 90, "Beverly Hills Cop")
    responses.add(responses.GET, f"{TMDB_BASE_URL}/movie/90",
                  json={"id": 90, "title": "Beverly Hills Cop",
                        "belongs_to_collection": {"id": COLLECTION, "name": "BHC"}})
    responses.add(responses.GET, f"{TMDB_BASE_URL}/collection/{COLLECTION}",
                  json=_tmdb_collection_response())
    # The 1984 film, not the 1987 one.
    responses.add(responses.GET, f"{FANART_BASE_URL}/movies/90",
                  json={"hdmovielogo": [{"lang": "en", "likes": "9",
                                         "url": "https://f/bhc-logo.png"}]})

    scan_service._cache_collections(
        session, TmdbClient("k", max_requests_per_second=10_000), timedelta(0),
        scan_service.ScanSummary(), fanart=_fanart_client(),
    )

    cached = session.get(TmdbCollection, COLLECTION)
    assert cached.logo_url == "https://f/bhc-logo.png"
    assert cached.backdrop_path == "/backdrop.jpg"


@responses.activate
def test_a_scan_without_a_fanart_key_still_caches_the_collection(session: Session) -> None:
    """Artwork is optional; no key is the default state, not a misconfiguration."""
    _own(session, 90, "Beverly Hills Cop")
    responses.add(responses.GET, f"{TMDB_BASE_URL}/movie/90",
                  json={"id": 90, "title": "Beverly Hills Cop",
                        "belongs_to_collection": {"id": COLLECTION, "name": "BHC"}})
    responses.add(responses.GET, f"{TMDB_BASE_URL}/collection/{COLLECTION}",
                  json=_tmdb_collection_response())

    scan_service._cache_collections(
        session, TmdbClient("k", max_requests_per_second=10_000), timedelta(0),
        scan_service.ScanSummary(), fanart=None,
    )

    cached = session.get(TmdbCollection, COLLECTION)
    assert cached is not None
    assert cached.logo_url is None


@responses.activate
def test_fanart_being_down_does_not_stop_the_scan(session: Session) -> None:
    from app.clients.fanart_client import FANART_BASE_URL

    _own(session, 90, "Beverly Hills Cop")
    responses.add(responses.GET, f"{TMDB_BASE_URL}/movie/90",
                  json={"id": 90, "title": "Beverly Hills Cop",
                        "belongs_to_collection": {"id": COLLECTION, "name": "BHC"}})
    responses.add(responses.GET, f"{TMDB_BASE_URL}/collection/{COLLECTION}",
                  json=_tmdb_collection_response())
    responses.add(responses.GET, f"{FANART_BASE_URL}/movies/90", status=500)

    summary = scan_service.ScanSummary()
    scan_service._cache_collections(
        session, TmdbClient("k", max_requests_per_second=10_000), timedelta(0), summary,
        fanart=_fanart_client(),
    )

    assert session.get(TmdbCollection, COLLECTION) is not None
    assert summary.errors == []  # a missing logo is not worth telling the user about


@responses.activate
def test_a_rejected_fanart_key_stops_it_being_asked_again(session: Session) -> None:
    """Same lesson as TMDb: a rejected key is rejected for every remaining collection, and
    finding that out once per collection is minutes of waiting to learn one thing."""
    from app.clients.fanart_client import FANART_BASE_URL

    _own(session, 90, "First")
    _own(session, 500, "Second")
    # _own files everything under COLLECTION; this one needs its own so there are two to fetch.
    session.get(TmdbMovie, 500).collection_id = 99
    session.commit()

    for tmdb_id, collection_id in ((90, COLLECTION), (500, 99)):
        responses.add(responses.GET, f"{TMDB_BASE_URL}/movie/{tmdb_id}",
                      json={"id": tmdb_id, "title": "x",
                            "belongs_to_collection": {"id": collection_id, "name": "c"}})
    responses.add(responses.GET, f"{TMDB_BASE_URL}/collection/{COLLECTION}",
                  json=_tmdb_collection_response())
    responses.add(responses.GET, f"{TMDB_BASE_URL}/collection/99",
                  json=_tmdb_collection_response(99))
    responses.add(responses.GET, f"{FANART_BASE_URL}/movies/90", status=401, json={})

    summary = scan_service.ScanSummary()
    scan_service._cache_collections(
        session, TmdbClient("k", max_requests_per_second=10_000), timedelta(0), summary,
        fanart=_fanart_client(),
    )

    fanart_calls = [c for c in responses.calls if "webservice.fanart.tv" in c.request.url]
    assert len(fanart_calls) == 1, "asked fanart again after the key was rejected"
    # Both collections still cached: artwork failing must not cost the actual feature.
    assert session.get(TmdbCollection, COLLECTION) is not None
    assert session.get(TmdbCollection, 99) is not None
    assert summary.errors, "a rejected key is worth telling the user about, once"


@responses.activate
def test_recaching_a_collection_whose_films_are_unchanged(session: Session) -> None:
    """The refetch path, with members that overlap -- which is every refetch in practice, since
    a collection's membership is the thing that barely changes.

    An ORM delete loop passes a test whose before/after ids differ and fails on real data, so
    this test's whole point is that the two sets are the same. Same trap as the Radarr cache
    refresh; this one only surfaced when a migration forced every collection to refetch at once.
    """
    _own(session, 90, "Beverly Hills Cop")
    responses.add(responses.GET, f"{TMDB_BASE_URL}/movie/90",
                  json={"id": 90, "title": "Beverly Hills Cop",
                        "belongs_to_collection": {"id": COLLECTION, "name": "BHC"}})
    responses.add(responses.GET, f"{TMDB_BASE_URL}/collection/{COLLECTION}",
                  json=_tmdb_collection_response())
    responses.add(responses.GET, f"{TMDB_BASE_URL}/collection/{COLLECTION}",
                  json=_tmdb_collection_response())

    tmdb = TmdbClient("k", max_requests_per_second=10_000)
    for _ in range(2):
        scan_service._cache_collections(
            session, tmdb, timedelta(0), scan_service.ScanSummary(),
        )

    members = session.exec(
        select(TmdbCollectionMovie).where(TmdbCollectionMovie.collection_id == COLLECTION)
    ).all()
    assert sorted(m.tmdb_movie_id for m in members) == [90, 9836], "members duplicated or lost"


@responses.activate
def test_a_film_dropped_from_a_collection_upstream_disappears(session: Session) -> None:
    """The reason members are replaced wholesale rather than merged."""
    _own(session, 90, "Beverly Hills Cop")
    responses.add(responses.GET, f"{TMDB_BASE_URL}/movie/90",
                  json={"id": 90, "title": "Beverly Hills Cop",
                        "belongs_to_collection": {"id": COLLECTION, "name": "BHC"}})
    responses.add(responses.GET, f"{TMDB_BASE_URL}/collection/{COLLECTION}",
                  json=_tmdb_collection_response())
    shrunk = _tmdb_collection_response()
    shrunk["parts"] = shrunk["parts"][:1]
    responses.add(responses.GET, f"{TMDB_BASE_URL}/collection/{COLLECTION}", json=shrunk)

    tmdb = TmdbClient("k", max_requests_per_second=10_000)
    for _ in range(2):
        scan_service._cache_collections(
            session, tmdb, timedelta(0), scan_service.ScanSummary(),
        )

    members = session.exec(
        select(TmdbCollectionMovie).where(TmdbCollectionMovie.collection_id == COLLECTION)
    ).all()
    assert [m.tmdb_movie_id for m in members] == [90]


# ------------------------------------------------------------------ ratings


def _rate(session: Session, tmdb_id: int, average: float, count: int = 500) -> None:
    from sqlmodel import col

    row = session.exec(
        select(TmdbCollectionMovie).where(col(TmdbCollectionMovie.tmdb_movie_id) == tmdb_id)
    ).one()
    row.vote_average, row.vote_count = average, count
    session.add(row)
    session.commit()


def _set_threshold(session: Session, value: str) -> None:
    from app.services.settings_service import SettingKey, set_setting

    set_setting(session, SettingKey.MIN_GAP_RATING, value)
    session.commit()


def test_a_low_rated_film_is_hidden_not_missing(session: Session) -> None:
    _own(session, 90, "Beverly Hills Cop")
    _collection(session, (90, "Beverly Hills Cop"), (96, "Beverly Hills Cop II"), (306, "III"))
    _rate(session, 96, 6.6)
    _rate(session, 306, 5.4)
    _set_threshold(session, "6")

    gap = movie_gap_service.collection_gaps(session)[0]

    assert [m.tmdb_id for m in gap.missing] == [96]
    assert [m.tmdb_id for m in gap.hidden] == [306]


def test_hidden_films_do_not_count_as_gaps(session: Session) -> None:
    """A collection whose only absence is a film the user has said isn't worth having is
    complete, as far as they are concerned -- the same rule as upcoming films."""
    _own(session, 90, "Beverly Hills Cop")
    _collection(session, (90, "Beverly Hills Cop"), (306, "III"))
    _rate(session, 306, 5.4)
    _set_threshold(session, "6")

    assert movie_gap_service.collections_with_gaps(session) == []


def test_a_film_with_too_few_votes_is_never_hidden(session: Session) -> None:
    """Unknown is not the same as bad. Every obscure film in every collection has a handful of
    votes, and a filter that hid them would hide most of what the app exists to find."""
    _own(session, 90, "Beverly Hills Cop")
    _collection(session, (90, "Beverly Hills Cop"), (306, "III"))
    _rate(session, 306, 2.0, count=4)
    _set_threshold(session, "6")

    gap = movie_gap_service.collection_gaps(session)[0]

    assert [m.tmdb_id for m in gap.missing] == [306]
    assert gap.missing[0].rating is None, "a four-vote average should not be shown as a rating"


def test_the_filter_is_off_by_default(session: Session) -> None:
    _own(session, 90, "Beverly Hills Cop")
    _collection(session, (90, "Beverly Hills Cop"), (306, "III"))
    _rate(session, 306, 1.0)

    gap = movie_gap_service.collection_gaps(session)[0]

    assert [m.tmdb_id for m in gap.missing] == [306]
    assert gap.hidden == ()


def test_a_bad_threshold_value_means_off(session: Session) -> None:
    _set_threshold(session, "lots")
    assert movie_gap_service.min_gap_rating(session) == 0.0
    _set_threshold(session, "40")
    assert movie_gap_service.min_gap_rating(session) == 10.0


def test_collections_are_led_by_their_best_missing_film(session: Session) -> None:
    """The order that answers "what's worth getting?" rather than "what starts with A?"."""
    _own(session, 90, "Beverly Hills Cop")
    _collection(session, (90, "Beverly Hills Cop"), (96, "Beverly Hills Cop II"))
    _rate(session, 96, 6.6)
    # A second collection, alphabetically first, with a worse gap.
    session.add(TmdbCollection(tmdb_collection_id=2, name="Aardvark Collection"))
    session.add(TmdbCollectionMovie(collection_id=2, tmdb_movie_id=500, title="Aardvark",
                                    release_year=1990, release_date="1990-01-01", position=0))
    session.add(TmdbCollectionMovie(collection_id=2, tmdb_movie_id=501, title="Aardvark 2",
                                    release_year=1992, release_date="1992-01-01", position=1,
                                    vote_average=4.1, vote_count=900))
    session.add(TmdbMovie(tmdb_id=500, title="Aardvark", collection_id=2))
    session.add(LibraryItem(library_key="1", item_key="500", item_type="movie",
                            title="Aardvark", year=1990, tmdb_id=500, match_source="guid"))
    session.commit()

    by_rating = [g.name for g in movie_gap_service.collections_with_gaps(session)]
    by_name = [g.name for g in movie_gap_service.collections_with_gaps(session, sort="name")]

    assert by_rating == ["Beverly Hills Cop Collection", "Aardvark Collection"]
    assert by_name == ["Aardvark Collection", "Beverly Hills Cop Collection"]


def test_unrated_collections_sort_after_rated_ones(session: Session) -> None:
    """A list led by films nobody has scored would bury the ones people actually want."""
    _own(session, 90, "Beverly Hills Cop")
    _collection(session, (90, "Beverly Hills Cop"), (96, "Beverly Hills Cop II"))  # no votes
    session.add(TmdbCollection(tmdb_collection_id=2, name="Zebra Collection"))
    session.add(TmdbCollectionMovie(collection_id=2, tmdb_movie_id=500, title="Zebra",
                                    release_year=1990, release_date="1990-01-01", position=0))
    session.add(TmdbCollectionMovie(collection_id=2, tmdb_movie_id=501, title="Zebra 2",
                                    release_year=1992, release_date="1992-01-01", position=1,
                                    vote_average=5.0, vote_count=900))
    session.add(TmdbMovie(tmdb_id=500, title="Zebra", collection_id=2))
    session.add(LibraryItem(library_key="1", item_key="500", item_type="movie",
                            title="Zebra", year=1990, tmdb_id=500, match_source="guid"))
    session.commit()

    names = [g.name for g in movie_gap_service.collections_with_gaps(session)]

    assert names == ["Zebra Collection", "Beverly Hills Cop Collection"]
