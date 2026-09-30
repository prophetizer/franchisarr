"""The Trophy case (0.52.0): every collection, franchise and director's filmography the library has
finished, newest first, and milestone badges for how many. For everyone (michael's call); the
Showcase look frames it in gold.

"Finished" is the household's, as for the confetti: every released film owned, whoever's
dismissed what. A collection's date is when a scan first found it complete (celebrations'
records); the ones already complete when those began are shown without one."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from sqlmodel import Session, select

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


@dataclass
class Case:
    collections: list[Trophy] = field(default_factory=list)
    franchises: list[Trophy] = field(default_factory=list)
    directors: list[Trophy] = field(default_factory=list)

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
    for g in movie_gap_service.collection_gaps(session):
        if not g.owned or g.missing or g.hidden:
            continue
        when, new = dated(recorded.get(g.collection_id))
        collections.append(Trophy(g.name, f"/collections/{g.collection_id}", g.small_poster,
                                  _films(len(g.owned)), when, new))
    # Newest first; the undated (complete before anyone was counting) after, by name.
    collections.sort(key=lambda t: (t.when is None, -(t.when.timestamp() if t.when else 0), t.name.casefold()))

    franchises = [
        Trophy(f.name, f"/franchises/{f.wikidata_id}", f.small_poster,
               _films(len(f.owned_films), len(f.owned_shows)), mosaic=tuple(f.mosaic or ()))
        for f in franchise_service.franchise_views(session) if f.owned and not f.missing
    ]
    franchises.sort(key=lambda t: t.name.casefold())

    directors = [
        Trophy(d.name, f"/directors/{d.person_id}", d.photo, _films(len(d.owned)))
        for d in director_service.director_views(session) if d.owned and not d.missing and not d.pending
    ]
    directors.sort(key=lambda t: t.name.casefold())
    return Case(collections, franchises, directors)
