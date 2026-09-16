import asyncio
import datetime

import pytest

from gameclub_backend.application.errors import ApplicationError, ErrorCode
from gameclub_backend.modules.clients.application.service import ClientService
from gameclub_backend.modules.clients.infrastructure.memory import InMemoryClientRepository
from gameclub_backend.modules.reservations.application.service import ReservationService
from gameclub_backend.modules.reservations.domain import ReservationStatus
from gameclub_backend.modules.reservations.infrastructure.memory import (
    InMemoryReservationRepository,
)
from gameclub_backend.modules.sessions.application.service import SessionService
from gameclub_backend.modules.sessions.domain import SessionStatus
from gameclub_backend.modules.sessions.infrastructure.memory import InMemorySessionRepository
from gameclub_backend.modules.workstations.application.service import WorkstationService
from gameclub_backend.modules.workstations.infrastructure.memory import (
    InMemoryWorkstationRepository,
)

pytestmark = pytest.mark.unit

async def test_reservation_rejects_conflicts_and_allows_reuse_after_cancel() -> None:
    """
    Проверяет сценарий «test_reservation_rejects_conflicts_and_allows_reuse_after_cancel» и
    подтверждает ожидаемый публичный результат согласно соответствующему бизнес-правилу.
    """
    workstation_repository = InMemoryWorkstationRepository()
    workstation_service = WorkstationService(workstation_repository)
    workstation = await workstation_service.register("device-01", "PC-01")
    client_repository = InMemoryClientRepository()
    client_service = ClientService(client_repository)
    client = await client_service.create("NightFox")
    reservation_service = ReservationService(
        InMemoryReservationRepository(),
        workstations=workstation_repository,
        clients=client_repository,
    )
    start_at = datetime.datetime(2026, 8, 27, 18, tzinfo=datetime.UTC)
    end_at = start_at + datetime.timedelta(hours=2)

    reservation = await reservation_service.create(
        workstation_ids=[workstation.id],
        start_at=start_at,
        end_at=end_at,
        created_by="operator",
        client_id=client.id,
    )

    with pytest.raises(ApplicationError) as error:
        await reservation_service.create(
            workstation_ids=[workstation.id],
            start_at=start_at + datetime.timedelta(minutes=30),
            end_at=end_at,
            created_by="operator",
            guest_name="Guest",
        )

    assert error.value.code is ErrorCode.CONFLICT
    cancelled = await reservation_service.cancel(reservation.id)
    assert cancelled.status.value == "cancelled"
    replacement = await reservation_service.create(
        workstation_ids=[workstation.id],
        start_at=start_at,
        end_at=end_at,
        created_by="operator",
        guest_name="Guest",
    )
    assert replacement.id != reservation.id

    repeated = await reservation_service.create(
        workstation_ids=[workstation.id],
        start_at=end_at,
        end_at=end_at + datetime.timedelta(hours=2),
        created_by="operator",
        guest_name="Another name is ignored for a repeated key",
        idempotency_key="reservation-002",
    )
    repeated_again = await reservation_service.create(
        workstation_ids=[workstation.id],
        start_at=end_at,
        end_at=end_at + datetime.timedelta(hours=2),
        created_by="operator",
        guest_name="Another name is ignored for a repeated key",
        idempotency_key="reservation-002",
    )
    assert repeated_again.id == repeated.id
    with pytest.raises(ApplicationError) as mismatch_error:
        await reservation_service.create(
            workstation_ids=[workstation.id],
            start_at=end_at,
            end_at=end_at + datetime.timedelta(hours=2),
            created_by="operator",
            guest_name="Different payload",
            idempotency_key="reservation-002",
        )
    assert mismatch_error.value.code is ErrorCode.CONFLICT
    with pytest.raises(ApplicationError) as author_error:
        await reservation_service.create(
            workstation_ids=[workstation.id],
            start_at=end_at,
            end_at=end_at + datetime.timedelta(hours=2),
            created_by="another-operator",
            guest_name="Another name is ignored for a repeated key",
            idempotency_key="reservation-002",
        )
    assert author_error.value.code is ErrorCode.CONFLICT


