"""Managing configured Sonarr instances.

Deliberately a sibling of `instance_service` rather than a shared generic layer. The two look
alike but diverge where it matters -- Sonarr instances carry a default monitor mode, their cache
holds a TVDB id alongside the TMDb one, and the add call has a different shape. A single
parameterised module would have to branch on type in most of its functions, which is the
abstraction earning nothing and costing clarity.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from sqlmodel import Session, col, delete, select

from app.clients.sonarr_client import SonarrClient, SonarrError
from app.config import EnvSettings
from app.logging_config import register_secret
from app.models import SonarrInstance, SonarrSeries, User, utcnow

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class InstanceRefresh:
    instance_id: int
    name: str
    series: int = 0
    queued: int = 0
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None


def list_sonarr(session: Session) -> list[SonarrInstance]:
    return list(session.exec(select(SonarrInstance).order_by(col(SonarrInstance.name))).all())


def get_sonarr(session: Session, instance_id: int) -> SonarrInstance | None:
    return session.get(SonarrInstance, instance_id)


def client_for(instance: SonarrInstance) -> SonarrClient:
    return SonarrClient(instance.url, instance.api_key)


def create_sonarr(session: Session, **fields) -> SonarrInstance:
    instance = SonarrInstance(**fields)
    if not list_sonarr(session):
        instance.is_default = True
    session.add(instance)
    session.commit()
    session.refresh(instance)
    register_secret(instance.api_key)
    logger.info("Added Sonarr instance %r", instance.name)
    return instance


def set_default(session: Session, instance_id: int) -> None:
    for instance in list_sonarr(session):
        instance.is_default = instance.id == instance_id
        session.add(instance)
    session.commit()


def delete_sonarr(session: Session, instance_id: int) -> None:
    instance = get_sonarr(session, instance_id)
    if instance is None:
        return

    was_default = instance.is_default
    session.delete(instance)
    session.commit()

    remaining = list_sonarr(session)
    if was_default and remaining:
        set_default(session, remaining[0].id)
    logger.info("Removed Sonarr instance %r", instance.name)


def preferred_instance(session: Session, user: User | None = None) -> SonarrInstance | None:
    instances = list_sonarr(session)
    if not instances:
        return None

    if user is not None and user.last_sonarr_instance_id:
        for instance in instances:
            if instance.id == user.last_sonarr_instance_id:
                return instance

    for instance in instances:
        if instance.is_default:
            return instance

    return instances[0]


def remember_choice(session: Session, user: User, instance_id: int) -> None:
    user.last_sonarr_instance_id = instance_id
    session.add(user)
    session.commit()


def remember_monitor_mode(session: Session, instance: SonarrInstance, mode: str) -> None:
    """The add dialog pre-selects the last mode used on this instance (docs/DESIGN.md section 5)."""
    if instance.default_monitor_mode != mode:
        instance.default_monitor_mode = mode
        session.add(instance)
        session.commit()


def seed_sonarr_from_env(session: Session, env: EnvSettings) -> SonarrInstance | None:
    """Create a first instance from SONARR_URL/SONARR_API_KEY on first boot. Create-only."""
    if not env.sonarr_url or not env.sonarr_api_key:
        return None
    if list_sonarr(session):
        logger.debug("Sonarr instances already configured; skipping env bootstrap")
        return None

    instance = create_sonarr(
        session, name="Sonarr", url=env.sonarr_url, api_key=env.sonarr_api_key
    )
    logger.info("Seeded Sonarr instance from the environment")
    return instance


def refresh_instance_cache(session: Session, instance: SonarrInstance) -> InstanceRefresh:
    """Re-read what this instance holds. An unreachable instance keeps its previous cache."""
    client = client_for(instance)
    try:
        series = client.series()
        queued = client.queued_tmdb_ids() if instance.hide_if_queued else set()
    except SonarrError as exc:
        logger.warning("Could not refresh Sonarr instance %r: %s", instance.name, exc)
        return InstanceRefresh(instance.id, instance.name, error=str(exc))

    # Bulk delete then flush, so the inserts below can't race the deletes and trip the unique
    # constraint -- the failure that only shows up once the two sets overlap.
    session.exec(delete(SonarrSeries).where(col(SonarrSeries.instance_id) == instance.id))
    session.flush()

    stored = 0
    for show in series:
        if show.tmdb_id is None:
            # Sonarr tracks some series it has no TMDb id for. They can't be matched against
            # TMDb-keyed suggestions, so caching them would achieve nothing.
            continue
        session.add(
            SonarrSeries(
                instance_id=instance.id,
                tmdb_id=show.tmdb_id,
                tvdb_id=show.tvdb_id,
                title=show.title,
                monitored=show.monitored,
                in_queue=show.tmdb_id in queued,
                fetched_at=utcnow(),
            )
        )
        stored += 1
    session.commit()

    return InstanceRefresh(instance.id, instance.name, series=stored, queued=len(queued))


def refresh_all(session: Session) -> list[InstanceRefresh]:
    return [refresh_instance_cache(session, instance) for instance in list_sonarr(session)]
