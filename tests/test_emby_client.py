"""Jellyfin and Emby through one client.

Response shapes below are what the developer's own Jellyfin 10.11 and Emby 4.9 returned; the
two servers answered every request identically, which is why one client covers both.
"""

from __future__ import annotations

import json

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


USERS = [
    {"Id": "u-guest", "Name": "guest", "Policy": {"IsAdministrator": False}},
    {"Id": "u-admin", "Name": "michael", "Policy": {"IsAdministrator": True}},
]


def _users(users: list[dict] | None = None) -> None:
    """Listings are asked on behalf of a user, so /Users comes first in every item test."""
    responses.add(responses.GET, f"{URL}/Users", json=USERS if users is None else users)


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
def test_jellyfin_gets_the_key_in_its_authorization_header() -> None:
    """Jellyfin 12 answers X-Emby-Token with 401; its Authorization scheme works on 10.x too."""
    responses.add(responses.GET, f"{URL}/System/Info", json={"ServerName": "x", "Version": "1"})

    _client(MediaServerKind.JELLYFIN).test_connection()

    headers = responses.calls[0].request.headers
    assert f'Token="{KEY}"' in headers["Authorization"] and headers["Authorization"].startswith("MediaBrowser ")
    assert "X-Emby-Token" not in headers


@responses.activate
def test_emby_gets_the_key_in_x_emby_token() -> None:
    responses.add(responses.GET, f"{URL}/System/Info", json={"ServerName": "x", "Version": "1"})

    _client(MediaServerKind.EMBY).test_connection()

    headers = responses.calls[0].request.headers
    assert headers["X-Emby-Token"] == KEY and "Authorization" not in headers


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
    _users()
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
    query = responses.calls[1].request.url
    # Jellyfin gets camelCase parameters (Jellyfin 12 matches them case-sensitively).
    assert "parentId=f137a2dd" in query and "includeItemTypes=Movie" in query and "recursive=true" in query
    assert "userId=u-admin" in query, "no watched_user named: the first administrator"


@responses.activate
def test_reads_are_paged_until_the_total_is_reached() -> None:
    page1 = _items(*[{"Id": f"m{i}", "Name": f"Film {i}", "ProviderIds": {"Tmdb": str(i)}} for i in range(500)], total=750)
    page2 = _items(*[{"Id": f"m{i}", "Name": f"Film {i}", "ProviderIds": {"Tmdb": str(i)}} for i in range(500, 750)], total=750)
    _users()
    responses.add(responses.GET, f"{URL}/Items", json=page1)
    responses.add(responses.GET, f"{URL}/Items", json=page2)

    movies = list(_client().iter_movies("x"))

    assert len(movies) == 750
    assert "startIndex=500" in responses.calls[2].request.url


@responses.activate
def test_shows_are_series_items() -> None:
    _users()
    responses.add(responses.GET, f"{URL}/Items", json=_items(
        {"Id": "s1", "Name": "86 EIGHTY-SIX", "ProductionYear": 2021, "ProviderIds": {"Tmdb": "100565", "Tvdb": "386517"}}))

    shows = list(_client().iter_shows("a656b907"))

    assert shows[0].external_ids.tmdb_id == 100565
    assert "includeItemTypes=Series" in responses.calls[1].request.url


# ------------------------------------------------------------------ watched state


@responses.activate
def test_watched_state_comes_from_the_listing_user_data() -> None:
    """Shapes from a real Jellyfin: a played film, an unplayed one, a series half-way through
    (Played is only true once every episode is), and an item with no UserData at all."""
    _users()
    responses.add(responses.GET, f"{URL}/Items", json=_items(
        {"Id": "a", "Name": "Seen", "ProviderIds": {}, "UserData": {"Played": True, "PlayCount": 1}},
        {"Id": "b", "Name": "Unseen", "ProviderIds": {}, "UserData": {"Played": False, "PlayCount": 0}},
        {"Id": "c", "Name": "Started", "ProviderIds": {}, "RecursiveItemCount": 24,
         "UserData": {"Played": False, "UnplayedItemCount": 20, "PlayedPercentage": 16.6}},
        {"Id": "d", "Name": "Silent", "ProviderIds": {}},
    ))

    watched = [m.watched for m in _client().iter_movies("lib")]

    assert watched == [True, False, True, None]


@responses.activate
def test_a_named_watched_user_is_looked_up_by_name() -> None:
    _users()
    responses.add(responses.GET, f"{URL}/Items", json=_items())

    list(EmbyLikeClient(URL, KEY, watched_user="Guest").iter_movies("lib"))

    assert "userId=u-guest" in responses.calls[1].request.url


