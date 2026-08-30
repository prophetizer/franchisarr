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
    user_id: int = Field(foreign_key="users.id", index=True)
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
    added_by_user_id: int | None = Field(default=None, foreign_key="users.id")
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
    added_by_user_id: int | None = Field(default=None, foreign_key="users.id")
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


class TmdbCollection(SQLModel, table=True):
    __tablename__ = "tmdb_collections"

    tmdb_collection_id: int = Field(primary_key=True)
    name: str
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
    position: int = Field(default=0)


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
    triggered_by: int | None = Field(default=None, foreign_key="users.id")
    trigger_source: str = Field(default=TriggerSource.MANUAL.value)
