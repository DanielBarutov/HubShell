import datetime
import uuid
from types import SimpleNamespace

import pytest

from gameclub_backend.application.errors import ApplicationError, ErrorCode
from gameclub_backend.modules.catalog.application.service import CatalogService
from gameclub_backend.modules.catalog.domain import TariffAudience, TariffSaleChannel
from gameclub_backend.modules.catalog.infrastructure.memory import InMemoryCatalogRepository
from gameclub_backend.modules.direct_payments.application.service import GuestSessionPaymentService
from gameclub_backend.modules.direct_payments.domain import DirectPaymentStatus
from gameclub_backend.modules.direct_payments.infrastructure.memory import (
    InMemoryGuestSessionPaymentRepository,
)
from gameclub_backend.modules.payment_methods.domain import PaymentPart
from gameclub_backend.modules.workstations.application.service import WorkstationService
from gameclub_backend.modules.workstations.infrastructure.memory import (
    InMemoryWorkstationRepository,
)

pytestmark = pytest.mark.unit


class FixedClock:
    current = datetime.datetime(2026, 9, 30, 12, tzinfo=datetime.UTC)

    def now(self) -> datetime.datetime:
        return self.current


class RecordingCash:
    def __init__(self) -> None:
        self.calls: list[tuple[uuid.UUID, int, str]] = []

    async def settle(
        self,
        shift_id: uuid.UUID,
        amount_cents: int,
        payment_idempotency_key: str,
        actor_id: str,
    ) -> None:
        self.calls.append((shift_id, amount_cents, payment_idempotency_key))


class ActiveSessionLookup:
    def __init__(self, active: object | None = object()) -> None:
        self.active = active

    async def get_active_for_workstation(self, workstation_id: uuid.UUID) -> object | None:
        return self.active


async def build_guest_payment_service(
    *,
    group_id: str | None = "vip",
    audience: TariffAudience = TariffAudience.GUEST,
    sale_channel: TariffSaleChannel = TariffSaleChannel.BOTH,
    price_cents: int = 500,
    workstations=None,
    active_sessions=None,
):
    clock = FixedClock()
    catalog = CatalogService(InMemoryCatalogRepository())
    tariff = await catalog.create_tariff(
        "Гостевой пакет",
        group_id,
        duration_minutes=60,
        price_cents=price_cents,
        valid_from=clock.current,
        valid_to=None,
        audience=audience,
        sale_channel=sale_channel,
    )
    cash = RecordingCash()
    service = GuestSessionPaymentService(
        InMemoryGuestSessionPaymentRepository(),
        tariffs=catalog,
        cash=cash,
        clock=clock,
        workstations=workstations,
        active_sessions=active_sessions,
    )
    workstation_id = uuid.uuid4()
    return service, tariff, cash, workstation_id


@pytest.mark.asyncio
async def test_guest_cash_tariff_confirms_and_records_normalized_name() -> None:
    """
    Проверяет продажу гостевого тарифа за наличные и сохранение очищенного имени гостя.
    """
    service, tariff, cash, workstation_id = await build_guest_payment_service()
    shift_id = uuid.uuid4()

    payment = await service.confirm(
        workstation_id,
        tariff.id,
        1,
        "  Гость  ",
        "operator",
        "guest-cash-1",
        [PaymentPart("cash", 500)],
        cash_shift_id=shift_id,
    )

    assert payment.status is DirectPaymentStatus.CONFIRMED
    assert payment.guest_name == "Гость"
    assert payment.total_price_cents == 500
    assert cash.calls == [(shift_id, 500, "guest-cash-1")]


@pytest.mark.asyncio
async def test_guest_transfer_tariff_does_not_require_cash_shift() -> None:
    """
    Проверяет подтверждение гостевой покупки переводом без создания наличной смены.
    """
    service, tariff, cash, workstation_id = await build_guest_payment_service()

    payment = await service.confirm(
        workstation_id,
        tariff.id,
        2,
        "Перевод",
        "operator",
        "guest-transfer-1",
        [PaymentPart("transfer", 1_000, "bank-1")],
    )

    assert payment.status is DirectPaymentStatus.CONFIRMED
    assert payment.tariff_quantity == 2
    assert cash.calls == []