@responses.activate
def test_an_unknown_watched_user_leaves_the_state_unknown_rather_than_guessing() -> None:
    _users()
    responses.add(responses.GET, f"{URL}/Items", json=_items(
        {"Id": "a", "Name": "Seen", "ProviderIds": {}, "UserData": {"Played": True}}))

    movies = list(EmbyLikeClient(URL, KEY, watched_user="nobody").iter_movies("lib"))

    assert "UserId" not in responses.calls[1].request.url
    assert movies[0].watched is True, "if the server volunteers UserData anyway, it is used"


@responses.activate
def test_users_are_listed_once_per_client_not_per_page() -> None:
    _users()
    responses.add(responses.GET, f"{URL}/Items", json=_items())
    responses.add(responses.GET, f"{URL}/Items", json=_items())
    client = _client()

    list(client.iter_movies("a")); list(client.iter_shows("b"))

    assert [c.request.url.split("?")[0] for c in responses.calls].count(f"{URL}/Users") == 1


@responses.activate
def test_list_users_reports_who_administers() -> None:
    _users()

    users = _client().list_users()

    assert [(u["name"], u["is_admin"]) for u in users] == [("guest", False), ("michael", True)]


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


# ------------------------------------------------------------------ playlists


def _user_lookup() -> None:
    responses.add(responses.GET, f"{URL}/Users", json=[{"Name": "michael", "Id": "u1",
                                                         "Policy": {"IsAdministrator": True}}])


@responses.activate
def test_jellyfin_playlist_calls_use_camel_case_parameters() -> None:
    """Jellyfin 12 ignores `UserId` on some endpoints and answers 400 on others."""
    from urllib.parse import parse_qs, urlparse

    _user_lookup()
    responses.add(responses.GET, f"{URL}/Items", json={"Items": [
        {"Id": "m1", "PremiereDate": "1979-05-25T00:00:00Z"}, {"Id": "m2", "ProductionYear": 1986}]})
    responses.add(responses.GET, f"{URL}/Shows/s1/Episodes", json={"Items": [
        {"Id": "e2", "ParentIndexNumber": 1, "IndexNumber": 2},
        {"Id": "e1", "ParentIndexNumber": 1, "IndexNumber": 1, "PremiereDate": "2019-11-12T00:00:00Z"},
        {"Id": "e0", "ParentIndexNumber": 0, "IndexNumber": 1, "PremiereDate": "2019-01-01T00:00:00Z"}]})

    entries = _client(MediaServerKind.JELLYFIN).playlist_entries(["m1", "m2"], ["s1"])

    queries = [parse_qs(urlparse(c.request.url).query) for c in responses.calls if "/Users" not in c.request.url]
    assert all(not any(k[0].isupper() for k in q) for q in queries), queries
    by_id = {e.raw: e for e in entries}
    assert set(by_id) == {"m1", "m2", "e1", "e2"}, "specials left out"
    assert str(by_id["m2"].aired) == "1986-01-01" and str(by_id["e2"].aired) == "2019-11-12"


@responses.activate
@pytest.mark.parametrize("kind", [MediaServerKind.JELLYFIN, MediaServerKind.EMBY])
def test_replacing_a_playlist_deletes_old_copies_creates_and_adds_in_chunks(kind, monkeypatch) -> None:  # noqa: ANN001
    import app.clients.emby_client as ec

    monkeypatch.setattr(ec, "PLAYLIST_CHUNK", 2)
    _user_lookup()
    responses.add(responses.GET, f"{URL}/Items", json={"Items": [
        {"Id": "old1", "Name": "Alien (Franchisarr)"}, {"Id": "keep", "Name": "Alien"},
        {"Id": "old2", "Name": "Alien (Franchisarr)"}]})
    responses.add(responses.DELETE, f"{URL}/Items/old1")
    responses.add(responses.DELETE, f"{URL}/Items/old2")
    responses.add(responses.POST, f"{URL}/Playlists", json={"Id": "new"})
    responses.add(responses.POST, f"{URL}/Playlists/new/Items")

    _client(kind).replace_playlist("Alien (Franchisarr)", ["a", "b", "c", "d", "e"])

    methods = [(c.request.method, c.request.url.split("?")[0].replace(URL, "")) for c in responses.calls]
    assert ("DELETE", "/Items/old1") in methods and ("DELETE", "/Items/old2") in methods
    assert ("DELETE", "/Items/keep") not in methods, "only our own name"
    create = next(c for c in responses.calls if c.request.method == "POST" and c.request.url.split("?")[0].endswith("/Playlists"))
    if kind == MediaServerKind.JELLYFIN:
        assert json.loads(create.request.body)["Ids"] == ["a", "b"]
    else:
        assert "Ids=a%2Cb" in create.request.url
    adds = [c.request.url for c in responses.calls if "/Playlists/new/Items" in c.request.url]
    assert len(adds) == 2 and "ids=c%2cd" in adds[0].lower()


