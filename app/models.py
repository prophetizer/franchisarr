"""SQLModel table definitions (PROJECT_PLAN.md section 5).

Constrained columns (library type, mapping confidence, monitor mode, ...) are declared as
`str`-backed enums for type safety in Python but stored as plain VARCHAR. SQLite has no native
enum, and SQLAlchemy's `Enum` type emits a CHECK constraint that would turn "accept one more
value" into a table rebuild migration. Validation belongs in the service layer, not the schema.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from sqlmodel import Field, SQLModel, UniqueConstraint


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class LibraryType(str, Enum):
    MOVIE = "movie"
    SHOW = "show"


class ItemType(str, Enum):
    MOVIE = "movie"
    SHOW = "show"


class MonitorMode(str, Enum):
    """Friendly labels shown in the Sonarr add dialog. The mapping to Sonarr's actual
    `addOptions.monitor` API values is deliberately deferred to Phase 7 (technical challenge #22)."""

    ALL = "all"
    FUTURE_ONLY = "future_only"
    FIRST_SEASON = "first_season"


class MappingSource(str, Enum):
    LOCAL = "local"
    COMMUNITY = "community"
    #: Discovered from Wikidata during a scan. Kept distinct from LOCAL so a re-scan can refresh
    #: them without touching a mapping the user added by hand.
    WIKIDATA = "wikidata"


class MappingConfidence(str, Enum):
    CONFIRMED = "confirmed"
    HEURISTIC = "heuristic"


class TriggerSource(str, Enum):
    MANUAL = "manual"
    SCHEDULED = "scheduled"


class WebhookFormat(str, Enum):
    GENERIC = "generic"
    DISCORD = "discord"
    SLACK = "slack"


class User(SQLModel, table=True):
    """A Plex-authenticated user, or the fallback local admin.

    `api_key` authenticates the CLI against the app's own HTTP API without a browser session
    (technical challenge #21); it is nullable because it is generated on request from Settings.
    """

    __tablename__ = "users"

    id: int | None = Field(default=None, primary_key=True)
    plex_user_id: str | None = Field(default=None, index=True, unique=True)
    plex_username: str | None = Field(default=None)
    local_username: str | None = Field(default=None, index=True, unique=True)
    password_hash: str | None = Field(default=None)
    is_admin: bool = Field(default=False)
    api_key: str | None = Field(default=None, index=True, unique=True)
    #: Which instance this person last added to, so the add dialog can pre-select it
    #: (technical challenge #3). Deliberately not a foreign key: a stale id after an instance is
    #: deleted should read as "no preference", not block the delete or need a cascade rule while
    #: the on-delete semantics for the other user references are still unsettled.
    last_radarr_instance_id: int | None = Field(default=None)
    last_sonarr_instance_id: int | None = Field(default=None)
    created_at: datetime = Field(default_factory=utcnow)


class RadarrInstance(SQLModel, table=True):
    """One configured Radarr. Root folder / quality profile *options* are fetched live from the
    instance at add-time; only the default *selection* is persisted here."""

    __tablename__ = "radarr_instances"

    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(index=True)
    url: str
    api_key: str
    default_root_folder: str | None = Field(default=None)
    default_quality_profile_id: int | None = Field(default=None)
    is_default: bool = Field(default=False)
    hide_if_queued: bool = Field(default=True)
    created_at: datetime = Field(default_factory=utcnow)


class SonarrInstance(SQLModel, table=True):
    __tablename__ = "sonarr_instances"

    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(index=True)
    url: str
    api_key: str
    default_root_folder: str | None = Field(default=None)
    default_quality_profile_id: int | None = Field(default=None)
    default_monitor_mode: str = Field(default=MonitorMode.ALL.value)
    is_default: bool = Field(default=False)
    hide_if_queued: bool = Field(default=True)
    created_at: datetime = Field(default_factory=utcnow)


class Setting(SQLModel, table=True):
    """Install-wide key/value settings. Shared across everyone using this install, since the
    TMDb key and scan cache they govern are shared too."""

    __tablename__ = "settings"

    key: str = Field(primary_key=True)
    value: str | None = Field(default=None)
    updated_at: datetime = Field(default_factory=utcnow)


class DismissedItem(SQLModel, table=True):
    """Per-user ignore list — one person hiding a suggestion doesn't hide it for the household."""

    __tablename__ = "dismissed_items"
    __table_args__ = (UniqueConstraint("user_id", "item_type", "tmdb_id", name="uq_dismissed_item"),)

    id: int | None = Field(default=None, primary_key=True)
    # CASCADE: a dismiss list is one person's preference and means nothing without them.
    user_id: int = Field(foreign_key="users.id", ondelete="CASCADE", index=True)
    item_type: str
    tmdb_id: int = Field(index=True)
    created_at: datetime = Field(default_factory=utcnow)


class SpinoffMapping(SQLModel, table=True):
    """Show -> spin-off relation. v1 only ever writes source='local'; the `source`/`confidence`/
    `origin_ref` columns exist from day one so a future community-sync feature is additive
    (PROJECT_PLAN.md section 2)."""

    __tablename__ = "spinoff_mappings"
    __table_args__ = (
        UniqueConstraint("source_show_tmdb_id", "spinoff_show_tmdb_id", name="uq_spinoff_pair"),
    )

    id: int | None = Field(default=None, primary_key=True)
    source_show_tmdb_id: int = Field(index=True)
    spinoff_show_tmdb_id: int = Field(index=True)
    source: str = Field(default=MappingSource.LOCAL.value)
    confidence: str = Field(default=MappingConfidence.CONFIRMED.value)
    origin_ref: str | None = Field(default=None)
    # SET NULL: the mapping is shared household data and outlives whoever contributed it.
    added_by_user_id: int | None = Field(
        default=None, foreign_key="users.id", ondelete="SET NULL"
    )
    created_at: datetime = Field(default_factory=utcnow)


class CrossMediaMapping(SQLModel, table=True):
    """A film related to a show the user owns, or a show related to a film they own.

    Kept apart from `spinoff_mappings`, which is show-to-show and keyed by TMDb *TV* ids on both
    sides; putting movie ids in it would make every join a guess about which namespace a number
    is in. Display fields live on the row because the target is outside every other cache: a
    film that is not in any owned collection has no TmdbCollectionMovie row to borrow from.
    """

    __tablename__ = "cross_media_mappings"
    __table_args__ = (
        UniqueConstraint(
            "source_type", "source_tmdb_id", "target_type", "target_tmdb_id",
            name="uq_cross_media_pair",
        ),
    )

    id: int | None = Field(default=None, primary_key=True)
    #: "movie" or "show" -- what the user owns.
    source_type: str = Field(index=True)
    source_tmdb_id: int = Field(index=True)
    #: The other medium.
    target_type: str = Field(index=True)
    target_tmdb_id: int = Field(index=True)
    target_title: str
    target_year: int | None = Field(default=None)
    target_poster_path: str | None = Field(default=None)
    #: The Wikidata property that stated it, e.g. "P144".
    relation: str
    source: str = Field(default=MappingSource.WIKIDATA.value)
    confidence: str = Field(default=MappingConfidence.CONFIRMED.value)
    created_at: datetime = Field(default_factory=utcnow)


class CollectionExclude(SQLModel, table=True):
    """"Not really part of this collection" — a TMDb data-quality correction scoped to one
    collection, distinct from the per-user dismiss list."""

    __tablename__ = "collection_excludes"
    __table_args__ = (
        UniqueConstraint("tmdb_collection_id", "tmdb_movie_id", name="uq_collection_exclude"),
    )

    id: int | None = Field(default=None, primary_key=True)
    tmdb_collection_id: int = Field(index=True)
    tmdb_movie_id: int = Field(index=True)
    # SET NULL: an exclusion is a correction to TMDb's data, not a personal preference, so it
    # must survive the account that made it.
    added_by_user_id: int | None = Field(
        default=None, foreign_key="users.id", ondelete="SET NULL"
    )
    created_at: datetime = Field(default_factory=utcnow)


class IncludedLibrary(SQLModel, table=True):
    """Plex libraries discovered on connect. Only `enabled` ones are scanned."""

    __tablename__ = "included_libraries"

    id: int | None = Field(default=None, primary_key=True)
    plex_library_key: str = Field(index=True, unique=True)
    plex_library_name: str
    library_type: str
    enabled: bool = Field(default=True)


class MatchSource(str, Enum):
    """How a Plex item was resolved to a TMDb ID, in descending order of trust."""

    GUID = "guid"          # TMDb id supplied by Plex directly
    IMDB = "imdb"          # resolved via TMDb's /find using the IMDb id
    TVDB = "tvdb"          # resolved via TMDb's /find using the TVDb id
    TITLE = "title"        # title+year search
    NONE = "none"          # nothing matched


class LibraryItem(SQLModel, table=True):
    """Cached snapshot of one Plex item and the TMDb id it resolved to.

    Exists so gap views and scheduled scans don't re-walk Plex and re-query TMDb on every page
    load (technical challenge #7). `last_seen_at` is what makes an incremental scan possible:
    items missing from a later scan of the same library have been removed from Plex.
    """

    __tablename__ = "library_items"
    __table_args__ = (
        UniqueConstraint("plex_library_key", "rating_key", name="uq_library_item"),
    )

    id: int | None = Field(default=None, primary_key=True)
    plex_library_key: str = Field(index=True)
    rating_key: str = Field(index=True)
    item_type: str = Field(default=ItemType.MOVIE.value)
    title: str
    year: int | None = Field(default=None)

    tmdb_id: int | None = Field(default=None, index=True)
    imdb_id: str | None = Field(default=None)
    tvdb_id: int | None = Field(default=None)

    match_source: str = Field(default=MatchSource.NONE.value)
    #: Similarity score for a title match; None when the id came from an authoritative source.
    match_confidence: float | None = Field(default=None)
    #: A plausible but unconfirmed title match. Surfaced for review rather than acted on
    #: (technical challenge #14) -- never silently skipped, never silently trusted.
    needs_review: bool = Field(default=False)

    last_seen_at: datetime = Field(default_factory=utcnow, index=True)
    updated_at: datetime = Field(default_factory=utcnow)


class TmdbMovie(SQLModel, table=True):
    """Cached TMDb movie details -- chiefly which collection it belongs to.

    Collection membership changes about never, so this is cached with a TTL measured in days
    (technical challenge #4). `fetched_at` drives expiry.
    """

    __tablename__ = "tmdb_movies"

    tmdb_id: int = Field(primary_key=True)
    title: str
    release_year: int | None = Field(default=None)
    collection_id: int | None = Field(default=None, index=True)
    fetched_at: datetime = Field(default_factory=utcnow, index=True)


class TmdbShow(SQLModel, table=True):
    """Cached TMDb show details.

    `network` is kept because it corroborates a heuristic spin-off guess: shows that spun off
    from each other usually shared a broadcaster, and a title that merely *looks* like a spin-off
    on a different network is far more often an unrelated show with a similar name.
    """

    __tablename__ = "tmdb_shows"

    tmdb_id: int = Field(primary_key=True)
    name: str
    first_air_year: int | None = Field(default=None)
    #: TMDb's path fragment, as on the movie tables: the size stays a rendering decision.
    poster_path: str | None = Field(default=None)
    #: External ids, so a suggestion can link out to a page that says what the show *is*. A title
    #: and a year are not enough to tell "Ghosts" from "Ghosts" -- IMDb or TVDB usually are.
    imdb_id: str | None = Field(default=None)
    tvdb_id: int | None = Field(default=None)
    network: str | None = Field(default=None)
    fetched_at: datetime = Field(default_factory=utcnow, index=True)


class TmdbCollection(SQLModel, table=True):
    __tablename__ = "tmdb_collections"

    tmdb_collection_id: int = Field(primary_key=True)
    name: str
    #: TMDb's path fragment, e.g. "/7TEAr7....jpg". Stored rather than a full URL so the size and
    #: the CDN host stay a rendering decision.
    poster_path: str | None = Field(default=None)
    #: The wide image behind a collection heading. A TMDb path fragment, like poster_path.
    backdrop_path: str | None = Field(default=None)
    #: A full URL, not a fragment: fanart.tv serves one size from its own CDN, so unlike TMDb
    #: there is no size left to choose at render time. Null whenever no fanart key is configured,
    #: which is the normal state for an install that never sets one.
    logo_url: str | None = Field(default=None)
    fetched_at: datetime = Field(default_factory=utcnow, index=True)


class TmdbCollectionMovie(SQLModel, table=True):
    """One film belonging to a cached collection.

    Rows are replaced wholesale when a collection is refreshed, which is why collection_excludes
    keys on TMDb ids rather than referencing these rows -- an exclusion has to survive a refresh
    (technical challenge #13).
    """

    __tablename__ = "tmdb_collection_movies"
    __table_args__ = (
        UniqueConstraint("collection_id", "tmdb_movie_id", name="uq_collection_member"),
    )

    id: int | None = Field(default=None, primary_key=True)
    collection_id: int = Field(
        foreign_key="tmdb_collections.tmdb_collection_id", ondelete="CASCADE", index=True
    )
    tmdb_movie_id: int = Field(index=True)
    title: str
    release_year: int | None = Field(default=None)
    release_date: str | None = Field(default=None)
    poster_path: str | None = Field(default=None)
    #: TMDb's community score, captured because a flat list of 200 gaps needs an order, and the
    #: straight-to-video sequels are what most of that list is. vote_count is kept so a film
    #: nobody has rated is never mistaken for a bad one.
    vote_average: float | None = Field(default=None)
    vote_count: int | None = Field(default=None)
    popularity: float | None = Field(default=None)
    position: int = Field(default=0)


class RadarrMovie(SQLModel, table=True):
    """What a Radarr instance already knows about, cached.

    The "do I already have this?" check runs at diff time against every configured instance
    (technical challenge #5), and diff time is a page load. Radarr's movie list can run to
    thousands of entries, so asking every instance for its whole library on every page view is
    not viable -- this is refreshed on scan and on demand instead.

    `in_queue` is kept separate from `has_file` because they answer different questions: one is
    "you own it", the other is "it's already on its way", and `hide_if_queued` decides per
    instance whether the second counts.
    """

    __tablename__ = "radarr_movies"
    __table_args__ = (UniqueConstraint("instance_id", "tmdb_id", name="uq_radarr_movie"),)

    id: int | None = Field(default=None, primary_key=True)
    instance_id: int = Field(
        foreign_key="radarr_instances.id", ondelete="CASCADE", index=True
    )
    tmdb_id: int = Field(index=True)
    title: str = Field(default="")
    monitored: bool = Field(default=True)
    has_file: bool = Field(default=False)
    in_queue: bool = Field(default=False)
    fetched_at: datetime = Field(default_factory=utcnow)


class SonarrSeries(SQLModel, table=True):
    """What a Sonarr instance already tracks. The TV counterpart of RadarrMovie, and there for
    the same reason: the "already have it" check runs at diff time, which is a page load."""

    __tablename__ = "sonarr_series"
    __table_args__ = (UniqueConstraint("instance_id", "tmdb_id", name="uq_sonarr_series"),)

    id: int | None = Field(default=None, primary_key=True)
    instance_id: int = Field(
        foreign_key="sonarr_instances.id", ondelete="CASCADE", index=True
    )
    tmdb_id: int = Field(index=True)
    tvdb_id: int | None = Field(default=None, index=True)
    title: str = Field(default="")
    monitored: bool = Field(default=True)
    in_queue: bool = Field(default=False)
    fetched_at: datetime = Field(default_factory=utcnow)


class UpcomingWatch(SQLModel, table=True):
    """The last known release date of each announced-but-unreleased film in a collection the
    user owns part of.

    Exists so a scan can say what *changed*: a film that has just been given a release date, or
    whose date moved. The collection cache cannot answer that -- its rows are replaced wholesale
    on refetch, so there is no "before" to compare against. Rows come and go: a film leaves this
    table when it is released (at which point it is an ordinary gap, and `seen_gaps` takes over)
    or when TMDb drops it.
    """

    __tablename__ = "upcoming_watch"

    tmdb_id: int = Field(primary_key=True)
    title: str
    collection_id: int = Field(index=True)
    collection_name: str
    #: ISO date, or None while TMDb has the film announced but undated.
    release_date: str | None = Field(default=None)
    first_seen_at: datetime = Field(default_factory=utcnow)
    last_seen_at: datetime = Field(default_factory=utcnow)


class SeenGap(SQLModel, table=True):
    """A gap Franchisarr has already told someone about.

    Exists so a scheduled scan can notify about what is *new* rather than re-announcing the same
    227 films every night, which would train everyone to ignore the notification. Rows are only
    ever added, so a film that is added and later removed from Radarr doesn't re-notify.
    """

    __tablename__ = "seen_gaps"
    __table_args__ = (UniqueConstraint("item_type", "tmdb_id", name="uq_seen_gap"),)

    id: int | None = Field(default=None, primary_key=True)
    item_type: str = Field(index=True)
    tmdb_id: int = Field(index=True)
    title: str = Field(default="")
    first_seen_at: datetime = Field(default_factory=utcnow)


class UserSession(SQLModel, table=True):
    """A logged-in browser session.

    Named UserSession rather than Session to avoid colliding with SQLModel's own Session.

    Only a hash of the session token is stored. The plaintext token lives solely in the user's
    cookie, so a leaked database -- a copied /config volume, a backup, a support bundle -- cannot
    be replayed as a live login. Being a table rather than a signed cookie also means logout
    actually revokes: deleting the row ends the session everywhere immediately.
    """

    __tablename__ = "sessions"

    id: int | None = Field(default=None, primary_key=True)
    token_hash: str = Field(index=True, unique=True)
    # CASCADE: an orphaned session is meaningless and would be a live credential for an account
    # that no longer exists. Note the other tables referencing users deliberately do NOT cascade
    # -- deleting a user must not erase shared spin-off mappings or the audit log -- but those
    # semantics are settled when user management arrives, not here.
    user_id: int = Field(foreign_key="users.id", ondelete="CASCADE", index=True)
    created_at: datetime = Field(default_factory=utcnow)
    expires_at: datetime = Field(index=True)
    last_seen_at: datetime = Field(default_factory=utcnow)


class ActivityLogEntry(SQLModel, table=True):
    """Append-only record of adds Franchisarr made. `instance_id` has no foreign key because
    `item_type` decides which instance table it points at; it records what happened even if the
    instance is later deleted. Download/import status stays Radarr/Sonarr's business
    (technical challenge #24)."""

    __tablename__ = "activity_log"

    id: int | None = Field(default=None, primary_key=True)
    timestamp: datetime = Field(default_factory=utcnow, index=True)
    item_type: str
    tmdb_id: int = Field(index=True)
    title: str
    instance_id: int | None = Field(default=None)
    # SET NULL is safe here despite NULL also meaning "a scheduled scan did this", because
    # `trigger_source` already carries that distinction: NULL with trigger_source='scheduled' is
    # the scheduler, NULL with 'manual' is a person whose account has since been deleted. Without
    # that second column this would have to be RESTRICT, and deleting a user would be blocked by
    # their own history.
    triggered_by: int | None = Field(
        default=None, foreign_key="users.id", ondelete="SET NULL"
    )
    trigger_source: str = Field(default=TriggerSource.MANUAL.value)
