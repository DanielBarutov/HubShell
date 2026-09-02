import datetime
import uuid

import pytest

from gameclub_backend.modules.billing.application.service import BillingService
from gameclub_backend.modules.billing.domain import MeterStatus
from gameclub_backend.modules.billing.infrastructure.memory import (
    InMemoryChargeRepository,
    InMemoryMeterRepository,
)
from gameclub_backend.modules.catalog.application.service import CatalogService
from gameclub_backend.modules.catalog.domain import BillingMode
from gameclub_backend.modules.catalog.infrastructure.memory import InMemoryCatalogRepository
from gameclub_backend.modules.clients.application.service import ClientService
from gameclub_backend.modules.clients.infrastructure.memory import InMemoryClientRepository
from gameclub_backend.modules.offline.application.service import OfflineReplayService
from gameclub_backend.modules.offline.domain import (
    OfflineBatch,
    OfflineOperation,
    OfflineOperationKind,
    OfflineOperationStatus,
)
from gameclub_backend.modules.offline.infrastructure.memory import InMemoryOfflineReplayRepository
from gameclub_backend.modules.sessions.application.service import SessionService
from gameclub_backend.modules.sessions.infrastructure.memory import InMemorySessionRepository
from gameclub_backend.modules.workstations.application.service import WorkstationService
from gameclub_backend.modules.workstations.infrastructure.memory import (
    InMemoryWorkstationRepository,
)


class FixedClock:
    def __init__(self) -> None:
        self.current = datetime.datetime(2026, 9, 2, 12, tzinfo=datetime.UTC)

    def now(self) -> datetime.datetime:
        return self.current


async def build_offline_services(clock: FixedClock):
    workstation_repository = InMemoryWorkstationRepository()
    workstation = await WorkstationService(workstation_repository).register(
        "offline-device", "Offline PC", group_id="vip"
    )
    client_repository = InMemoryClientRepository()
    clients = ClientService(client_repository, clock=clock)
    client = await clients.create("OfflineFox")
    await clients.top_up(
        client.id,
        amount_cents=500,
        bonus_amount=0,
        reason="Offline test",
        actor_id="operator",
        idempotency_key="offline-top-up",
    )
    catalog = CatalogService(InMemoryCatalogRepository())
    tariff = await catalog.create_tariff(
        "Offline minute",
        "vip",
        duration_minutes=1,
        price_cents=0,
        valid_from=clock.current,
        valid_to=None,
        billing_mode=BillingMode.PER_MINUTE,
        price_per_minute_cents=10,
    )
    session_repository = InMemorySessionRepository()
    meter_repository = InMemoryMeterRepository()
    sessions = SessionService(
        session_repository,
        workstations=workstation_repository,
        clients=client_repository,
        clock=clock,
        meters=meter_repository,
    )
    billing = BillingService(
        InMemoryChargeRepository(),
        sessions=session_repository,
        workstations=workstation_repository,
        clients=clients,
        catalog=catalog,
        clock=clock,
        meter_repository=meter_repository,
    )
    offline = OfflineReplayService(
        InMemoryOfflineReplayRepository(),
        sessions=sessions,
        session_repository=session_repository,
        workstations=workstation_repository,
        billing=billing,
        clock=clock,
    )
    return workstation, client, tariff, sessions, billing, offline


def make_operation(
    session_id: uuid.UUID,
    device_id: str,
    sequence: int,
    kind: OfflineOperationKind,
    clock: FixedClock,
    key: str,
    payload: dict[str, object] | None = None,
) -> OfflineOperation:
    return OfflineOperation.create(
        session_id=session_id,
        device_id=device_id,
        sequence=sequence,
        kind=kind,
        payload=payload or {},
        snapshot_version=1,
        idempotency_key=key,
        created_at=clock.now(),
    )


@pytest.mark.asyncio
async def test_offline_replay_is_duplicate_safe_and_returns_snapshot() -> None:
    clock = FixedClock()
    workstation, client, tariff, sessions, billing, offline = await build_offline_services(clock)
    session = await sessions.start(
        workstation.id,
        created_by="device",
        client_id=client.id,
        source="device",
        tariff_id=tariff.id,
        idempotency_key="offline-session",
    )
    clock.current += datetime.timedelta(minutes=7)
    operation = make_operation(
        session.id,
        workstation.device_id,
        1,
        OfflineOperationKind.METER_DELTA,
        clock,
        "offline-meter-1",
        {"minutes": 2},
    )
    batch = OfflineBatch(1, workstation.device_id, session.id, (operation,))

    first = await offline.replay(batch, actor_device_id=workstation.device_id)
    second = await offline.replay(batch, actor_device_id=workstation.device_id)

    assert first.results[0].status is OfflineOperationStatus.APPLIED
    assert second.results[0].status is OfflineOperationStatus.DUPLICATE
    assert first.snapshot is not None
    assert first.snapshot.meter is not None
    assert first.snapshot.meter.status is MeterStatus.RUNNING
    assert (await billing.get_meter(session.id)).billed_cents == 20

    conflicting = make_operation(
        session.id,
        workstation.device_id,
        2,
        OfflineOperationKind.METER_DELTA,
        clock,
        "offline-meter-1",
        {"minutes": 3},
    )
    conflict = await offline.replay(
        OfflineBatch(1, workstation.device_id, session.id, (conflicting,)),
        actor_device_id=workstation.device_id,
    )
    assert conflict.results[0].status is OfflineOperationStatus.CONFLICT


@pytest.mark.asyncio
async def test_offline_stop_is_replayed_and_gap_is_rejected() -> None:
    clock = FixedClock()
    workstation, client, _tariff, sessions, _billing, offline = await build_offline_services(clock)
    session = await sessions.start(
        workstation.id,
        created_by="device",
        client_id=client.id,
        source="device",
        idempotency_key="offline-session-stop",
    )
    operation = make_operation(
        session.id,
        workstation.device_id,
        1,
        OfflineOperationKind.STOP,
        clock,
        "offline-stop-1",
    )
    stopped = await offline.replay(
        OfflineBatch(1, workstation.device_id, session.id, (operation,)),
        actor_device_id=workstation.device_id,
    )
    assert stopped.results[0].status is OfflineOperationStatus.APPLIED
    assert stopped.snapshot is not None
    assert stopped.snapshot.session.status.value == "completed"

    gap = make_operation(
        session.id,
        workstation.device_id,
        3,
        OfflineOperationKind.LOCK,
        clock,
        "offline-gap-3",
    )
    result = await offline.replay(
        OfflineBatch(1, workstation.device_id, session.id, (gap,)),
        actor_device_id=workstation.device_id,
    )
    assert result.results[0].status is OfflineOperationStatus.CONFLICT
