"""Scan and gap-diff logic, over cached data only.

Covers the three separate reasons a film can be hidden -- owned, excluded, dismissed -- because
conflating them is the easy mistake, and each has different scope: owned is a fact, an exclusion
is shared data-quality, a dismissal is one person's preference.
"""

from __future__ import annotations

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

COLLECTION = 8354


def _own(session: Session, tmdb_id: int, title: str, **kwargs) -> LibraryItem:
    fields = {
        "plex_library_key": "1",
        "rating_key": str(tmdb_id),
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
    _collection(session, (90, "Beverly Hills Cop"), (9836, "Beverly Hills Cop II"),
                (9558, "Beverly Hills Cop III"))
    _own(session, 90, "Beverly Hills Cop")
    _own(session, 9836, "Beverly Hills Cop II")

    gaps = movie_gap_service.collections_with_gaps(session)

    assert len(gaps) == 1
    assert [m.tmdb_id for m in gaps[0].missing] == [9558]
    assert len(gaps[0].owned) == 2


def test_a_complete_collection_is_not_reported_as_a_gap(session: Session) -> None:
    _collection(session, (90, "Beverly Hills Cop"), (9836, "Beverly Hills Cop II"))
    _own(session, 90, "Beverly Hills Cop")
    _own(session, 9836, "Beverly Hills Cop II")

    assert movie_gap_service.collections_with_gaps(session) == []
    assert len(movie_gap_service.collection_gaps(session)) == 1, "still listed when asked for all"


def test_collections_you_own_nothing_from_are_not_suggested(session: Session) -> None:
    """Otherwise this becomes "every franchise on TMDb" rather than gaps in your own library."""
    _collection(session, (90, "Beverly Hills Cop"), (9836, "Beverly Hills Cop II"))

    assert movie_gap_service.collection_gaps(session) == []


# ------------------------------------------------------------------ the three ways to hide


def test_a_collection_exclude_hides_a_film_for_everyone(session: Session) -> None:
    """A TMDb data-quality correction: a re-release listed as a separate film."""
    _collection(session, (90, "Beverly Hills Cop"), (9558, "Beverly Hills Cop III"))
    _own(session, 90, "Beverly Hills Cop")
    session.add(CollectionExclude(tmdb_collection_id=COLLECTION, tmdb_movie_id=9558))
    session.commit()

    assert movie_gap_service.collections_with_gaps(session) == []


def test_a_dismissal_hides_a_film_only_for_that_user(session: Session) -> None:
    _collection(session, (90, "Beverly Hills Cop"), (9558, "Beverly Hills Cop III"))
    _own(session, 90, "Beverly Hills Cop")
    user = _user(session)
    session.add(
        DismissedItem(user_id=user.id, item_type=ItemType.MOVIE.value, tmdb_id=9558)
    )
    session.commit()

    assert movie_gap_service.collections_with_gaps(session, user.id) == []
    assert movie_gap_service.collections_with_gaps(session, user_id=None), (
        "another user should still see the gap"
    )


def test_an_exclusion_survives_a_collection_refresh(session: Session) -> None:
    """Technical challenge #13: re-fetching the collection must not resurrect an exclusion."""
    _collection(session, (90, "Beverly Hills Cop"), (9558, "Beverly Hills Cop III"))
    _own(session, 90, "Beverly Hills Cop")
    session.add(CollectionExclude(tmdb_collection_id=COLLECTION, tmdb_movie_id=9558))
    session.commit()

    # Simulate the refresh: members are replaced wholesale, exactly as _cache_collection does.
    for row in session.exec(select(TmdbCollectionMovie)).all():
        session.delete(row)
    session.delete(session.get(TmdbCollection, COLLECTION))
    session.commit()
    _collection(session, (90, "Beverly Hills Cop"), (9558, "Beverly Hills Cop III"))

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
    _collection(session, (90, "Beverly Hills Cop"), (9558, "Beverly Hills Cop III"))
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
    _collection(session, (90, "Beverly Hills Cop"), (9836, "Beverly Hills Cop II"))
    _own(session, 90, "Beverly Hills Cop")
    _own(session, 9836, "Beverly Hills Cop II", needs_review=True,
         match_source=MatchSource.TITLE.value, match_confidence=0.7)

    gaps = movie_gap_service.collections_with_gaps(session)

    assert [m.tmdb_id for m in gaps[0].missing] == [9836]


def test_items_needing_review_are_listed_rather_than_silently_dropped(session: Session) -> None:
    _own(session, 90, "Beverly Hills Cop", needs_review=True,
         match_source=MatchSource.TITLE.value, match_confidence=0.7)

    assert [i.title for i in movie_gap_service.items_needing_review(session)] == [
        "Beverly Hills Cop"
    ]


def test_unmatched_items_are_listed(session: Session) -> None:
    session.add(
        LibraryItem(plex_library_key="1", rating_key="x", title="Christmas 2019",
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
    responses.add(responses.GET, f"{TMDB_BASE_URL}/movie/9836", json={
        "id": 9836, "title": "Beverly Hills Cop II", "release_date": "1987-05-20",
        "belongs_to_collection": {"id": COLLECTION, "name": "Beverly Hills Cop Collection"}})
    responses.add(responses.GET, f"{TMDB_BASE_URL}/search/movie", json={"results": []})
    responses.add(responses.GET, f"{TMDB_BASE_URL}/collection/{COLLECTION}", json={
        "id": COLLECTION, "name": "Beverly Hills Cop Collection",
        "parts": [
            {"id": 90, "title": "Beverly Hills Cop", "release_date": "1984-12-05"},
            {"id": 9836, "title": "Beverly Hills Cop II", "release_date": "1987-05-20"},
            {"id": 9558, "title": "Beverly Hills Cop III", "release_date": "1994-05-25"},
        ]})

    session.add(IncludedLibrary(plex_library_key="1", plex_library_name="Movies",
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
    responses.add(responses.GET, f"{TMDB_BASE_URL}/movie/9836", status=401)
    responses.add(responses.GET, f"{TMDB_BASE_URL}/search/movie", json={"results": []})

    session.add(IncludedLibrary(plex_library_key="1", plex_library_name="Movies",
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
