import datetime
import logging

import dramatiq

from gameclub_backend.config import get_settings
from gameclub_backend.infrastructure.broker import configure_broker
from gameclub_backend.infrastructure.resources import create_resources
from gameclub_backend.modules.clients.infrastructure.postgres import PostgresClientRepository
from gameclub_backend.modules.reservations.application.service import ReservationService
from gameclub_backend.modules.reservations.infrastructure.postgres import (
    PostgresReservationRepository,
)
from gameclub_backend.modules.workstations.infrastructure.postgres import (
    PostgresWorkstationRepository,
)

logger = logging.getLogger(__name__)

broker = configure_broker(get_settings())


def _parse_sweep_time(value: str | None) -> datetime.datetime:
    if value is None:
        return datetime.datetime.now(datetime.UTC)
    parsed = datetime.datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise ValueError("Sweep time must include timezone")
    return parsed


@dramatiq.actor(queue_name="reservations", max_retries=3)
async def sweep_reservation_no_shows(now_iso: str | None = None) -> None:
    """Mark reservations past their grace period; safe to run repeatedly."""
    settings = get_settings()
    if not settings.postgres_dsn:
        raise RuntimeError("GAMECLUB_POSTGRES_DSN is required for reservation workers")

    resources = create_resources(settings)
    engine = resources.engine
    if engine is None:
        await resources.close()
        raise RuntimeError("PostgreSQL resources are not configured")

    try:

        def engine_provider():
            return engine

        reservation_service = ReservationService(
            PostgresReservationRepository(engine_provider),
            workstations=PostgresWorkstationRepository(engine_provider),
            clients=PostgresClientRepository(engine_provider),
            grace_period_minutes=settings.reservation_grace_period_minutes,
        )
        updated = await reservation_service.sweep_no_shows(_parse_sweep_time(now_iso))
        logger.info("reservation_no_show_sweep_completed updated_count=%s", len(updated))
    finally:
        await resources.close()