@pytest.mark.asyncio
async def test_guest_duplicate_idempotency_key_reuses_payment_and_cash_settlement() -> None:
    """
    Проверяет, что повтор гостевой покупки не создаёт второй платёж и повторное списание кассы.
    """
    service, tariff, cash, workstation_id = await build_guest_payment_service()
    shift_id = uuid.uuid4()
    parts = [PaymentPart("cash", 500)]

    first = await service.confirm(
        workstation_id,
        tariff.id,
        1,
        "Гость",
        "operator",
        "guest-idempotent",
        parts,
        cash_shift_id=shift_id,
    )
    repeated = await service.confirm(
        workstation_id,
        tariff.id,
        1,
        "Гость",
        "operator",
        "guest-idempotent",
        parts,
        cash_shift_id=shift_id,
    )

    assert repeated.id == first.id
    assert len(cash.calls) == 1


@pytest.mark.asyncio
async def test_guest_idempotency_key_cannot_change_quantity() -> None:
    """
    Проверяет конфликт при повторном запросе с тем же ключом, но другой длительностью тарифа.
    """
    service, tariff, _cash, workstation_id = await build_guest_payment_service(price_cents=250)
    await service.confirm(
        workstation_id,
        tariff.id,
        1,
        "Гость",
        "operator",
        "guest-conflict",
        [PaymentPart("transfer", 250)],
    )

    with pytest.raises(ApplicationError) as error:
        await service.confirm(
            workstation_id,
            tariff.id,
            2,
            "Гость",
            "operator",
            "guest-conflict",
            [PaymentPart("transfer", 250)],
        )

    assert error.value.code is ErrorCode.CONFLICT


@pytest.mark.asyncio
async def test_guest_tariff_rejects_non_positive_quantity() -> None:
    """
    Проверяет отказ покупки гостевого тарифа с нулевым или отрицательным количеством.
    """
    service, tariff, _cash, workstation_id = await build_guest_payment_service()

    for quantity in (0, -1):
        with pytest.raises(ApplicationError) as error:
            await service.confirm(
                workstation_id,
                tariff.id,
                quantity,
                "Гость",
                "operator",
                f"guest-invalid-quantity-{quantity}",
                [PaymentPart("transfer", 500)],
            )
        assert error.value.code is ErrorCode.INVALID_ARGUMENT


@pytest.mark.asyncio
async def test_guest_cannot_buy_registered_only_tariff() -> None:
    """
    Проверяет, что тариф только для зарегистрированных клиентов недоступен гостю.
    """
    service, tariff, _cash, workstation_id = await build_guest_payment_service(
        audience=TariffAudience.REGISTERED
    )

    with pytest.raises(ApplicationError, match="not available for guests"):
        await service.confirm(
            workstation_id,
            tariff.id,
            1,
            "Гость",
            "operator",
            "guest-audience",
            [PaymentPart("transfer", 500)],
        )


@pytest.mark.asyncio
async def test_guest_cannot_buy_tariff_outside_operator_sale_channel() -> None:
    """
    Проверяет, что гостевая покупка отклоняется для тарифа без канала продажи оператором.
    """
    service, tariff, _cash, workstation_id = await build_guest_payment_service(
        sale_channel=TariffSaleChannel.SELF_SERVICE
    )

    with pytest.raises(ApplicationError, match="operator sale"):
        await service.confirm(
            workstation_id,
            tariff.id,
            1,
            "Гость",
            "operator",
            "guest-channel",
            [PaymentPart("transfer", 500)],
        )


@pytest.mark.asyncio
async def test_guest_sale_is_rejected_when_workstation_has_active_session() -> None:
    """
    Проверяет запрет продажи гостевого времени на уже занятом игровом месте.
    """
    service, tariff, _cash, workstation_id = await build_guest_payment_service(
        active_sessions=ActiveSessionLookup()
    )

    with pytest.raises(ApplicationError, match="active session"):
        await service.confirm(
            workstation_id,
            tariff.id,
            1,
            "Гость",
            "operator",
            "guest-active-session",
            [PaymentPart("transfer", 500)],
        )


