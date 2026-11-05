"""Not interested, and not part of this collection, as folds with Undo (0.77.0; GLOSSARY.md: not
interested, folded). Both used to vanish with no way back."""

from __future__ import annotations

from fastapi.testclient import TestClient

from tests.test_movie_ui import BASE, COLLECTION, _seed_collection, client  # noqa: F401 - fixture


def test_not_interested_folds_on_the_page_and_undo_brings_it_back(client: TestClient) -> None:  # noqa: F811
    _seed_collection()
    client.post(f"{BASE}/collections/{COLLECTION}/dismiss/306")

    page = client.get(f"{BASE}/collections/{COLLECTION}").text
    assert "1 title you" in page and "not interested in" in page
    assert f'hx-post="{BASE}/not-interested/movie/306/undo"' in page

    undone = client.post(f"{BASE}/not-interested/movie/306/undo")
    assert undone.status_code == 200 and undone.headers["HX-Refresh"] == "true"
    page = client.get(f"{BASE}/collections/{COLLECTION}").text
    assert "not interested in" not in page and "Beverly Hills Cop III" in page


def test_not_part_of_this_collection_folds_for_administrators_with_undo(client: TestClient) -> None:  # noqa: F811
    _seed_collection()
    client.post(f"{BASE}/collections/{COLLECTION}/exclude/306")

    page = client.get(f"{BASE}/collections/{COLLECTION}").text
    assert "1 film marked not part of this collection" in page
    client.post(f"{BASE}/collections/{COLLECTION}/exclude/306/undo")
    assert "marked not part of this collection" not in client.get(f"{BASE}/collections/{COLLECTION}").text


def test_undo_refuses_an_unknown_kind_of_title(client: TestClient) -> None:  # noqa: F811
    assert client.post(f"{BASE}/not-interested/album/1/undo").status_code == 404


def test_a_wanted_film_has_its_section_and_no_add_button(client: TestClient) -> None:  # noqa: F811
    from sqlmodel import Session

    from app.db import get_engine
    from app.models import RadarrInstance, RadarrMovie

    _seed_collection()
    with Session(get_engine()) as session:
        instance = RadarrInstance(name="Radarr", url="http://radarr:7878", api_key="k" * 32)
        session.add(instance); session.commit(); session.refresh(instance)
        session.add(RadarrMovie(instance_id=instance.id, tmdb_id=306, title="III"))
        session.commit()

    page = client.get(f"{BASE}/collections/{COLLECTION}").text
    assert "<h2>Wanted</h2>" in page and f"{BASE}/add/306" not in page
