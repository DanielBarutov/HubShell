import dataclasses
import datetime
import os
import uuid

import pytest
from sqlalchemy.ext.asyncio import create_async_engine

from gameclub_backend.application.errors import ApplicationError, ErrorCode
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

    async def list(self, workstation_id, active_only=False):
        return [
            item
            for item in self._repository.items.values()
            if item.workstation_id == workstation_id
            and (not active_only or item.status is SessionStatus.ACTIVE)
        ]

    async def get(self, session_id):
        session = await self._repository.get(session_id)
        if session is None:
            raise ApplicationError(ErrorCode.NOT_FOUND, "Session not found")
        return session

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
    assert (await sessions._repository.get(session_id)).status is SessionStatus.COMPLETED


@pytest.mark.asyncio
async def test_guest_additions_keep_session_queue_order_and_cannot_survive_exit() -> None:
    workstation = Workstation(
        id=uuid.uuid4(),
        device_id="guest-device",
        name="PC-01",
        status=WorkstationStatus.ONLINE,
        session_mode=WorkstationSessionMode.LOCAL_LEDGER,
    )
    first_payment = make_payment(workstation.id, uuid.uuid4())
    payments = {first_payment.id: first_payment}

    class Payments:
        async def get(self, payment_id):
            return payments.get(payment_id)

    sessions = FakeSessions(workstation)
    grants = InMemoryGuestAccessGrantRepository()
    service = V2GuestAccessService(
        payments=Payments(),
        workstations=FakeWorkstations(workstation),
        sessions=sessions,
        grants=grants,
        signing_key_id="key",
        signer=FakeSigner(),
    )
    initial_grant = await service.prepare(first_payment.id)
    initial = await service.redeem(workstation.device_id)
    session_id = uuid.UUID(initial.payload.session_id)
    assert await service.prepare(first_payment.id) == await grants.get_by_payment(first_payment.id)
    addition = dataclasses.replace(
        make_payment(workstation.id, uuid.uuid4()),
        session_id=session_id,
        duration_minutes=90,
        tariff_name="Полтора часа",
        tariff_quantity=2,
    )
    payments[addition.id] = addition
    extension = await service.prepare(addition.id)
    # Initial clients must never receive a paid addition as a new access grant.
    assert (await service.redeem(workstation.device_id)).payload.schema_version == 1
    signed = await service.redeem(workstation.device_id, session_id, (initial_grant.id,))
    assert signed.payload.schema_version == 2
    assert signed.payload.session_id == str(session_id)
    assert signed.payload.duration_minutes == 90
    assert signed.payload.tariff_quantity == 2
    assert signed.payload.tariff_id == str(addition.tariff_id)
    assert await service.redeem(workstation.device_id, session_id, (initial_grant.id,)) == signed
    assert len(sessions._repository.items) == 1
    second_payment = dataclasses.replace(
        make_payment(workstation.id, uuid.uuid4()), session_id=session_id
    )
    payments[second_payment.id] = second_payment
    second_grant = await service.prepare(second_payment.id)
    assert await service.redeem(workstation.device_id, session_id, (initial_grant.id,)) == signed
    second = await service.redeem(
        workstation.device_id, session_id, (initial_grant.id, extension.id)
    )
    assert second.payload.grant_id == str(second_grant.id)
    with pytest.raises(ApplicationError, match="No pending"):
        await service.redeem(
            workstation.device_id, session_id, (initial_grant.id, extension.id, second_grant.id)
        )
    await service.stop(workstation.device_id, session_id, first_payment.id)
    with pytest.raises(ApplicationError, match="no longer active"):
        await service.redeem(workstation.device_id, session_id)
    with pytest.raises(ApplicationError, match="no longer active"):
        await service.prepare(addition.id)
    # A new guest starts with only their own paid package, despite old additions.
    new_payment = make_payment(workstation.id, uuid.uuid4())
    payments[new_payment.id] = new_payment
    new_grant = await service.prepare(new_payment.id)
    new_signed = await service.redeem(workstation.device_id)
    assert new_signed.payload.grant_id == str(new_grant.id)
    assert new_signed.payload.session_id != str(session_id)


@pytest.mark.integration
@pytest.mark.postgres
@pytest.mark.asyncio
async def test_postgres_guest_payment_and_queue_persist_across_repository_restart() -> None:
    from sqlalchemy import text

    from gameclub_backend.modules.direct_payments.infrastructure.postgres import (
        PostgresGuestSessionPaymentRepository,
    )
    from gameclub_backend.modules.eventing_v2.application.guest_access import GuestAccessGrant
    from gameclub_backend.modules.eventing_v2.infrastructure.guest_access_postgres import (
        PostgresGuestAccessGrantRepository,
    )

    dsn = os.getenv("GAMECLUB_TEST_POSTGRES_DSN")
    if not dsn:
        pytest.skip("Set GAMECLUB_TEST_POSTGRES_DSN to test guest queue persistence")
    engine = create_async_engine(dsn)
    workstation_id, session_id = uuid.uuid4(), uuid.uuid4()
    now = datetime.datetime.now(datetime.UTC)
    payment = dataclasses.replace(
        make_payment(workstation_id, uuid.uuid4()),
        session_id=session_id,
        idempotency_key=f"guest-queue-{uuid.uuid4()}",
        duration_minutes=90,
        tariff_name="Полтора часа",
    )
    grant = GuestAccessGrant(
        id=uuid.uuid4(),
        payment_id=payment.id,
        workstation_id=workstation_id,
        session_id=session_id,
        is_extension=True,
        expires_at=now - datetime.timedelta(minutes=1),
    )
    try:
        payments = PostgresGuestSessionPaymentRepository(lambda: engine)
        assert await payments.save(payment) == payment
        assert (
            await PostgresGuestSessionPaymentRepository(lambda: engine).get(payment.id) == payment
        )
        with pytest.raises(ValueError, match="another payment"):
            await payments.save(dataclasses.replace(payment, session_id=uuid.uuid4()))
        await PostgresGuestAccessGrantRepository(lambda: engine).save(grant)
        grants = PostgresGuestAccessGrantRepository(lambda: engine)
        assert await grants.get_pending_for_workstation(workstation_id, now) is None
        assert await grants.get_pending_for_workstation(workstation_id, now, session_id) == grant
        signed = dataclasses.replace(
            grant, payload=b"snapshot", signature=b"signature", signing_key_id="key"
        )
        assert await grants.save(signed) == signed
        assert (
            await PostgresGuestAccessGrantRepository(lambda: engine).get_pending_for_workstation(
                workstation_id,
                now,
                session_id,
            )
            == signed
        )
        assert (
            await grants.get_pending_for_workstation(workstation_id, now, session_id, (grant.id,))
            is None
        )
        assert await grants.get_pending_for_workstation(workstation_id, now, uuid.uuid4()) is None
    finally:
        async with engine.begin() as connection:
            await connection.execute(
                text("DELETE FROM v2_guest_access_grants WHERE id = :id"), {"id": grant.id}
            )
            await connection.execute(
                text("DELETE FROM guest_session_payments WHERE id = :id"), {"id": payment.id}
            )
        await engine.dispose()
