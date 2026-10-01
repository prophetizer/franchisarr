"""The Franchise map (0.55.0): how a franchise hangs together -- its collections, its other films,
its shows and which show spun off which -- as data for static/franchise_map.js to draw.

Three shapes, all kept after a trial (michael, 0.55.1): lanes (a timeline lane per series), tree
(the franchise, its series, their titles) and constellation (a web to drag about). Each person's
pick is kept, like the look."""

from __future__ import annotations

from sqlmodel import Session, col, select

from app.models import CrossMediaMapping, ItemType, SpinoffMapping, TmdbCollection, TmdbCollectionMovie, UserPreference

SHAPES = ("lanes", "tree", "constellation")
KEY = "franchise_map"


def shape_of(session: Session, user_id: int | None) -> str:
    if user_id is None:
        return SHAPES[0]
    value = session.exec(select(UserPreference.value).where(
        col(UserPreference.user_id) == user_id, col(UserPreference.key) == KEY)).first()
    return value if value in SHAPES else SHAPES[0]


def set_shape(session: Session, user_id: int, value: str) -> str:
    from app.services.sorting import _save

    value = value if value in SHAPES else SHAPES[0]
    _save(session, user_id, KEY, value)
    return value


def build(session: Session, view) -> dict:  # noqa: ANN001 - a FranchiseView
    """The map's data: groups (each collection, other films, TV), a node per title, and the
    spin-off and continuation links between them. Plain JSON for the page."""
    from app.services.artwork import SMALL_CARD_SIZE, poster_url

    titles = ([(t, "owned") for t in view.owned_films + view.owned_shows]
              + [(t, "missing") for t in view.missing_films + view.missing_shows]
              + [(t, "upcoming") for t in view.upcoming_films])
    film_ids = [t.tmdb_id for t, _ in titles if t.item_type == ItemType.MOVIE.value]
    show_ids = {t.tmdb_id for t, _ in titles if t.item_type == ItemType.SHOW.value}

    # Which collection each film is in: one query for all of them. A film in two collections
    # (rare -- a boxset and its series) goes with the one met first.
    collection_of: dict[int, int] = {}
    for tmdb_id, collection_id in session.exec(select(TmdbCollectionMovie.tmdb_movie_id, TmdbCollectionMovie.collection_id)
                                               .where(col(TmdbCollectionMovie.tmdb_movie_id).in_(film_ids))).all():
        collection_of.setdefault(tmdb_id, collection_id)
    names = dict(session.exec(select(TmdbCollection.tmdb_collection_id, TmdbCollection.name)
                              .where(col(TmdbCollection.tmdb_collection_id).in_(set(collection_of.values())))).all())

    groups: list[dict] = []
    index: dict[tuple[str, int | None], int] = {}

    def group_for(kind: str, ref: int | None, name: str) -> int:
        if (kind, ref) not in index:
            index[(kind, ref)] = len(groups)
            groups.append({"name": name, "kind": kind,
                           "href": f"/collections/{ref}" if kind == "collection" else None})
        return index[(kind, ref)]

    nodes = []
    ordered = sorted(titles, key=lambda pair: (pair[0].year or 9999, pair[0].title.casefold()))
    for t, state in ordered:
        if t.item_type == ItemType.SHOW.value:
            group = group_for("shows", None, "TV")
        elif (cid := collection_of.get(t.tmdb_id)) is not None and cid in names:
            group = group_for("collection", cid, names[cid])
        else:
            group = group_for("films", None, "Other films")
        nodes.append({
            "id": f"{t.item_type}:{t.tmdb_id}", "title": t.title, "year": t.year, "type": t.item_type,
            "state": state, "group": group, "poster": poster_url(t.poster_path, SMALL_CARD_SIZE),
        })
    # Groups in the order a reader meets them: films before TV, each by its first title.
    first_year = {}
    for n in nodes:
        first_year.setdefault(n["group"], n["year"] or 9999)
    order = sorted(range(len(groups)), key=lambda g: (groups[g]["kind"] == "shows", groups[g]["kind"] == "films",
                                                      first_year.get(g, 9999)))
    renumber = {old: new for new, old in enumerate(order)}
    groups = [groups[old] for old in order]
    for n in nodes:
        n["group"] = renumber[n["group"]]

    present = {n["id"] for n in nodes}
    edges = []
    for source, target in session.exec(select(SpinoffMapping.source_show_tmdb_id, SpinoffMapping.spinoff_show_tmdb_id)
                                       .where(col(SpinoffMapping.source_show_tmdb_id).in_(show_ids))).all():
        a, b = f"show:{source}", f"show:{target}"
        if a in present and b in present and a != b:
            edges.append([a, b, "spin-off"])
    for s_type, s_id, t_type, t_id in session.exec(select(
            CrossMediaMapping.source_type, CrossMediaMapping.source_tmdb_id,
            CrossMediaMapping.target_type, CrossMediaMapping.target_tmdb_id)
            .where(col(CrossMediaMapping.source_tmdb_id).in_(film_ids + list(show_ids)))).all():
        a, b = f"{s_type}:{s_id}", f"{t_type}:{t_id}"
        if a in present and b in present and a != b:
            edges.append([a, b, "continuation"])
    edges = [list(e) for e in dict.fromkeys(tuple(e) for e in edges)]

    years = [n["year"] for n in nodes if n["year"]]
    return {"name": view.name, "groups": groups, "nodes": nodes, "edges": edges,
            "years": [min(years), max(years)] if years else None}
