"""Keeps contrib/theme-park/franchisarr-base.css honest.

That file lives in someone else's repository once submitted, so nothing else would notice if a
class here were renamed — the component would simply stop being themed, silently, for everyone
using it. These tests fail instead.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.auth.local_admin import create_local_admin
from app.db import get_engine
from app.models import (
    ItemType,
    LibraryItem,
    MatchSource,
    TmdbCollection,
    TmdbCollectionMovie,
    TmdbMovie,
)
from app.templating import STATIC_DIR
from tests.conftest import ensure_server

BASE = "/franchisarr"
PASSWORD = "s3cret-passphrase"
COLLECTION = 85861

BASE_CSS = Path(__file__).resolve().parents[1] / "contrib" / "theme-park" / "franchisarr-base.css"


@pytest.fixture
def client(app_factory):
    module = app_factory(BASE)
    with TestClient(module.app, follow_redirects=False) as test_client:
        with Session(get_engine()) as session:
            create_local_admin(session, "admin", PASSWORD)
            session.add(TmdbCollection(tmdb_collection_id=COLLECTION, name="A Collection"))
            for position, (tmdb_id, title) in enumerate([(90, "Owned"), (96, "Missing")]):
                session.add(TmdbCollectionMovie(
                    collection_id=COLLECTION, tmdb_movie_id=tmdb_id, title=title,
                    release_year=1984 + position, release_date=f"{1984 + position}-06-01",
                    position=position))
            session.add(LibraryItem(server_id=ensure_server(session), library_key="1", item_key="1",
                                    item_type=ItemType.MOVIE.value, title="Owned", year=1984,
                                    tmdb_id=90, match_source=MatchSource.GUID.value))
            session.add(TmdbMovie(tmdb_id=90, title="Owned", collection_id=COLLECTION))
            session.commit()
        test_client.post(f"{BASE}/login", data={"username": "admin", "password": PASSWORD})
        yield test_client


def _targeted_classes() -> set[str]:
    css = BASE_CSS.read_text()
    body = css[css.index("Franchisarr's own components"):]
    return set(re.findall(r"\.([a-z][a-z0-9-]+)", body))


def test_the_base_stylesheet_exists() -> None:
    assert BASE_CSS.is_file()


def test_every_class_it_targets_still_exists_in_the_app() -> None:
    """A rename in the app would otherwise silently unstyle that component for every user of the
    stylesheet, with nothing failing anywhere.

    Checked against the templates rather than a sample of rendered pages: several of these
    classes are conditional -- an error notice only appears when something failed -- and a page
    sample would report those as missing.
    """
    templates = Path(__file__).resolve().parents[1] / "app" / "templates"
    markup = "".join(
        path.read_text() for path in templates.rglob("*.html")
    ) + (STATIC_DIR / "app.css").read_text()

    missing = [name for name in _targeted_classes() if name not in markup]

    assert missing == [], f"the base stylesheet targets classes the app no longer uses: {missing}"


def test_it_sets_the_same_pico_variables_the_built_in_adapter_does() -> None:
    """The two should not drift: someone using the base stylesheet should get the same result as
    someone relying on the app's own copy."""
    adapter = (STATIC_DIR / "theme-adapter.css").read_text()
    base = BASE_CSS.read_text()

    adapter_vars = set(re.findall(r"(--pico-[a-z0-9-]+):", adapter))
    base_vars = set(re.findall(r"(--pico-[a-z0-9-]+):", base))

    missing = adapter_vars - base_vars
    assert missing == set(), f"the base stylesheet doesn't map: {sorted(missing)}"


def test_it_needs_no_important_declarations() -> None:
    """Franchisarr paints from variables, so there is nothing to fight. An !important creeping in
    would mean something had started hardcoding a colour."""
    css = BASE_CSS.read_text()
    # Strip comments first -- the header explains why none are needed, and would match itself.
    body = re.sub(r"/\*.*?\*/", "", css, flags=re.S)

    assert "!important" not in body


def test_it_uses_theme_park_variables_rather_than_literal_colours() -> None:
    css = BASE_CSS.read_text()
    body = css[css.index(":root"):]
    literals = re.findall(r":\s*(#[0-9a-fA-F]{3,8})\s*;", body)

    assert literals == [], f"literal colours in the base stylesheet: {literals}"