@pytest.mark.asyncio
async def test_guest_sale_rejects_tariff_from_another_workstation_zone() -> None:
    """
    Проверяет, что гостевой тариф другой зоны нельзя продать для выбранного компьютера.
    """
    workstations = InMemoryWorkstationRepository()
    workstation = await WorkstationService(workstations).register(
        "guest-zone-device",
        "Guest PC",
        group_id="standard",
    )
    service, tariff, _cash, _unused_id = await build_guest_payment_service(
        group_id="vip",
        workstations=workstations,
    )

    with pytest.raises(ApplicationError, match="workstation zone"):
        await service.confirm(
            workstation.id,
            tariff.id,
            1,
            "Гость",
            "operator",
            "guest-zone",
            [PaymentPart("transfer", 500)],
        )


@pytest.mark.asyncio
async def test_guest_cash_payment_requires_cash_shift() -> None:
    """
    Проверяет обязательность открытой кассовой смены для наличной гостевой покупки.
    """
    service, tariff, _cash, workstation_id = await build_guest_payment_service()

    with pytest.raises(ApplicationError) as error:
        await service.confirm(
            workstation_id,
            tariff.id,
            1,
            "Гость",
            "operator",
            "guest-no-shift",
            [PaymentPart("cash", 500)],
        )

    assert error.value.code is ErrorCode.INVALID_ARGUMENT


@pytest.mark.asyncio
async def test_guest_mixed_cash_transfer_requires_exact_two_methods_and_total() -> None:
    """
    Проверяет допустимую смешанную оплату гостевого тарифа и отклонение двух одинаковых частей.
    """
    service, tariff, cash, workstation_id = await build_guest_payment_service()
    shift_id = uuid.uuid4()
    payment = await service.confirm(
        workstation_id,
        tariff.id,
        1,
        "Гость",
        "operator",
        "guest-mixed",
        [PaymentPart("cash", 200), PaymentPart("transfer", 300)],
        cash_shift_id=shift_id,
    )

    assert payment.status is DirectPaymentStatus.CONFIRMED
    assert cash.calls == [(shift_id, 200, "guest-mixed")]

    with pytest.raises(ApplicationError, match="Mixed payment"):
        await service.confirm(
            workstation_id,
            tariff.id,
            1,
            "Другой гость",
            "operator",
            "guest-invalid-mixed",
            [PaymentPart("transfer", 250), PaymentPart("transfer", 250)],
        )


@pytest.mark.asyncio
async def test_guest_additional_payment_is_bound_to_active_session_and_idempotent() -> None:
    session_id = uuid.uuid4()
    active = SimpleNamespace(id=session_id, client_id=None, source="guest_local_ledger")
    lookup = ActiveSessionLookup(active)
    service, tariff, cash, workstation_id = await build_guest_payment_service(
        active_sessions=lookup
    )
    shift = uuid.uuid4()
    request = dict(
        workstation_id=workstation_id,
        tariff_id=tariff.id,
        tariff_quantity=2,
        guest_name="Гость",
        actor_id="operator",
        idempotency_key="guest-addition",
        payment_parts=[PaymentPart("cash", 1000)],
        cash_shift_id=shift,
        session_id=session_id,
    )
    first = await service.confirm(**request)
    assert first.session_id == session_id
    assert first.duration_minutes == 60
    assert first.status is DirectPaymentStatus.CONFIRMED
    assert await service.confirm(**request) == first
    assert len(cash.calls) == 1
    with pytest.raises(ApplicationError, match="another payment"):
        await service.confirm(**(request | {"session_id": uuid.uuid4()}))


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "client_id,source,matches",
    [
        (uuid.uuid4(), "local_ledger", True),
        (None, "guest_local_ledger", False),
        (None, "local_ledger", True),
    ],
)
async def test_guest_addition_rejects_wrong_session(client_id, source, matches) -> None:
    session_id = uuid.uuid4()
    active = SimpleNamespace(
        id=session_id if matches else uuid.uuid4(), client_id=client_id, source=source
    )
    service, tariff, cash, workstation_id = await build_guest_payment_service(
        active_sessions=ActiveSessionLookup(active)
    )
    with pytest.raises(ApplicationError, match="does not match"):
        await service.confirm(
            workstation_id,
            tariff.id,
            1,
            "Гость",
            "operator",
            "wrong-session",
            [PaymentPart("cash", 500)],
            cash_shift_id=uuid.uuid4(),
            session_id=session_id,
        )
    assert cash.calls == []