async def test_reservation_availability_returns_conflict_and_disabled_reason() -> None:
    """
    Проверяет сценарий «test_reservation_availability_returns_conflict_and_disabled_reason» и
    подтверждает ожидаемый публичный результат согласно соответствующему бизнес-правилу.
    """
    workstation_repository = InMemoryWorkstationRepository()
    workstation_service = WorkstationService(workstation_repository)
    workstation = await workstation_service.register("device-availability", "PC-01")
    disabled = await workstation_service.register("device-disabled", "PC-02")
    await workstation_service.disable(disabled.id, "Maintenance")
    client_repository = InMemoryClientRepository()
    client = await ClientService(client_repository).create("AvailabilityFox")
    service = ReservationService(
        InMemoryReservationRepository(),
        workstations=workstation_repository,
        clients=client_repository,
    )
    start_at = datetime.datetime(2026, 8, 27, 20, tzinfo=datetime.UTC)
    end_at = start_at + datetime.timedelta(hours=1)
    reservation = await service.create(
        workstation_ids=[workstation.id],
        start_at=start_at,
        end_at=end_at,
        created_by="operator",
        client_id=client.id,
    )

    conflict = await service.check_availability([workstation.id], start_at, end_at)
    unavailable = await service.check_availability([disabled.id], start_at, end_at)
    free = await service.check_availability(
        [workstation.id], end_at, end_at + datetime.timedelta(hours=1)
    )

    assert conflict.available is False
    assert conflict.conflicting_reservation_ids == (reservation.id,)
    assert conflict.reason == "workstation_reserved"
    assert unavailable.available is False
    assert unavailable.reason == "workstation_disabled"
    assert free.available is True
    assert free.reason is None


async def test_reservation_conflict_is_serialized_for_concurrent_creates() -> None:
    """
    Проверяет сценарий «test_reservation_conflict_is_serialized_for_concurrent_creates» и
    подтверждает ожидаемый публичный результат согласно соответствующему бизнес-правилу.
    """
    workstation_repository = InMemoryWorkstationRepository()
    workstation = await WorkstationService(workstation_repository).register(
        "device-concurrent-reservation",
        "PC-01",
    )
    client_repository = InMemoryClientRepository()
    client = await ClientService(client_repository).create("ReservationFox")
    reservation_service = ReservationService(
        InMemoryReservationRepository(),
        workstations=workstation_repository,
        clients=client_repository,
    )
    start_at = datetime.datetime(2026, 8, 27, 18, tzinfo=datetime.UTC)
    end_at = start_at + datetime.timedelta(hours=2)

    results = await asyncio.gather(
        *(
            reservation_service.create(
                workstation_ids=[workstation.id],
                start_at=start_at,
                end_at=end_at,
                created_by="operator",
                client_id=client.id,
            )
            for _ in range(2)
        ),
        return_exceptions=True,
    )

    reservations = [item for item in results if not isinstance(item, Exception)]
    conflicts = [item for item in results if isinstance(item, ApplicationError)]
    assert len(reservations) == 1
    assert len(conflicts) == 1
    assert conflicts[0].code is ErrorCode.CONFLICT


async def test_reservation_lifecycle_rejects_invalid_transitions() -> None:
    """
    Проверяет сценарий «test_reservation_lifecycle_rejects_invalid_transitions» и подтверждает
    ожидаемый публичный результат согласно соответствующему бизнес-правилу.
    """
    workstation_repository = InMemoryWorkstationRepository()
    workstation = await WorkstationService(workstation_repository).register(
        "device-lifecycle-reservation",
        "PC-01",
    )
    client_repository = InMemoryClientRepository()
    client = await ClientService(client_repository).create("LifecycleFox")
    service = ReservationService(
        InMemoryReservationRepository(),
        workstations=workstation_repository,
        clients=client_repository,
    )
    start_at = datetime.datetime(2026, 8, 27, 18, tzinfo=datetime.UTC)
    reservation = await service.create(
        workstation_ids=[workstation.id],
        start_at=start_at,
        end_at=start_at + datetime.timedelta(hours=1),
        created_by="operator",
        client_id=client.id,
    )

    with pytest.raises(ApplicationError) as complete_error:
        await service.complete(reservation.id)
    assert complete_error.value.code is ErrorCode.CONFLICT

    updated = await service.update(
        reservation.id,
        workstation_ids=[workstation.id],
        start_at=start_at + datetime.timedelta(minutes=15),
        end_at=start_at + datetime.timedelta(hours=1, minutes=15),
        guest_name="Updated guest",
        notes="Updated note",
    )
    assert updated.guest_name == "Updated guest"
    assert updated.notes == "Updated note"

    active = await service.activate(reservation.id)
    assert active.status is ReservationStatus.ACTIVE
    completed = await service.complete(reservation.id)
    assert completed.status is ReservationStatus.COMPLETED

    with pytest.raises(ApplicationError) as cancel_error:
        await service.cancel(reservation.id)
    assert cancel_error.value.code is ErrorCode.CONFLICT