@responses.activate
def test_the_poster_goes_up_base64_encoded() -> None:
    import base64

    _user_lookup()
    responses.add(responses.GET, f"{URL}/Items", json={"Items": [{"Id": "p1", "Name": "Alien (Franchisarr)"}]})
    responses.add(responses.POST, f"{URL}/Items/p1/Images/Primary")

    assert _client(MediaServerKind.EMBY).set_playlist_poster("Alien (Franchisarr)", b"\xff\xd8jpeg") is True

    upload = responses.calls[-1].request
    assert base64.b64decode(upload.body) == b"\xff\xd8jpeg" and upload.headers["Content-Type"] == "image/jpeg"


@responses.activate
@pytest.mark.parametrize("kind", [MediaServerKind.JELLYFIN, MediaServerKind.EMBY])
def test_deleting_our_playlists_is_server_wide_and_never_touches_anyone_elses(kind) -> None:  # noqa: ANN001
    responses.add(responses.GET, f"{URL}/Items", json={"Items": [
        {"Id": "a", "Name": "Alien (Franchisarr)"}, {"Id": "mine", "Name": "Alien"},
        {"Id": "b", "Name": "Star Wars (Franchisarr)"}, {"Id": "c", "Name": "Franchisarr favourites"}]})
    responses.add(responses.DELETE, f"{URL}/Items/a")
    responses.add(responses.DELETE, f"{URL}/Items/b")

    assert _client(kind).playlists_ending(" (Franchisarr)") == ["Alien (Franchisarr)", "Star Wars (Franchisarr)"]
    assert _client(kind).delete_playlists(" (Franchisarr)") == ["Alien (Franchisarr)", "Star Wars (Franchisarr)"]

    deleted = [c.request.url.replace(URL, "") for c in responses.calls if c.request.method == "DELETE"]
    assert deleted == ["/Items/a", "/Items/b"]
    listing = next(c.request.url for c in responses.calls if c.request.method == "GET")
    assert "userid" not in listing.lower(), "every user's playlists, not just the watched-as user's"


# ------------------------------------------------------------------ playlist sync


@responses.activate
def test_sync_reads_a_playlists_films_and_episodes_in_order() -> None:
    _user_lookup()
    responses.add(responses.GET, f"{URL}/Items", json={"Items": [
        {"Id": "p1", "Name": "Road trip", "MediaType": "Video", "ChildCount": 3},
        {"Id": "p2", "Name": "Workout", "MediaType": "Audio", "ChildCount": 9}]})
    responses.add(responses.GET, f"{URL}/Playlists/p1/Items", json={"Items": [
        {"Id": "m1", "Type": "Movie", "Name": "Alien"},
        {"Id": "e1", "Type": "Episode", "SeriesId": "s1", "SeriesName": "Breaking Bad",
         "ParentIndexNumber": 2, "IndexNumber": 3},
        {"Id": "a1", "Type": "Audio", "Name": "A song"}]})
    client = _client(MediaServerKind.JELLYFIN)

    listing = client.list_playlists()
    items = client.playlist_items("p1")

    assert [(p.id, p.title, p.video, p.count) for p in listing] == [("p1", "Road trip", True, 3), ("p2", "Workout", False, 9)]
    assert [(i.item_type, i.key, i.show_key, i.season, i.episode) for i in items] == [
        ("movie", "m1", None, 0, 0), ("episode", "e1", "s1", 2, 3), ("other", "a1", None, 0, 0)]
    assert items[1].title == "Breaking Bad S02E03"


@responses.activate
def test_a_copy_is_created_without_touching_a_same_named_playlist() -> None:
    """replace_playlist deletes every playlist of its name server-wide -- fine for
    "(Franchisarr)" names, ruinous for a person's "Road trip". Sync creates by id instead."""
    _user_lookup()
    responses.add(responses.GET, f"{URL}/Items", json={"Items": [{"Id": "mine", "Name": "Road trip"}]})
    responses.add(responses.POST, f"{URL}/Playlists", json={"Id": "copy1"})

    new_id = _client(MediaServerKind.JELLYFIN).create_playlist("Road trip", ["a", "b"])

    assert new_id == "copy1"
    assert not any(c.request.method == "DELETE" for c in responses.calls)


@responses.activate
def test_deleting_a_copy_that_is_already_gone_is_not_an_error() -> None:
    _user_lookup()
    responses.add(responses.GET, f"{URL}/Items", json={"Items": []})

    _client(MediaServerKind.EMBY).delete_playlist_id("gone")

    assert not any(c.request.method == "DELETE" for c in responses.calls)
