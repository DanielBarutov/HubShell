import asyncio
import datetime

import dramatiq
import pytest

from gameclub_backend.config import Settings
from gameclub_backend.infrastructure.broker import create_broker
from gameclub_backend.jobs.billing import reconcile_billing_charges
from gameclub_backend.jobs.reservations import _parse_sweep_time, sweep_reservation_no_shows
from gameclub_backend.jobs.scheduler import run


def test_broker_uses_stub_without_redis_and_enables_asyncio_middleware() -> None:
    broker = create_broker(Settings())

    assert isinstance(broker, dramatiq.brokers.stub.StubBroker)
    assert any(type(middleware).__name__ == "AsyncIO" for middleware in broker.middleware)


def test_sweep_time_requires_timezone() -> None:
    parsed = _parse_sweep_time("2036-01-01T12:00:00+00:00")

    assert parsed == datetime.datetime(2036, 1, 1, 12, tzinfo=datetime.UTC)


def test_background_actors_do_not_publish_discarded_results() -> None:
    assert sweep_reservation_no_shows.fn.__annotations__["return"] is None
    assert reconcile_billing_charges.fn.__annotations__["return"] is None


def test_scheduler_requires_redis() -> None:
    with pytest.raises(RuntimeError, match="GAMECLUB_REDIS_URL is required"):
        asyncio.run(run())