async def test_reservation_no_show_requires_grace_period() -> None:
    """
    Проверяет сценарий «test_reservation_no_show_requires_grace_period» и подтверждает ожидаемый
    публичный результат согласно соответствующему бизнес-правилу.
    """
    class FixedClock:
        def __init__(self) -> None:
            self.current = datetime.datetime(2026, 8, 27, 17, 59, tzinfo=datetime.UTC)

        def now(self) -> datetime.datetime:
            return self.current

    workstation_repository = InMemoryWorkstationRepository()
    workstation = await WorkstationService(workstation_repository).register(
        "device-grace-reservation",
        "PC-01",
    )
    client_repository = InMemoryClientRepository()
    client = await ClientService(client_repository).create("GraceReservationFox")
    clock = FixedClock()
    service = ReservationService(
        InMemoryReservationRepository(),
        workstations=workstation_repository,
        clients=client_repository,
        clock=clock,
        grace_period_minutes=15,
    )
    start_at = datetime.datetime(2026, 8, 27, 18, tzinfo=datetime.UTC)
    reservation = await service.create(
        workstation_ids=[workstation.id],
        start_at=start_at,
        end_at=start_at + datetime.timedelta(hours=1),
        created_by="operator",
        client_id=client.id,
    )

    with pytest.raises(ApplicationError) as early_error:
        await service.mark_no_show(reservation.id)
    assert early_error.value.code is ErrorCode.CONFLICT

    clock.current = start_at + datetime.timedelta(minutes=14, seconds=59)
    with pytest.raises(ApplicationError) as grace_error:
        await service.mark_no_show(reservation.id)
    assert grace_error.value.code is ErrorCode.CONFLICT

    clock.current = start_at + datetime.timedelta(minutes=15)
    no_show = await service.mark_no_show(reservation.id)
    assert no_show.status is ReservationStatus.NO_SHOW


async def test_reservation_sweep_is_idempotent_and_skips_changed_state() -> None:
    """
    Проверяет сценарий «test_reservation_sweep_is_idempotent_and_skips_changed_state» и
    подтверждает ожидаемый публичный результат согласно соответствующему бизнес-правилу.
    """
    workstation_repository = InMemoryWorkstationRepository()
    workstation = await WorkstationService(workstation_repository).register(
        "device-sweep-reservation",
        "PC-01",
    )
    client_repository = InMemoryClientRepository()
    client = await ClientService(client_repository).create("SweepReservationFox")
    repository = InMemoryReservationRepository()
    service = ReservationService(
        repository,
        workstations=workstation_repository,
        clients=client_repository,
        grace_period_minutes=15,
    )
    start_at = datetime.datetime(2026, 8, 27, 18, tzinfo=datetime.UTC)
    reservation = await service.create(
        workstation_ids=[workstation.id],
        start_at=start_at,
        end_at=start_at + datetime.timedelta(hours=1),
        created_by="operator",
        client_id=client.id,
    )
    now = start_at + datetime.timedelta(minutes=15)

    changed = await service.activate(reservation.id)
    assert changed.status is ReservationStatus.ACTIVE
    assert await service.sweep_no_shows(now) == []

    second_reservation = await service.create(
        workstation_ids=[workstation.id],
        start_at=start_at + datetime.timedelta(hours=2),
        end_at=start_at + datetime.timedelta(hours=3),
        created_by="operator",
        guest_name="Future guest",
    )
    swept = await service.sweep_no_shows(start_at + datetime.timedelta(hours=3))
    assert [item.id for item in swept] == [second_reservation.id]
    assert (await repository.get(second_reservation.id)).status is ReservationStatus.NO_SHOW
    assert await service.sweep_no_shows(start_at + datetime.timedelta(hours=3)) == []


