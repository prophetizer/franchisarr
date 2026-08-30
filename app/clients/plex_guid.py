"""Plex GUID -> external ID parsing (PROJECT_PLAN.md technical challenge #1).

Deliberately I/O-free. Every format quirk a real library throws at us gets fixed here, in pure
functions with a table-driven test, rather than somewhere that needs a Plex server to reproduce.

Plex exposes external IDs two different ways depending on the agent that matched the item:

*New agents* (Plex Movie / Plex TV Series) set the item's own ``guid`` to an opaque, Plex-internal
``plex://movie/<hash>`` and put the useful IDs in child ``<Guid id="tmdb://..."/>`` elements.

*Legacy agents* have no child elements at all -- the ID is encoded in the item's ``guid`` itself,
in a per-agent scheme, sometimes with trailing season/episode path segments and a ``?lang=``
query. HAMA (the community anime agent) additionally namespaces its body, which matters for
anyone running a separate anime library.

Anything unrecognised resolves to no IDs rather than raising: an unmatched item, a home video, or
an agent we've never seen must not break a scan of 3,600 movies.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass

_GUID_RE = re.compile(r"^(?P<scheme>[A-Za-z0-9_.\-]+)://(?P<body>.*)$")
_IMDB_RE = re.compile(r"^tt\d+$", re.IGNORECASE)

#: Agent/scheme -> the ID namespace its body contains.
_DIRECT_SCHEMES: dict[str, str] = {
    "tmdb": "tmdb",
    "themoviedb": "tmdb",
    "com.plexapp.agents.tmdb": "tmdb",
    "com.plexapp.agents.themoviedb": "tmdb",
    "imdb": "imdb",
    "com.plexapp.agents.imdb": "imdb",
    "tvdb": "tvdb",
    "thetvdb": "tvdb",
    "com.plexapp.agents.tvdb": "tvdb",
    "com.plexapp.agents.thetvdb": "tvdb",
    "anidb": "anidb",
    "com.plexapp.agents.anidb": "anidb",
}

#: Agents whose body is prefixed with the namespace it belongs to, e.g. ``tvdb-73244``.
_PREFIXED_SCHEMES = frozenset({"com.plexapp.agents.hama"})

#: The Kodi NFO agents put a bare IMDb or TMDb/TVDb id in the body with no namespace, so the
#: namespace has to be inferred from the value's shape and from which of the two agents it is.
_NFO_MOVIE_SCHEMES = frozenset({"com.plexapp.agents.xbmcnfo"})
_NFO_TV_SCHEMES = frozenset({"com.plexapp.agents.xbmcnfotv"})

#: Recognised but carrying no external ID: Plex-internal identifiers, unmatched items, and
#: local-media-only matches. Listed explicitly so they're distinguishable from an agent we simply
#: don't know about yet -- the latter is worth a log line, these are not.
_ID_FREE_SCHEMES = frozenset(
    {
        "plex",
        "local",
        "com.plexapp.agents.none",
        "com.plexapp.agents.localmedia",
        "com.plexapp.agents.lambda",
        # The new-agent equivalents. An unmatched item in a modern library reports
        # tv.plex.agents.none rather than the com.plexapp.agents.none a legacy library uses --
        # confirmed against a real 4,300-item server, where a "Sets" library of DJ sets produced
        # 209 of them. Both spellings coexist on the same server, so both are needed.
        "tv.plex.agents.none",
        "tv.plex.agents.localmedia",
    }
)

#: Namespaces we deliberately ignore (music, and anything else Plex may add).
_IGNORED_SCHEMES = frozenset({"mbid", "musicbrainz"})


@dataclass(frozen=True)
class ExternalIds:
    """External identifiers resolved for one Plex item. Any field may be None."""

    tmdb_id: int | None = None
    imdb_id: str | None = None
    tvdb_id: int | None = None
    anidb_id: int | None = None

    @property
    def is_empty(self) -> bool:
        return not any((self.tmdb_id, self.imdb_id, self.tvdb_id, self.anidb_id))

    def merge(self, other: ExternalIds) -> ExternalIds:
        """Combine two results, keeping whatever is already set. Used to fold several GUIDs
        from one item together; first writer wins, so callers should pass the more trustworthy
        source first."""
        return ExternalIds(
            tmdb_id=self.tmdb_id if self.tmdb_id is not None else other.tmdb_id,
            imdb_id=self.imdb_id if self.imdb_id is not None else other.imdb_id,
            tvdb_id=self.tvdb_id if self.tvdb_id is not None else other.tvdb_id,
            anidb_id=self.anidb_id if self.anidb_id is not None else other.anidb_id,
        )


def _split(raw: str) -> tuple[str, str] | None:
    """Split a GUID into (lowercased scheme, body), stripping the ``?lang=en`` query and any
    trailing ``/season/episode`` path segments legacy TV GUIDs carry."""
    match = _GUID_RE.match(raw.strip())
    if match is None:
        return None
    body = match.group("body").split("?", 1)[0].split("#", 1)[0].split("/", 1)[0]
    return match.group("scheme").lower(), body.strip()


def _with_id(namespace: str, value: str) -> ExternalIds:
    """Build an ExternalIds from one namespace/value pair, discarding values of the wrong shape."""
    if not value:
        return ExternalIds()
    if namespace == "imdb":
        return ExternalIds(imdb_id=value.lower()) if _IMDB_RE.match(value) else ExternalIds()
    if not value.isdigit():
        return ExternalIds()
    number = int(value)
    if namespace == "tmdb":
        return ExternalIds(tmdb_id=number)
    if namespace == "tvdb":
        return ExternalIds(tvdb_id=number)
    if namespace == "anidb":
        return ExternalIds(anidb_id=number)
    return ExternalIds()


def is_known_scheme(raw: str) -> bool:
    """Whether this GUID's agent is one we understand -- including the agents that legitimately
    carry no external ID. False means "new format, worth a look", which is the signal the client
    logs when a real library surprises us."""
    split = _split(raw)
    if split is None:
        return False
    scheme, _ = split
    return (
        scheme in _DIRECT_SCHEMES
        or scheme in _PREFIXED_SCHEMES
        or scheme in _NFO_MOVIE_SCHEMES
        or scheme in _NFO_TV_SCHEMES
        or scheme in _ID_FREE_SCHEMES
        or scheme in _IGNORED_SCHEMES
    )


def parse_guid(raw: str | None) -> ExternalIds:
    """Resolve a single GUID string, in either the new or legacy format."""
    if not raw:
        return ExternalIds()

    split = _split(raw)
    if split is None:
        return ExternalIds()
    scheme, body = split

    if scheme in _DIRECT_SCHEMES:
        return _with_id(_DIRECT_SCHEMES[scheme], body)

    if scheme in _PREFIXED_SCHEMES:
        # HAMA: "tvdb-73244", "anidb-4691", "tmdb-1234", "imdb-tt0080339".
        namespace, _, value = body.partition("-")
        return _with_id(namespace.lower(), value)

    if scheme in _NFO_MOVIE_SCHEMES:
        return _with_id("imdb" if _IMDB_RE.match(body) else "tmdb", body)

    if scheme in _NFO_TV_SCHEMES:
        return _with_id("imdb" if _IMDB_RE.match(body) else "tvdb", body)

    return ExternalIds()


def extract_external_ids(
    item_guid: str | None = None, guids: Iterable[str] | None = None
) -> ExternalIds:
    """Resolve one Plex item's IDs from its own GUID plus any child ``<Guid>`` values.

    The child GUIDs are consulted first: when both are present the item was matched by a new
    agent, and the child elements are the richer, unambiguous source.
    """
    result = ExternalIds()
    for raw in guids or ():
        result = result.merge(parse_guid(raw))
    return result.merge(parse_guid(item_guid))


def unknown_schemes(item_guid: str | None = None, guids: Iterable[str] | None = None) -> list[str]:
    """GUIDs on this item whose agent we don't recognise -- diagnostics for the client's logs."""
    candidates = [raw for raw in (guids or ()) if raw]
    if item_guid:
        candidates.append(item_guid)
    return [raw for raw in candidates if not is_known_scheme(raw)]


__all__ = [
    "ExternalIds",
    "extract_external_ids",
    "is_known_scheme",
    "parse_guid",
    "unknown_schemes",
]