@pytest.mark.asyncio
async def test_guest_snapshot_includes_all_paid_packages_and_advances_queue() -> None:
    import dataclasses

    from gameclub_backend.modules.clients.infrastructure.memory import InMemoryClientRepository
    from gameclub_backend.modules.sessions.application.service import SessionService
    from gameclub_backend.modules.sessions.domain import Session, SessionStatus
    from gameclub_backend.modules.sessions.infrastructure.memory import InMemorySessionRepository
    from gameclub_backend.modules.sessions.presentation.http import SessionSnapshotResponse

    clock = FixedClock()
    workstations = InMemoryWorkstationRepository()
    workstation = await WorkstationService(workstations).register("guest-snapshot", "Guest PC")
    catalog = CatalogService(InMemoryCatalogRepository())
    tariffs = [
        await catalog.create_tariff(
            name,
            None,
            duration_minutes=minutes,
            price_cents=500,
            valid_from=clock.now(),
            valid_to=None,
            audience=TariffAudience.GUEST,
        )
        for name, minutes in [("Три минуты", 3), ("Шесть минут", 6)]
    ]
    session_repository = InMemorySessionRepository()
    payment_repository = InMemoryGuestSessionPaymentRepository()
    payments = GuestSessionPaymentService(
        payment_repository,
        catalog,
        RecordingCash(),
        clock=clock,
        active_sessions=session_repository,
    )
    first = await payments.confirm(
        workstation.id,
        tariffs[0].id,
        1,
        "Гость",
        "operator",
        "snapshot-first",
        [PaymentPart("transfer", 500)],
    )
    session = Session(
        id=uuid.uuid4(),
        workstation_id=workstation.id,
        client_id=None,
        guest_name="Гость",
        status=SessionStatus.ACTIVE,
        started_at=clock.now() + datetime.timedelta(seconds=20),
        ended_at=None,
        source="guest_local_ledger",
        created_by="operator",
        created_at=clock.now(),
        idempotency_key="snapshot-session",
        tariff_id=tariffs[0].id,
        tariff_quantity=1,
        guest_payment_id=first.id,
    )
    await session_repository.save(session)
    addition = await payments.confirm(
        workstation.id,
        tariffs[1].id,
        1,
        "Гость",
        "operator",
        "snapshot-addition",
        [PaymentPart("transfer", 500)],
        session_id=session.id,
    )
    await payment_repository.save(
        dataclasses.replace(
            addition,
            id=uuid.uuid4(),
            idempotency_key="snapshot-pending",
            status=DirectPaymentStatus.PENDING,
        )
    )
    sessions = SessionService(
        session_repository,
        workstations=workstations,
        clients=InMemoryClientRepository(),
        tariffs=catalog,
        guest_payments=payments,
        clock=clock,
    )
    before_boundary = await sessions.snapshot(
        session.id, now=clock.now() + datetime.timedelta(seconds=30)
    )
    assert sum(item.remaining_minutes for item in before_boundary.guest_packages) == 9
    snapshot = await sessions.snapshot(session.id, now=clock.now() + datetime.timedelta(minutes=1))
    assert [
        (item.tariff_name, item.remaining_minutes, item.status) for item in snapshot.guest_packages
    ] == [
        ("Три минуты", 2, "active"),
        ("Шесть минут", 6, "queued"),
    ]
    response = SessionSnapshotResponse.from_domain(snapshot)
    assert sum(item.remaining_minutes for item in response.guest_packages) == 8
    later = await sessions.snapshot(session.id, now=clock.now() + datetime.timedelta(minutes=4))
    assert len(later.guest_packages) == 1
    assert later.guest_packages[0].remaining_minutes == 5
    assert later.guest_packages[0].status == "active"
    await session_repository.save(session.stop(clock.now() + datetime.timedelta(minutes=4)))
    assert (await sessions.snapshot(session.id)).guest_packages == ()
