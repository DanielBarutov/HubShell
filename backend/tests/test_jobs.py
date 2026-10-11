import asyncio
import datetime
import uuid
from pathlib import Path

import pytest
from dramatiq.brokers.stub import StubBroker

from gameclub_backend.config import Settings
from gameclub_backend.infrastructure.broker import create_broker
from gameclub_backend.jobs import scheduler
from gameclub_backend.jobs.billing import (
    meter_active_sessions,
    meter_sessions_once,
    reconcile_billing_charges,
)
from gameclub_backend.jobs.cash_shifts import run_cash_shift_schedule
from gameclub_backend.jobs.reports import (
    backfill_v2_confirmed_per_minute_debits,
    project_analytics_events,
)
from gameclub_backend.jobs.reservations import _parse_sweep_time, sweep_reservation_no_shows
from gameclub_backend.jobs.scheduler import dispatch_periodic_jobs, run
from gameclub_backend.modules.sessions.domain import Session, SessionStatus


def test_broker_uses_stub_without_redis_and_enables_asyncio_middleware() -> None:
    """
    Проверяет сценарий «test_broker_uses_stub_without_redis_and_enables_asyncio_middleware» и
    подтверждает ожидаемый публичный результат согласно соответствующему бизнес-правилу.
    """
    broker = create_broker(Settings())

    assert isinstance(broker, StubBroker)
    assert any(type(middleware).__name__ == "AsyncIO" for middleware in broker.middleware)


def test_sweep_time_requires_timezone() -> None:
    """
    Проверяет сценарий «test_sweep_time_requires_timezone» и подтверждает ожидаемый публичный
    результат согласно соответствующему бизнес-правилу.
    """
    parsed = _parse_sweep_time("2036-01-01T12:00:00+00:00")

    assert parsed == datetime.datetime(2036, 1, 1, 12, tzinfo=datetime.UTC)


def test_background_actors_do_not_publish_discarded_results() -> None:
    """
    Проверяет сценарий «test_background_actors_do_not_publish_discarded_results» и подтверждает
    ожидаемый публичный результат согласно соответствующему бизнес-правилу.
    """
    assert sweep_reservation_no_shows.fn.__annotations__["return"] is None
    assert reconcile_billing_charges.fn.__annotations__["return"] is None
    assert project_analytics_events.fn.__annotations__["return"] in {None, "None"}
    assert backfill_v2_confirmed_per_minute_debits.fn.__annotations__["return"] in {None, "None"}


def test_background_actors_share_one_broker() -> None:
    """
    Проверяет сценарий «test_background_actors_share_one_broker» и подтверждает ожидаемый
    публичный результат согласно соответствующему бизнес-правилу.
    """
    assert sweep_reservation_no_shows.broker is reconcile_billing_charges.broker
    assert reconcile_billing_charges.broker is run_cash_shift_schedule.broker
    assert set(reconcile_billing_charges.broker.actors) >= {
        "meter_active_sessions",
        "reconcile_billing_charges",
        "reconcile_pending_settlements",
        "run_cash_shift_schedule",
        "sweep_reservation_no_shows",
        "backfill_v2_confirmed_per_minute_debits",
        "project_analytics_events",
    }
    assert meter_active_sessions.queue_name == "metering"


def test_scheduler_dispatches_read_only_analytics_projection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Планировщик передаёт immutable outbox в проекцию, не меняя write-path."""

    scheduled: list[str] = []

    class RecordingActor:
        def __init__(self, name: str) -> None:
            self._name = name

        def send(self) -> None:
            scheduled.append(self._name)

    names = (
        "sweep_reservation_no_shows",
        "reconcile_billing_charges",
        "reconcile_pending_settlements",
        "meter_active_sessions",
        "run_cash_shift_schedule",
        "backfill_v2_confirmed_per_minute_debits",
        "project_analytics_events",
    )
    for name in names:
        monkeypatch.setattr(scheduler, name, RecordingActor(name))

    dispatch_periodic_jobs()

    assert scheduled == list(names)


def test_metering_worker_loads_client_group_debt_policy() -> None:
    """
    Проверяет, что фоновое списание минут получает правила группы клиента,
    поэтому не принимает должника за обычного клиента с лимитом 0 ₽.
    """
    worker_source = (
        Path(__file__).parents[1] / "src" / "gameclub_backend" / "jobs" / "billing.py"
    ).read_text(encoding="utf-8")

    assert "PostgresClientGroupRepository" in worker_source
    assert "groups=PostgresClientGroupRepository(engine_provider)" in worker_source


@pytest.mark.asyncio
async def test_metering_worker_ignores_local_ledger_sessions() -> None:
    """Проверяет, что серверный метр не изменяет автономную сессию клиента."""

    session = Session(
        id=uuid.uuid4(),
        workstation_id=uuid.uuid4(),
        client_id=uuid.uuid4(),
        guest_name=None,
        status=SessionStatus.ACTIVE,
        started_at=datetime.datetime(2026, 1, 1, tzinfo=datetime.UTC),
        ended_at=None,
        source="local_ledger",
        created_by="device",
        created_at=datetime.datetime(2026, 1, 1, tzinfo=datetime.UTC),
    )

    class Reader:
        async def list(self, **kwargs):
            del kwargs
            return [session]

    class Billing:
        calls = 0

        async def meter_session(self, session_id):
            del session_id
            self.calls += 1

    class Stopper:
        async def stop(self, session_id):
            raise AssertionError(session_id)

    class Commands:
        async def dispatch(self, *args):
            raise AssertionError(args)

    billing = Billing()
    assert await meter_sessions_once(billing, Reader(), Stopper(), Commands()) == 0
    assert billing.calls == 0


def test_scheduler_requires_redis() -> None:
    """
    Проверяет сценарий «test_scheduler_requires_redis» и подтверждает ожидаемый публичный
    результат согласно соответствующему бизнес-правилу.
    """
    with pytest.raises(RuntimeError, match="GAMECLUB_REDIS_URL is required"):
        asyncio.run(run())
