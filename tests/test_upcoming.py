"""Upcoming films in owned franchises, and what a scan says about their release dates.

The diff is the part that has to be exactly right. Too eager and it re-announces forty sequels
every night, which is how people learn to mute the channel; too quiet and the one moment worth
knowing about -- a film getting its date -- goes by unmentioned.
"""

from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.auth.local_admin import create_local_admin
from app.db import get_engine

from app.models import (
    IncludedLibrary, ItemType, LibraryItem, MatchSource, TmdbCollection, TmdbCollectionMovie,
    TmdbMovie, UpcomingWatch,
)
from app.services import notifier, upcoming_service

TODAY = date(2026, 9, 15)
COLLECTION = 2150  # Shrek
BASE = "/franchisarr"
PASSWORD = "s3cret-passphrase"


@pytest.fixture
def client(app_factory):
    module = app_factory(BASE)
    with TestClient(module.app, follow_redirects=False) as test_client:
        with Session(get_engine()) as session:
            create_local_admin(session, "admin", PASSWORD)
            session.add(IncludedLibrary(library_key="1", library_name="Movies",
                                        library_type="movie", enabled=True))
            session.commit()
        test_client.post(f"{BASE}/login", data={"username": "admin", "password": PASSWORD})
        yield test_client


def _franchise(session: Session, *films: tuple[int, str, str | None]) -> None:
    """Own the first film; the rest are members with the given release dates."""
    session.add(TmdbCollection(tmdb_collection_id=COLLECTION, name="Shrek Collection"))
    for position, (tmdb_id, title, released) in enumerate(films):
        session.add(TmdbCollectionMovie(
            collection_id=COLLECTION, tmdb_movie_id=tmdb_id, title=title,
            release_year=int(released[:4]) if released else None, release_date=released,
            position=position,
        ))
    owned_id, owned_title, _ = films[0]
    session.add(TmdbMovie(tmdb_id=owned_id, title=owned_title, collection_id=COLLECTION))
    session.add(LibraryItem(library_key="1", item_key=str(owned_id),
                            item_type=ItemType.MOVIE.value, title=owned_title, year=2001,
                            tmdb_id=owned_id, match_source=MatchSource.GUID.value))
    session.commit()


def _redate(session: Session, tmdb_id: int, released: str | None) -> None:
    from sqlmodel import col

    row = session.exec(select(TmdbCollectionMovie)
                       .where(col(TmdbCollectionMovie.tmdb_movie_id) == tmdb_id)).one()
    row.release_date = released
    row.release_year = int(released[:4]) if released else None
    session.add(row)
    session.commit()


# ------------------------------------------------------------------ the list


def test_upcoming_lists_announced_films_soonest_first(session: Session) -> None:
    _franchise(session,
               (808, "Shrek", "2001-05-18"),
               (5, "Shrek 5", "2027-06-30"),
               (6, "Shrek 6", None),
               (7, "Puss in Boots 3", "2026-12-25"))

    films = upcoming_service.upcoming_films(session, today=TODAY)

    assert [f.title for f in films] == ["Puss in Boots 3", "Shrek 5", "Shrek 6"]
    assert films[0].days_until(TODAY) == 101
    assert films[2].days_until(TODAY) is None
    assert films[0].owned_count == 1 and films[0].total_count == 4


def test_a_released_film_is_a_gap_not_an_upcoming_one(session: Session) -> None:
    _franchise(session, (808, "Shrek", "2001-05-18"), (2, "Shrek 2", "2004-05-19"))

    assert upcoming_service.upcoming_films(session, today=TODAY) == []


def test_month_labels_group_dated_films_and_gather_undated_ones(session: Session) -> None:
    _franchise(session, (808, "Shrek", "2001-05-18"),
               (5, "Shrek 5", "2027-06-30"), (6, "Shrek 6", None))

    labels = [f.month_label for f in upcoming_service.upcoming_films(session, today=TODAY)]

    assert labels == ["June 2027", "No date yet"]


# ------------------------------------------------------------------ the diff


def test_the_first_sighting_is_recorded_but_not_news(session: Session) -> None:
    """On a first scan this is every announced sequel in the library at once."""
    _franchise(session, (808, "Shrek", "2001-05-18"), (5, "Shrek 5", "2027-06-30"))

    events = upcoming_service.record_and_diff(
        session, upcoming_service.upcoming_films(session, today=TODAY))

    assert events == []
    assert session.get(UpcomingWatch, 5).release_date == "2027-06-30"


