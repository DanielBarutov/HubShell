import asyncio
import contextlib

from gameclub_backend.config import get_settings
from gameclub_backend.jobs.billing import meter_active_sessions, reconcile_billing_charges
from gameclub_backend.jobs.cash_shifts import run_cash_shift_schedule
from gameclub_backend.jobs.reservations import sweep_reservation_no_shows


async def run() -> None:
    settings = get_settings()
    if not settings.redis_url:
        raise RuntimeError("GAMECLUB_REDIS_URL is required for reservation scheduler")
    if settings.reservation_sweep_interval_seconds <= 0:
        raise ValueError("Reservation sweep interval must be positive")
    if settings.billing_reconciliation_interval_seconds <= 0:
        raise ValueError("Billing reconciliation interval must be positive")

    try:
        while True:
            sweep_reservation_no_shows.send()
            reconcile_billing_charges.send()
            meter_active_sessions.send()
            run_cash_shift_schedule.send()
            await asyncio.sleep(
                min(
                    settings.reservation_sweep_interval_seconds,
                    settings.billing_reconciliation_interval_seconds,
                )
            )
    finally:
        with contextlib.suppress(Exception):
            sweep_reservation_no_shows.broker.close()
        with contextlib.suppress(Exception):
            reconcile_billing_charges.broker.close()
        with contextlib.suppress(Exception):
            meter_active_sessions.broker.close()
        with contextlib.suppress(Exception):
            run_cash_shift_schedule.broker.close()


if __name__ == "__main__":
    asyncio.run(run())
