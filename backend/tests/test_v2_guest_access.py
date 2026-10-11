import datetime
import uuid

import pytest

from gameclub_backend.modules.direct_payments.domain import DirectPaymentStatus, GuestSessionPayment
from gameclub_backend.modules.eventing_v2.application.guest_access import (
    GUEST_SOURCE,
    V2GuestAccessService,
)
from gameclub_backend.modules.eventing_v2.infrastructure.guest_access_memory import (
    InMemoryGuestAccessGrantRepository,
)
from gameclub_backend.modules.payment_methods.domain import PaymentPart
from gameclub_backend.modules.sessions.domain import Session, SessionStatus
from gameclub_backend.modules.workstations.domain import (
    Workstation,
    WorkstationSessionMode,
    WorkstationStatus,
)

pytestmark = pytest.mark.unit


class FakeWorkstations:
    def __init__(self, workstation: Workstation) -> None:
        self.workstation = workstation

    async def get(self, workstation_id: uuid.UUID) -> Workstation | None:
        return self.workstation if workstation_id == self.workstation.id else None

    async def get_by_device_id(self, device_id: str) -> Workstation:
        if device_id != self.workstation.device_id:
            raise ValueError("device not found")
        return self.workstation


class FakeRepository:
    def __init__(self) -> None:
        self.items: dict[uuid.UUID, Session] = {}

    async def get_active_for_workstation(self, workstation_id: uuid.UUID):
        return next(
            (
                item
                for item in self.items.values()
                if item.workstation_id == workstation_id and item.status is SessionStatus.ACTIVE
            ),
            None,
        )

    async def get_by_idempotency_key(self, key: str):
        return next((item for item in self.items.values() if item.idempotency_key == key), None)

    async def get(self, session_id: uuid.UUID):
        return self.items.get(session_id)


class FakeTariffs:
    async def get_tariff(self, tariff_id: uuid.UUID):
        return type(
            "Tariff",
            (),
            {"name": "Гостевой час", "duration_minutes": 60, "id": tariff_id},
        )()


class FakeSessions:
    def __init__(self, workstation: Workstation) -> None:
        self._repository = FakeRepository()
        self._tariffs = FakeTariffs()
        self.workstation = workstation

    async def start(self, **kwargs):
        existing = await self._repository.get_by_idempotency_key(kwargs["idempotency_key"])
        if existing is not None:
            return existing
        now = datetime.datetime.now(datetime.UTC)
        session = Session(
            id=uuid.uuid4(),
            workstation_id=kwargs["workstation_id"],
            client_id=None,
            guest_name=kwargs["guest_name"],
            status=SessionStatus.ACTIVE,
            started_at=now,
            ended_at=None,
            source=kwargs["source"],
            created_by=kwargs["created_by"],
            created_at=now,
            idempotency_key=kwargs["idempotency_key"],
            guest_id=kwargs.get("guest_id"),
            tariff_id=kwargs.get("tariff_id"),
            tariff_quantity=kwargs["tariff_quantity"],
            guest_payment_id=kwargs["guest_payment_id"],
        )
        self._repository.items[session.id] = session
        return session

    async def stop(self, session_id: uuid.UUID, device_id: str):
        session = await self._repository.get(session_id)
        stopped = session.stop(datetime.datetime.now(datetime.UTC))
        self._repository.items[session_id] = stopped
        return stopped


class FakeSigner:
    def sign(self, payload: bytes) -> bytes:
        return b"signature:" + payload[:8]


def make_payment(workstation_id: uuid.UUID, tariff_id: uuid.UUID) -> GuestSessionPayment:
    now = datetime.datetime.now(datetime.UTC)
    return GuestSessionPayment(
        id=uuid.uuid4(),
        workstation_id=workstation_id,
        tariff_id=tariff_id,
        tariff_quantity=1,
        guest_id=None,
        guest_name="Гость",
        total_price_cents=100,
        payment_parts=(PaymentPart(method="transfer", amount_cents=100),),
        cash_shift_id=None,
        status=DirectPaymentStatus.CONFIRMED,
        idempotency_key="payment-key",
        created_at=now,
    )


@pytest.mark.asyncio
async def test_guest_v2_access_is_prepared_redeemed_and_idempotent() -> None:
    """Проверяет заявленное поведение backend."""
    workstation = Workstation(
        id=uuid.uuid4(),
        device_id="guest-device",
        name="PC-01",
        status=WorkstationStatus.ONLINE,
        session_mode=WorkstationSessionMode.LOCAL_LEDGER,
    )
    tariff_id = uuid.uuid4()
    payment = make_payment(workstation.id, tariff_id)

    class Payments:
        async def get(self, payment_id: uuid.UUID):
            return payment if payment_id == payment.id else None

    sessions = FakeSessions(workstation)
    service = V2GuestAccessService(
        payments=Payments(),
        workstations=FakeWorkstations(workstation),
        sessions=sessions,
        grants=InMemoryGuestAccessGrantRepository(),
        signing_key_id="test-key",
        signer=FakeSigner(),
    )

    grant = await service.prepare(payment.id)
    first = await service.redeem(workstation.device_id)
    second = await service.redeem(workstation.device_id)

    assert first.payload.grant_id == str(grant.id)
    assert first.payload.session_id == second.payload.session_id
    assert first == second
    session_id = uuid.UUID(first.payload.session_id)
    assert sessions._repository.items[session_id].source == GUEST_SOURCE

    await service.stop(workstation.device_id, session_id, payment.id)
    assert (
        await sessions._repository.get(session_id)
    ).status is SessionStatus.COMPLETED