def test_a_film_that_gains_a_date_is_news(session: Session) -> None:
    """The moment this feature exists for."""
    _franchise(session, (808, "Shrek", "2001-05-18"), (5, "Shrek 5", None))
    upcoming_service.record_and_diff(session, upcoming_service.upcoming_films(session, today=TODAY))

    _redate(session, 5, "2027-06-30")
    events = upcoming_service.record_and_diff(
        session, upcoming_service.upcoming_films(session, today=TODAY))

    assert [(e.kind, e.film.title) for e in events] == [("dated", "Shrek 5")]
    assert events[0].detail == "Shrek Collection · 2027-06-30"


def test_a_date_that_moves_is_news(session: Session) -> None:
    _franchise(session, (808, "Shrek", "2001-05-18"), (5, "Shrek 5", "2027-06-30"))
    upcoming_service.record_and_diff(session, upcoming_service.upcoming_films(session, today=TODAY))

    _redate(session, 5, "2027-12-23")
    events = upcoming_service.record_and_diff(
        session, upcoming_service.upcoming_films(session, today=TODAY))

    assert [e.kind for e in events] == ["moved"]
    assert events[0].detail == "Shrek Collection · 2027-06-30 → 2027-12-23"


def test_an_unchanged_date_is_not_news_again(session: Session) -> None:
    """The nightly-re-announcement failure mode."""
    _franchise(session, (808, "Shrek", "2001-05-18"), (5, "Shrek 5", "2027-06-30"))
    for _ in range(3):
        events = upcoming_service.record_and_diff(
            session, upcoming_service.upcoming_films(session, today=TODAY))

    assert events == []


def test_losing_a_date_is_not_announced_but_regaining_one_is(session: Session) -> None:
    """TMDb data flaps. A date vanishing is usually an edit in progress, not a cancellation;
    but when it comes back it is a date the user has not been told about."""
    _franchise(session, (808, "Shrek", "2001-05-18"), (5, "Shrek 5", "2027-06-30"))
    upcoming_service.record_and_diff(session, upcoming_service.upcoming_films(session, today=TODAY))

    _redate(session, 5, None)
    assert upcoming_service.record_and_diff(
        session, upcoming_service.upcoming_films(session, today=TODAY)) == []

    _redate(session, 5, "2027-06-30")
    events = upcoming_service.record_and_diff(
        session, upcoming_service.upcoming_films(session, today=TODAY))
    assert [e.kind for e in events] == ["dated"]


def test_a_film_that_is_released_leaves_the_watch_table(session: Session) -> None:
    """From here it is an ordinary gap and seen_gaps takes over."""
    _franchise(session, (808, "Shrek", "2001-05-18"), (5, "Shrek 5", "2027-06-30"))
    upcoming_service.record_and_diff(session, upcoming_service.upcoming_films(session, today=TODAY))

    upcoming_service.record_and_diff(
        session, upcoming_service.upcoming_films(session, today=date(2027, 7, 1)))

    assert session.get(UpcomingWatch, 5) is None


# ------------------------------------------------------------------ the notification


def test_release_dates_reach_every_webhook_format() -> None:
    report = notifier.ScanReport(release_dates=[
        notifier.NewItem(item_type="movie", tmdb_id=5, title="Shrek 5",
                         detail="Shrek Collection · 2027-06-30"),
    ])

    assert report.summary() == "1 release date"
    generic = notifier.build_generic(report)
    assert generic["release_dates"][0]["title"] == "Shrek 5"
    assert "Release dates (1)" in str(notifier.build_discord(report))
    assert "Release dates (1)" in str(notifier.build_slack(report))


def test_the_summary_reads_as_a_sentence_with_three_kinds() -> None:
    report = notifier.ScanReport(
        new_movies=[notifier.NewItem("movie", 1, "A")],
        new_shows=[notifier.NewItem("show", 2, "B")],
        release_dates=[notifier.NewItem("movie", 3, "C")],
    )

    assert report.summary() == "1 missing film, 1 spin-off and 1 release date"


# ------------------------------------------------------------------ the page


def _seed_page(session: Session) -> None:
    _franchise(session, (808, "Shrek", "2001-05-18"),
               (5, "Shrek 5", "2027-06-30"), (6, "Shrek 6", None))


def test_the_upcoming_page_lists_by_month_with_undated_last(client: TestClient) -> None:
    with Session(get_engine()) as session:
        _seed_page(session)

    body = client.get("/franchisarr/upcoming").text

    assert "June 2027" in body and "No date yet" in body
    assert body.index("June 2027") < body.index("No date yet")
    assert "you have 1 of 3" in body
    assert 'href="/franchisarr/collections/2150"' in body


def test_the_home_page_counts_what_is_coming(client: TestClient) -> None:
    with Session(get_engine()) as session:
        _seed_page(session)

    body = " ".join(client.get("/franchisarr/").text.split())

    assert "2 announced films in franchises you own" in body
