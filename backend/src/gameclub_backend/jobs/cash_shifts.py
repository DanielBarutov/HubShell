import datetime
import logging

import dramatiq

from gameclub_backend.config import get_settings
from gameclub_backend.infrastructure.broker import configure_broker
from gameclub_backend.infrastructure.resources import create_resources
from gameclub_backend.modules.cash_shifts.application.service import CashShiftService
from gameclub_backend.modules.cash_shifts.infrastructure.postgres import PostgresCashShiftRepository

logger = logging.getLogger(__name__)
broker = configure_broker(get_settings())


def _parse_now(value: str | None) -> datetime.datetime:
    if value:
        current = datetime.datetime.fromisoformat(value)
    else:
        current = datetime.datetime.now(datetime.UTC)
    if current.tzinfo is None:
        raise ValueError("Automatic shift time must include timezone")
    return current


@dramatiq.actor(queue_name="cash-shifts", max_retries=3)
async def run_cash_shift_schedule(now_iso: str | None = None) -> None:
    """Apply configured register schedules; both actions are idempotent per local day."""
    settings = get_settings()
    if not settings.postgres_dsn:
        raise RuntimeError("GAMECLUB_POSTGRES_DSN is required for cash shift workers")
    resources = create_resources(settings)
    engine = resources.engine
    if engine is None:
        await resources.close()
        raise RuntimeError("PostgreSQL resources are not configured")
    try:

        def engine_provider():
            return engine

        service = CashShiftService(PostgresCashShiftRepository(engine_provider))
        actions = await service.run_auto_schedule(_parse_now(now_iso))
        logger.info("cash_shift_schedule_completed actions=%s", actions)
    finally:
        await resources.close()