async def test_session_lifecycle_is_idempotent_and_serializes_active_workstation() -> None:
    """
    Проверяет сценарий «test_session_lifecycle_is_idempotent_and_serializes_active_workstation»
    и подтверждает ожидаемый публичный результат согласно соответствующему бизнес-правилу.
    """
    workstation_repository = InMemoryWorkstationRepository()
    workstation = await WorkstationService(workstation_repository).register(
        "device-session-01",
        "PC-01",
    )
    client_repository = InMemoryClientRepository()
    client = await ClientService(client_repository).create("SessionFox")
    repository = InMemorySessionRepository()
    service = SessionService(
        repository,
        workstations=workstation_repository,
        clients=client_repository,
    )

    results = await asyncio.gather(
        *(
            service.start(
                workstation_id=workstation.id,
                client_id=client.id,
                created_by="operator",
                idempotency_key="session-001",
            )
            for _ in range(4)
        )
    )
    session = results[0]
    assert {item.id for item in results} == {session.id}
    assert session.status is SessionStatus.ACTIVE
    assert (await service.list(active_only=True)) == [session]

    with pytest.raises(ApplicationError) as mismatch_error:
        await service.start(
            workstation_id=workstation.id,
            client_id=client.id,
            created_by="operator",
            source="device",
            idempotency_key="session-001",
        )
    assert mismatch_error.value.code is ErrorCode.CONFLICT
    with pytest.raises(ApplicationError) as author_error:
        await service.start(
            workstation_id=workstation.id,
            client_id=client.id,
            created_by="another-operator",
            idempotency_key="session-001",
        )
    assert author_error.value.code is ErrorCode.CONFLICT

    stopped = await service.stop(session.id)
    repeated_stop = await service.stop(session.id)
    assert stopped.status is SessionStatus.COMPLETED
    assert repeated_stop == stopped

    second_session = await service.start(
        workstation.id,
        created_by="operator",
        client_id=client.id,
        idempotency_key="session-interrupt-001",
    )
    interrupted = await service.interrupt(
        second_session.id,
        interrupted_by="operator",
        reason="Клиент закончил раньше",
        idempotency_key="interrupt-001",
    )
    repeated_interrupt = await service.interrupt(
        second_session.id,
        interrupted_by="operator",
        reason="Клиент закончил раньше",
        idempotency_key="interrupt-001",
    )
    assert interrupted.status is SessionStatus.COMPLETED
    assert repeated_interrupt == interrupted


async def test_session_rejects_a_second_active_session_and_disabled_workstation() -> None:
    """
    Проверяет сценарий «test_session_rejects_a_second_active_session_and_disabled_workstation» и
    подтверждает ожидаемый публичный результат согласно соответствующему бизнес-правилу.
    """
    workstation_repository = InMemoryWorkstationRepository()
    workstation_service = WorkstationService(workstation_repository)
    first = await workstation_service.register("device-session-02", "PC-01")
    disabled = await workstation_service.register("device-session-03", "PC-02")
    await workstation_service.disable(disabled.id, "Maintenance")
    client_repository = InMemoryClientRepository()
    await ClientService(client_repository).create("SecondSessionFox")
    service = SessionService(
        InMemorySessionRepository(),
        workstations=workstation_repository,
        clients=client_repository,
    )

    await service.start(first.id, created_by="operator", guest_name="Guest")
    with pytest.raises(ApplicationError) as active_error:
        await service.start(first.id, created_by="operator", guest_name="Another guest")
    with pytest.raises(ApplicationError) as disabled_error:
        await service.start(disabled.id, created_by="operator", guest_name="Guest")

    assert active_error.value.code is ErrorCode.CONFLICT
    assert disabled_error.value.code is ErrorCode.CONFLICT


