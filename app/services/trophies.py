"""The Trophy case (0.52.0): every collection, franchise and director's filmography the library has
finished, newest first, and milestone badges for how many. For everyone (michael's call); the
Showcase look frames it in gold.

"Finished" is the household's, as for the confetti: every released film owned, whoever's
dismissed what. A collection's date is when a scan first found it complete (celebrations'
records); the ones already complete when those began are shown without one."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from sqlmodel import Session, col, select

from app.models import CollectionCompletion

#: Milestones per kind: (kind, noun, thresholds). The first of each gets its own name.
TRACKS = (
    ("collections", "collection", (1, 10, 25, 50, 100, 250, 500, 1000)),
    ("franchises", "franchise", (1, 5, 10, 25, 50, 100, 250, 500)),
    ("directors", "filmography", (1, 5, 10, 25, 50)),
)
FIRSTS = {
    "collections": "First complete collection",
    "franchises": "First complete franchise",
    "directors": "First complete filmography",
}
#: A trophy this recent is marked new.
NEW_FOR = timedelta(days=30)


@dataclass(frozen=True)
class Trophy:
    name: str
    path: str
    image: str | None
    detail: str
    when: datetime | None = None
    new: bool = False
    #: Up to four posters when there's no single image (a franchise's mosaic).
    mosaic: tuple[str, ...] = ()


@dataclass(frozen=True)
class Badge:
    kind: str
    label: str
    threshold: int
    have: int

    @property
    def earned(self) -> bool:
        return self.have >= self.threshold

    @property
    def to_go(self) -> int:
        return max(0, self.threshold - self.have)


@dataclass(frozen=True)
class Almost:
    """A set a few titles from the shelf (0.72.0): what it is, how far along, and what's left."""

    kind: str
    name: str
    path: str
    image: str | None
    have: int
    total: int
    left: tuple[str, ...]

    @property
    def to_go(self) -> int:
        return self.total - self.have


#: How few titles short a set has to be to count as almost on the shelf, and how many to show.
ALMOST_WITHIN, ALMOST_SHOWN = 3, 8


@dataclass
class Case:
    collections: list[Trophy] = field(default_factory=list)
    franchises: list[Trophy] = field(default_factory=list)
    directors: list[Trophy] = field(default_factory=list)
    #: Sets a few titles short of a trophy, fewest to go first (0.72.0).
    almost: list[Almost] = field(default_factory=list)

    def count(self, kind: str) -> int:
        return len(getattr(self, kind))

    @property
    def total(self) -> int:
        return sum(self.count(kind) for kind, _, _ in TRACKS)

    @property
    def earned(self) -> list[Badge]:
        """Every milestone reached, biggest first within each kind."""
        return [b for kind, _, _ in TRACKS for b in reversed(_badges(self, kind)) if b.earned]

    @property
    def next_up(self) -> list[Badge]:
        """The next milestone of each kind, where there is one."""
        return [next(b for b in _badges(self, kind) if not b.earned)
                for kind, _, _ in TRACKS if any(not b.earned for b in _badges(self, kind))]


def _badges(case: Case, kind: str) -> list[Badge]:
    noun, thresholds = next((n, t) for k, n, t in TRACKS if k == kind)
    have = case.count(kind)
    plural = "filmographies" if noun == "filmography" else f"{noun}s"
    return [Badge(kind, FIRSTS[kind] if n == 1 else f"{n} complete {plural}", n, have) for n in thresholds]


def _films(n: int, shows: int = 0) -> str:
    parts = [f"{n} film{'' if n == 1 else 's'}"] if n else []
    if shows:
        parts.append(f"{shows} show{'' if shows == 1 else 's'}")
    return " · ".join(parts)


def case(session: Session, *, now: datetime | None = None) -> Case:
    from app.services import director_service, franchise_service, movie_gap_service

    now = now or datetime.now(timezone.utc)
    recorded = {c.collection_id: c for c in session.exec(select(CollectionCompletion)).all()}

    def dated(completion: CollectionCompletion | None) -> tuple[datetime | None, bool]:
        if completion is None or not completion.celebrate:
            return None, False
        when = completion.completed_at
        when = when if when.tzinfo else when.replace(tzinfo=timezone.utc)
        return when, now - when <= NEW_FOR

    collections = []
    almost: list[Almost] = []
    for g in movie_gap_service.collection_gaps(session):
        short = list(g.missing) + list(g.hidden)
        if g.owned and 0 < len(short) <= ALMOST_WITHIN:
            almost.append(Almost("collection", g.name, f"/collections/{g.collection_id}", g.small_poster,
                                 len(g.owned), len(g.owned) + len(short), tuple(m.title for m in short)))
        if not g.owned or g.missing or g.hidden:
            continue
        when, new = dated(recorded.get(g.collection_id))
        collections.append(Trophy(g.name, f"/collections/{g.collection_id}", g.small_poster,
                                  _films(len(g.owned)), when, new))
    # Newest first; the undated (complete before anyone was counting) after, by name.
    collections.sort(key=lambda t: (t.when is None, -(t.when.timestamp() if t.when else 0), t.name.casefold()))

    views = franchise_service.franchise_views(session)
    franchises = [
        Trophy(f.name, f"/franchises/{f.wikidata_id}", f.small_poster,
               _films(len(f.owned_films), len(f.owned_shows)), mosaic=tuple(f.mosaic or ()))
        for f in views if f.owned and not f.missing
    ]
    # A franchise that *is* a listed collection ("The Matrix" and "The Matrix Collection") would
    # be the same set twice; the collection stands for both.
    listed = [a.name for a in almost]
    almost += [Almost("franchise", f.name, f"/franchises/{f.wikidata_id}", f.small_poster, f.owned, f.total,
                      tuple(t.title for t in f.missing_films + f.missing_shows))
               for f in views if f.owned and 0 < f.missing <= ALMOST_WITHIN
               and not any(franchise_service._same_name(f.name, name) for name in listed)]
    franchises.sort(key=lambda t: t.name.casefold())

    directors = [
        Trophy(d.name, f"/directors/{d.person_id}", d.photo, _films(len(d.owned)))
        for d in director_service.director_views(session) if d.owned and not d.missing and not d.pending
    ]
    directors.sort(key=lambda t: t.name.casefold())
    almost.sort(key=lambda a: (a.to_go, -a.have / a.total, a.name.casefold()))
    return Case(collections, franchises, directors, almost[:ALMOST_SHOWN])


#: Milestones a person has seen, for Showcase's "unlocked" moment (0.57.0).
SEEN_KEY = "trophies_seen"


def newly_earned(session: Session, user_id: int, case: Case) -> set[str]:
    """Milestones earned since this person last looked, marked seen as they're returned. The
    first look ever records them all quietly -- a case full of badges isn't news (the same
    reason the confetti skips what was complete before it existed)."""
    import json

    from app.models import UserPreference
    from app.services.sorting import _save

    earned = [b.label for b in case.earned]
    raw = session.exec(select(UserPreference.value).where(
        col(UserPreference.user_id) == user_id, col(UserPreference.key) == SEEN_KEY)).first()
    try:
        seen = set(json.loads(raw)) if raw else None
    except (ValueError, TypeError):
        seen = None
    _save(session, user_id, SEEN_KEY, json.dumps(sorted(earned)))
    session.commit()
    return set() if seen is None else set(earned) - seen
