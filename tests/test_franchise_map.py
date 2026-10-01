"""The Franchise map (0.55.0): its groups, its links, and the shape each person picks."""

from __future__ import annotations

import json

from fastapi.testclient import TestClient
from sqlmodel import Session

from app.db import get_engine
from app.models import SpinoffMapping, TmdbCollection, TmdbCollectionMovie
from app.services import franchise_map, franchise_service
from tests.test_franchises import BASE, TREK, _franchise, _own_film, _own_show, client  # noqa: F401 - fixture


def _trek(session: Session) -> None:
    session.add(TmdbCollection(tmdb_collection_id=151, name="Star Trek: The Original Series Collection"))
    for position, (tmdb_id, title) in enumerate([(152, "The Motion Picture"), (154, "Wrath of Khan")]):
        session.add(TmdbCollectionMovie(collection_id=151, tmdb_movie_id=tmdb_id, title=title,
                                        release_year=1979 + position * 3, release_date=f"{1979 + position * 3}-06-01",
                                        position=position))
    _own_film(session, 154, "Wrath of Khan", collection_id=151)
    _own_show(session, 253, "The Original Series")
    _own_show(session, 655, "The Next Generation")
    session.add(SpinoffMapping(source_show_tmdb_id=253, spinoff_show_tmdb_id=655))
    _franchise(session, ("movie", 154, "Wrath of Khan"), ("movie", 152, "The Motion Picture"),
               ("movie", 999, "A Fan Film"), ("show", 253, "The Original Series"), ("show", 655, "The Next Generation"))


def _map(session: Session) -> dict:
    return franchise_map.build(session, franchise_service.franchise_view(session, TREK))


def test_collections_first_then_other_films_then_tv(session: Session) -> None:
    _trek(session)

    found = _map(session)

    assert [g["name"] for g in found["groups"]] == ["Star Trek: The Original Series Collection", "Other films", "TV"]
    assert found["groups"][0]["href"] == "/collections/151" and found["groups"][2]["href"] is None
    by_title = {n["title"]: n for n in found["nodes"]}
    assert by_title["Wrath of Khan"]["state"] == "owned" and by_title["The Motion Picture"]["state"] == "missing"
    assert by_title["The Motion Picture"]["group"] == 0, "a missing film still sits with its collection"
    assert by_title["A Fan Film"]["group"] == 1 and by_title["The Next Generation"]["group"] == 2


def test_a_spin_off_is_a_link_between_the_two_shows(session: Session) -> None:
    _trek(session)

    assert _map(session)["edges"] == [["show:253", "show:655", "spin-off"]]


def test_the_shape_is_each_persons_and_defaults_to_lanes(session: Session) -> None:
    from app.auth.local_admin import create_local_admin

    me = create_local_admin(session, "admin", "s3cret-passphrase").id
    assert franchise_map.shape_of(session, me) == "lanes"
    assert franchise_map.set_shape(session, me, "constellation") == "constellation"
    session.commit()
    assert franchise_map.shape_of(session, me) == "constellation"
    assert franchise_map.set_shape(session, me, "pie chart") == "lanes", "only the three on trial"
    assert franchise_map.shape_of(session, me + 1) == "lanes"


def test_the_page_carries_the_map_and_remembers_the_shape(client: TestClient) -> None:  # noqa: F811
    with Session(get_engine()) as session:
        _trek(session)

    page = client.get(f"{BASE}/franchises/{TREK}").text
    assert 'class="fm-canvas" data-shape="lanes"' in page and f'data-base="{BASE}"' in page
    raw = page.split('<script type="application/json" class="fm-data">', 1)[1].split("</script>", 1)[0]
    assert json.loads(raw)["name"] == "Star Trek"
    assert "franchise_map.js" in page

    assert client.post(f"{BASE}/preferences/map-shape", data={"shape": "tree"}).status_code == 204
    assert 'class="fm-canvas" data-shape="tree"' in client.get(f"{BASE}/franchises/{TREK}").text