async def test_entry_decision_protects_reservations_and_allows_assigned_client() -> None:
    """
    Проверяет сценарий «test_entry_decision_protects_reservations_and_allows_assigned_client» и
    подтверждает ожидаемый публичный результат согласно соответствующему бизнес-правилу.
    """
    class FixedClock:
        current = datetime.datetime(2026, 8, 27, 12, tzinfo=datetime.UTC)

        def now(self) -> datetime.datetime:
            return self.current

    clock = FixedClock()
    workstations = InMemoryWorkstationRepository()
    workstation = await WorkstationService(workstations).register("entry-device", "Entry PC")
    clients = InMemoryClientRepository()
    client_service = ClientService(clients, clock=clock)
    assigned = await client_service.create("EntryAssigned")
    other = await client_service.create("EntryOther")
    reservations = ReservationService(
        InMemoryReservationRepository(),
        workstations=workstations,
        clients=clients,
        clock=clock,
    )
    reservation = await reservations.create(
        workstation_ids=[workstation.id],
        start_at=clock.current + datetime.timedelta(minutes=20),
        end_at=clock.current + datetime.timedelta(minutes=80),
        created_by="operator",
        client_id=assigned.id,
    )

    anonymous = await reservations.check_entry(workstation.id, now=clock.current)
    assert not anonymous.allowed
    assert anonymous.reason == "reservation_client_required"
    assert anonymous.reservation_id == reservation.id

    matching = await reservations.check_entry(
        workstation.id,
        client_id=assigned.id,
        now=clock.current,
    )
    assert matching.allowed
    assert matching.reason == "allowed"

    mismatch = await reservations.check_entry(
        workstation.id,
        client_id=other.id,
        now=clock.current,
    )
    assert not mismatch.allowed
    assert mismatch.reason == "reservation_client_mismatch"


async def test_session_rejects_one_client_on_two_workstations() -> None:
    """
    Проверяет сценарий «test_session_rejects_one_client_on_two_workstations» и подтверждает
    ожидаемый публичный результат согласно соответствующему бизнес-правилу.
    """
    workstations = InMemoryWorkstationRepository()
    workstation_service = WorkstationService(workstations)
    first = await workstation_service.register("client-session-device-1", "PC-01")
    second = await workstation_service.register("client-session-device-2", "PC-02")
    clients = InMemoryClientRepository()
    client = await ClientService(clients).create("OneSessionFox")
    service = SessionService(
        InMemorySessionRepository(),
        workstations=workstations,
        clients=clients,
    )

    await service.start(
        first.id,
        created_by="operator",
        client_id=client.id,
        idempotency_key="one-client-session-1",
    )
    with pytest.raises(ApplicationError) as error:
        await service.start(
            second.id,
            created_by="operator",
            client_id=client.id,
            idempotency_key="one-client-session-2",
        )

    assert error.value.code is ErrorCode.CONFLICT
    assert error.value.message == "Client already has an active session"


async def test_session_validates_linked_reservation_ownership() -> None:
    """
    Проверяет сценарий «test_session_validates_linked_reservation_ownership» и подтверждает
    ожидаемый публичный результат согласно соответствующему бизнес-правилу.
    """
    workstation_repository = InMemoryWorkstationRepository()
    workstation_service = WorkstationService(workstation_repository)
    workstation = await workstation_service.register("device-session-04", "PC-01")
    other_workstation = await workstation_service.register("device-session-05", "PC-02")
    client_repository = InMemoryClientRepository()
    client = await ClientService(client_repository).create("LinkedSessionFox")
    reservation_service = ReservationService(
        InMemoryReservationRepository(),
        workstations=workstation_repository,
        clients=client_repository,
    )
    start_at = datetime.datetime(2030, 1, 15, 18, tzinfo=datetime.UTC)
    reservation = await reservation_service.create(
        workstation_ids=[workstation.id],
        start_at=start_at,
        end_at=start_at + datetime.timedelta(hours=1),
        created_by="operator",
        client_id=client.id,
    )
    service = SessionService(
        InMemorySessionRepository(),
        workstations=workstation_repository,
        clients=client_repository,
        reservations=reservation_service,
    )

    session = await service.start(
        workstation_id=workstation.id,
        created_by="operator",
        client_id=client.id,
        reservation_id=reservation.id,
        idempotency_key="session-linked-001",
    )
    with pytest.raises(ApplicationError) as mismatch_error:
        await service.start(
            workstation_id=other_workstation.id,
            created_by="operator",
            guest_name="Wrong workstation",
            reservation_id=reservation.id,
            idempotency_key="session-linked-002",
        )

    assert session.reservation_id == reservation.id
    assert mismatch_error.value.code is ErrorCode.CONFLICT
