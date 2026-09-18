"""Jellyfin and Emby through one client.

Response shapes below are what the developer's own Jellyfin 10.11 and Emby 4.9 returned; the
two servers answered every request identically, which is why one client covers both.
"""

from __future__ import annotations

import pytest
import responses
from requests.exceptions import ConnectionError as RequestsConnectionError

from app.clients.emby_client import EmbyAuthError, EmbyClientError, EmbyLikeClient, _external_ids
from app.clients.media_server import MediaLibraryNotFoundError, MediaServerKind

URL = "http://jellyfin.test:8096"
KEY = "0123456789abcdef0123456789abcdef"


def _client(kind: MediaServerKind = MediaServerKind.JELLYFIN) -> EmbyLikeClient:
    return EmbyLikeClient(URL, KEY, kind=kind)


def _items(*items: dict, total: int | None = None) -> dict:
    return {"Items": list(items), "TotalRecordCount": total if total is not None else len(items)}


@responses.activate
def test_connection_names_the_server_and_flavour() -> None:
    responses.add(responses.GET, f"{URL}/System/Info",
                  json={"ServerName": "g00gsJellyFin", "Version": "10.11.11", "ProductName": "Jellyfin Server"})

    assert _client().test_connection() == "g00gsJellyFin (Jellyfin 10.11.11)"


@responses.activate
def test_emby_leaves_product_name_empty_and_that_is_fine() -> None:
    responses.add(responses.GET, f"{URL}/System/Info", json={"ServerName": "g00gsEMBY", "Version": "4.9.5.0", "ProductName": None})

    assert _client(MediaServerKind.EMBY).test_connection() == "g00gsEMBY (Emby 4.9.5.0)"


@responses.activate
def test_the_api_key_travels_in_the_header_both_servers_accept() -> None:
    responses.add(responses.GET, f"{URL}/System/Info", json={"ServerName": "x", "Version": "1"})

    _client().test_connection()

    assert responses.calls[0].request.headers["X-Emby-Token"] == KEY


@responses.activate
def test_only_movie_and_show_libraries_are_listed() -> None:
    """Emby lists collections and playlists as libraries; there is nothing in them to scan."""
    responses.add(responses.GET, f"{URL}/Library/VirtualFolders", json=[
        {"Name": "Movies", "CollectionType": "movies", "ItemId": "702521"},
        {"Name": "TV shows", "CollectionType": "tvshows", "ItemId": "802522"},
        {"Name": "Collections", "CollectionType": "boxsets", "ItemId": "107768"},
        {"Name": "Playlists", "CollectionType": "playlists", "ItemId": "821861"},
        {"Name": "Music", "CollectionType": "music", "ItemId": "1"},
    ])

    libraries = _client(MediaServerKind.EMBY).list_libraries()

    assert [(lib.title, lib.library_type, lib.key) for lib in libraries] == [
        ("Movies", "movie", "702521"), ("TV shows", "show", "802522")]


@responses.activate
def test_movies_come_with_their_provider_ids() -> None:
    responses.add(responses.GET, f"{URL}/Items", json=_items(
        {"Id": "a1", "Name": "28 Years Later", "ProductionYear": 2025,
         "ProviderIds": {"Tmdb": "1272837", "Imdb": "tt10548174", "Tvdb": "12345"}},
        {"Id": "a2", "Name": "Planes", "ProductionYear": 2013, "ProviderIds": {}},
    ))

    movies = list(_client().iter_movies("f137a2dd"))

    assert movies[0].item_key == "a1" and movies[0].year == 2025
    assert (movies[0].external_ids.tmdb_id, movies[0].external_ids.imdb_id, movies[0].external_ids.tvdb_id) == (1272837, "tt10548174", 12345)
    assert movies[1].has_external_ids is False
    assert movies[0].guids == (), "GUIDs are a Plex thing"
    query = responses.calls[0].request.url
    assert "ParentId=f137a2dd" in query and "IncludeItemTypes=Movie" in query and "Recursive=true" in query


@responses.activate
def test_reads_are_paged_until_the_total_is_reached() -> None:
    page1 = _items(*[{"Id": f"m{i}", "Name": f"Film {i}", "ProviderIds": {"Tmdb": str(i)}} for i in range(500)], total=750)
    page2 = _items(*[{"Id": f"m{i}", "Name": f"Film {i}", "ProviderIds": {"Tmdb": str(i)}} for i in range(500, 750)], total=750)
    responses.add(responses.GET, f"{URL}/Items", json=page1)
    responses.add(responses.GET, f"{URL}/Items", json=page2)

    movies = list(_client().iter_movies("x"))

    assert len(movies) == 750
    assert "StartIndex=500" in responses.calls[1].request.url


@responses.activate
def test_shows_are_series_items() -> None:
    responses.add(responses.GET, f"{URL}/Items", json=_items(
        {"Id": "s1", "Name": "86 EIGHTY-SIX", "ProductionYear": 2021, "ProviderIds": {"Tmdb": "100565", "Tvdb": "386517"}}))

    shows = list(_client().iter_shows("a656b907"))

    assert shows[0].external_ids.tmdb_id == 100565
    assert "IncludeItemTypes=Series" in responses.calls[0].request.url


def test_provider_id_keys_are_matched_case_insensitively() -> None:
    """Plugins write "Tmdb", "tmdb" and "TMDB"; all three are the same id."""
    ids = _external_ids({"TMDB": "1", "imdb": "tt2", "Tvdb": "3", "AniDb": "4", "Junk": "x"})
    assert (ids.tmdb_id, ids.imdb_id, ids.tvdb_id, ids.anidb_id) == (1, "tt2", 3, 4)
    assert _external_ids({"Tmdb": "not-a-number"}).tmdb_id is None


@responses.activate
def test_a_rejected_key_is_an_auth_error_in_the_servers_own_name() -> None:
    responses.add(responses.GET, f"{URL}/System/Info", status=401)
    with pytest.raises(EmbyAuthError, match="Emby rejected"):
        _client(MediaServerKind.EMBY).test_connection()


@responses.activate
def test_an_unreachable_server_never_quotes_the_key() -> None:
    responses.add(responses.GET, f"{URL}/System/Info", body=RequestsConnectionError("boom"))
    with pytest.raises(EmbyClientError) as exc:
        _client().test_connection()
    assert KEY not in str(exc.value) and "Could not reach Jellyfin" in str(exc.value)


@responses.activate
def test_a_missing_library_is_its_own_error() -> None:
    responses.add(responses.GET, f"{URL}/Items", status=404)
    with pytest.raises(MediaLibraryNotFoundError):
        list(_client().iter_movies("nope"))


# ------------------------------------------------------------------ sign-in


@responses.activate
def test_sign_in_returns_the_account_and_whether_it_administers() -> None:
    responses.add(responses.POST, f"{URL}/Users/AuthenticateByName", json={
        "User": {"Id": "u-1", "Name": "michael", "Policy": {"IsAdministrator": True}},
        "AccessToken": "session-token-never-kept"})

    account = _client().authenticate("michael", "pw")

    assert account == {"user_id": "u-1", "username": "michael", "is_admin": True}
    import json
    sent = json.loads(responses.calls[0].request.body)
    assert sent == {"Username": "michael", "Pw": "pw"}
    assert "Authorization" in responses.calls[0].request.headers, "the MediaBrowser auth header both servers require for this call"


@responses.activate
def test_a_wrong_password_is_an_auth_error() -> None:
    responses.add(responses.POST, f"{URL}/Users/AuthenticateByName", status=401)
    with pytest.raises(EmbyAuthError):
        _client().authenticate("michael", "wrong")
