"""Managing configured Radarr instances.

There is never "the Radarr" (docs/DEVELOPMENT.md convention 4). A household might run a 4K instance and a
1080p one, or split by content type. Everything here takes or returns an instance.

"Which instance should be selected?" is answered in order of how much it reflects an actual
choice: what this user picked last time, then the instance marked default, then the only one
there is (technical challenge #3).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from sqlmodel import Session, col, select

from app.clients.radarr_client import RadarrClient, RadarrError
from app.config import EnvSettings
from app.logging_config import register_secret
from app.models import RadarrInstance, RadarrMovie, User, utcnow

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class InstanceRefresh:
    instance_id: int
    name: str
    movies: int = 0
    queued: int = 0
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None


def list_radarr(session: Session) -> list[RadarrInstance]:
    return list(
        session.exec(select(RadarrInstance).order_by(col(RadarrInstance.name))).all()
    )


def get_radarr(session: Session, instance_id: int) -> RadarrInstance | None:
    return session.get(RadarrInstance, instance_id)


def client_for(instance: RadarrInstance) -> RadarrClient:
    return RadarrClient(instance.url, instance.api_key)


def create_radarr(session: Session, **fields) -> RadarrInstance:
    instance = RadarrInstance(**fields)
    # The first instance is the default whether or not anyone said so; otherwise the add dialog
    # would open with nothing selected on a single-instance install, which is most of them.
    if not list_radarr(session):
        instance.is_default = True
    session.add(instance)
    session.commit()
    session.refresh(instance)
    register_secret(instance.api_key)
    logger.info("Added Radarr instance %r", instance.name)
    return instance


def set_default(session: Session, instance_id: int) -> None:
    """Exactly one instance is the default; marking one clears the rest."""
    for instance in list_radarr(session):
        instance.is_default = instance.id == instance_id
        session.add(instance)
    session.commit()


def delete_radarr(session: Session, instance_id: int) -> None:
    instance = get_radarr(session, instance_id)
    if instance is None:
        return

    was_default = instance.is_default
    session.delete(instance)
    session.commit()

    # Don't leave an install with no default: it would make the add dialog open blank.
    remaining = list_radarr(session)
    if was_default and remaining:
        set_default(session, remaining[0].id)
    logger.info("Removed Radarr instance %r", instance.name)


def preferred_instance(session: Session, user: User | None = None) -> RadarrInstance | None:
    """Which instance the add dialog should pre-select.

    A user's last choice beats the global default: on a 4K-plus-1080p setup the person who always
    adds to 1080p shouldn't have to change the dropdown every time (technical challenge #3).
    """
    instances = list_radarr(session)
    if not instances:
        return None

    if user is not None and user.last_radarr_instance_id:
        for instance in instances:
            if instance.id == user.last_radarr_instance_id:
                return instance

    for instance in instances:
        if instance.is_default:
            return instance

    return instances[0]


def remember_choice(session: Session, user: User, instance_id: int) -> None:
    user.last_radarr_instance_id = instance_id
    session.add(user)
    session.commit()


def seed_radarr_from_env(session: Session, env: EnvSettings) -> RadarrInstance | None:
    """Create a first instance from RADARR_URL/RADARR_API_KEY on first boot.

    Only ever creates, and only when no instance exists at all -- the same rule the settings and
    local-admin bootstraps follow, so a stale value in docker-compose can't undo a change made in
    the app.
    """
    if not env.radarr_url or not env.radarr_api_key:
        return None
    if list_radarr(session):
        logger.debug("Radarr instances already configured; skipping env bootstrap")
        return None

    instance = create_radarr(
        session, name="Radarr", url=env.radarr_url, api_key=env.radarr_api_key
    )
    logger.info("Seeded Radarr instance from the environment")
    return instance


def refresh_instance_cache(session: Session, instance: RadarrInstance) -> InstanceRefresh:
    """Re-read what this instance holds, so gap views don't have to ask it live.

    An unreachable instance leaves the previous cache in place rather than emptying it. Treating
    "I couldn't ask" as "it has nothing" would flood the gap list with films the user already
    owns, which is worse than showing slightly stale data (technical challenge #15).
    """
    client = client_for(instance)
    try:
        movies = client.movies()
        queued = client.queued_tmdb_ids() if instance.hide_if_queued else set()
    except RadarrError as exc:
        logger.warning("Could not refresh Radarr instance %r: %s", instance.name, exc)
        return InstanceRefresh(instance.id, instance.name, error=str(exc))

    for row in session.exec(
        select(RadarrMovie).where(col(RadarrMovie.instance_id) == instance.id)
    ).all():
        session.delete(row)

    for movie in movies:
        session.add(
            RadarrMovie(
                instance_id=instance.id,
                tmdb_id=movie.tmdb_id,
                title=movie.title,
                monitored=movie.monitored,
                has_file=movie.has_file,
                in_queue=movie.tmdb_id in queued,
                fetched_at=utcnow(),
            )
        )
    session.commit()

    return InstanceRefresh(instance.id, instance.name, movies=len(movies), queued=len(queued))


def refresh_all(session: Session) -> list[InstanceRefresh]:
    return [refresh_instance_cache(session, instance) for instance in list_radarr(session)]
