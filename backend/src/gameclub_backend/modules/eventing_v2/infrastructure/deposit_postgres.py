"""Одна PostgreSQL-транзакция для V2 пополнения и его доставки."""

from __future__ import annotations

import datetime
import uuid

from sqlalchemy import DateTime, Integer, String, or_, select, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from gameclub_backend.application.audit import AuditEvent
from gameclub_backend.infrastructure.audit_postgres import AuditEventModel
from gameclub_backend.infrastructure.database import EngineProvider, open_session
from gameclub_backend.modules.cash_shifts.domain import (
    CashMovement,
    CashMovementDirection,
    CashShiftStatus,
)
from gameclub_backend.modules.cash_shifts.infrastructure.postgres import (
    CashMovementModel,
    CashShiftModel,
)
from gameclub_backend.modules.clients.application.ports import ClientBalanceTransactionWriter
from gameclub_backend.modules.clients.domain import BalanceOperation, BalanceOperationType
from gameclub_backend.modules.eventing_v2.application.deposit import (
    V2DepositCreditCommand,
    V2DepositCreditResult,
)
from gameclub_backend.modules.eventing_v2.domain import V2Event, V2EventType, V2OutgoingEventStatus
from gameclub_backend.modules.eventing_v2.infrastructure.lease_postgres import V2SessionLeaseModel
from gameclub_backend.modules.eventing_v2.infrastructure.postgres import (
    V2EventingBase,
    V2ServerOutboxModel,
)


class V2DepositCreditModel(V2EventingBase):
    """Неизменяемая связь payment operation, ledger и двух подтверждённых фактов."""

    __tablename__ = "v2_deposit_credits"

    payment_operation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    client_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    session_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    device_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    amount_delta_cents: Mapped[int] = mapped_column(Integer(), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    balance_operation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, unique=True
    )
    client_delivery_event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, unique=True
    )
    confirmed_domain_event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, unique=True
    )
    cash_shift_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    accepted_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    def to_result(self, *, is_duplicate: bool = False) -> V2DepositCreditResult:
        return V2DepositCreditResult(
            payment_operation_id=self.payment_operation_id,
            balance_operation_id=self.balance_operation_id,
            client_delivery_event_id=self.client_delivery_event_id,
            confirmed_domain_event_id=self.confirmed_domain_event_id,
            amount_delta_cents=self.amount_delta_cents,
            currency=self.currency,
            accepted_at=self.accepted_at,
            is_duplicate=is_duplicate,
        )


class PostgresV2DepositCreditRepository:
    """Единственная transaction boundary для server-owned пополнения V2."""

    def __init__(
        self, engine_provider: EngineProvider, *, clients: ClientBalanceTransactionWriter
    ) -> None:
        self._engine_provider = engine_provider
        self._clients = clients

    async def has_active_lease_for_client(self, client_id: uuid.UUID) -> bool:
        async with open_session(self._engine_provider) as session:
            lease_id = await session.scalar(
                select(V2SessionLeaseModel.session_id)
                .where(
                    V2SessionLeaseModel.client_id == client_id,
                    V2SessionLeaseModel.status == "active",
                    or_(
                        V2SessionLeaseModel.expires_at.is_(None),
                        V2SessionLeaseModel.expires_at >= datetime.datetime.now(datetime.UTC),
                    ),
                )
                .limit(1)
            )
            return lease_id is not None

    async def apply(
        self,
        command: V2DepositCreditCommand,
        accepted_at: datetime.datetime,
    ) -> V2DepositCreditResult:
        if accepted_at.tzinfo is None:
            raise ValueError("Deposit acceptance timestamp must include timezone")
        async with open_session(self._engine_provider) as session:
            async with session.begin():
                await session.execute(
                    text("SELECT pg_advisory_xact_lock(hashtext(:lock_key))"),
                    {"lock_key": f"v2-deposit:{command.payment_operation_id}"},
                )
                existing = await session.get(V2DepositCreditModel, command.payment_operation_id)
                if existing is not None:
                    if existing.request_hash != command.request_hash:
                        raise ValueError("Payment operation id belongs to another deposit request")
                    return existing.to_result(is_duplicate=True)

                lease = await session.scalar(
                    select(V2SessionLeaseModel)
                    .where(V2SessionLeaseModel.session_id == command.session_id)
                    .with_for_update()
                )
                now = datetime.datetime.now(datetime.UTC)
                if not (
                    lease
                    and lease.status == "active"
                    and lease.client_id == command.client_id
                    and lease.device_id == command.device_id
                    and (lease.expires_at is None or lease.expires_at >= now)
                ):
                    raise ValueError("No active V2 lease for deposit client/device/session")

                balance_operation = BalanceOperation(
                    id=uuid.uuid4(),
                    client_id=command.client_id,
                    amount_cents=command.amount_delta_cents,
                    bonus_amount=0,
                    reason=command.reason,
                    actor_id=command.actor_id,
                    idempotency_key=f"v2-deposit:{command.payment_operation_id}",
                    created_at=accepted_at,
                    operation_type=BalanceOperationType.TOP_UP,
                    payment_parts=command.payment_parts,
                )
                await self._record_cash_if_needed(session, command, accepted_at)
                if await self._clients.apply(session, balance_operation) is None:
                    raise ValueError("Client not found")

                client_event = self._client_delivery_event(command, accepted_at)
                domain_event = self._confirmed_domain_event(command, accepted_at)
                session.add(
                    V2ServerOutboxModel(
                        **V2ServerOutboxModel.values_from_domain(
                            self._outgoing(client_event, "v2.server-events")
                        )
                    )
                )
                session.add(
                    V2ServerOutboxModel(
                        **V2ServerOutboxModel.values_from_domain(
                            self._outgoing(
                                domain_event,
                                "v2.confirmed-domain-events",
                            )
                        )
                    )
                )
                session.add(
                    AuditEventModel.from_domain(
                        AuditEvent(
                            id=uuid.uuid4(),
                            actor_id=command.actor_id,
                            action="v2.deposit_credit.applied",
                            resource_path=(
                                f"clients/{command.client_id}/deposits/"
                                f"{command.payment_operation_id}"
                            ),
                            outcome="success",
                            status_code=201,
                            request_id=str(command.payment_operation_id),
                            created_at=accepted_at,
                        )
                    )
                )
                deposit = V2DepositCreditModel(
                    payment_operation_id=command.payment_operation_id,
                    request_hash=command.request_hash,
                    client_id=command.client_id,
                    session_id=command.session_id,
                    device_id=command.device_id,
                    amount_delta_cents=command.amount_delta_cents,
                    currency=command.currency,
                    balance_operation_id=balance_operation.id,
                    client_delivery_event_id=client_event.event_id,
                    confirmed_domain_event_id=domain_event.event_id,
                    cash_shift_id=command.cash_shift_id,
                    accepted_at=accepted_at,
                )
                session.add(deposit)
                return deposit.to_result()

    @staticmethod
    async def _record_cash_if_needed(
        session,
        command: V2DepositCreditCommand,
        accepted_at: datetime.datetime,
    ) -> None:
        cash_amount = sum(
            part.amount_cents for part in command.payment_parts if part.method == "cash"
        )
        if not cash_amount:
            return
        if command.cash_shift_id is None:
            raise ValueError("Cash deposit requires a cash shift")
        shift = await session.scalar(
            select(CashShiftModel)
            .where(CashShiftModel.id == command.cash_shift_id)
            .with_for_update()
        )
        if shift is None:
            raise ValueError("Cash shift not found")
        if shift.status != CashShiftStatus.OPEN.value:
            raise ValueError("Only an open cash shift can receive a deposit")
        movement = CashMovement(
            id=uuid.uuid4(),
            shift_id=command.cash_shift_id,
            direction=CashMovementDirection.CASH_IN,
            amount_cents=cash_amount,
            reason="Пополнение баланса клиента V2",
            actor_id=command.actor_id,
            idempotency_key=f"v2-deposit-cash:{command.payment_operation_id}",
            created_at=accepted_at,
            reference_type="v2_deposit_credit",
            reference_id=str(command.payment_operation_id),
        )
        shift.expected_close_cents += movement.delta_cents
        session.add(CashMovementModel.from_domain(movement))

    @staticmethod
    def _client_delivery_event(
        command: V2DepositCreditCommand,
        accepted_at: datetime.datetime,
    ) -> V2Event:
        return V2Event.create(
            operation_id=command.payment_operation_id,
            event_type=V2EventType.BALANCE_CREDIT_APPLIED,
            producer_id="server:deposit",
            client_id=command.client_id,
            session_id=command.session_id,
            device_id=command.device_id,
            sequence=1,
            occurred_at=accepted_at,
            payload={
                "amount_delta_cents": command.amount_delta_cents,
                "currency": command.currency,
                "deposit_operation_id": str(command.payment_operation_id),
                "payment_method_types": sorted({part.method for part in command.payment_parts}),
            },
        )

    @staticmethod
    def _confirmed_domain_event(
        command: V2DepositCreditCommand,
        accepted_at: datetime.datetime,
    ) -> V2Event:
        """Создать server-only финансовый факт для аналитики.

        Суммы по методам оплаты нужны аналитике для сверки денег, но не нужны
        автономному ПК. Ссылки платёжного провайдера намеренно не попадают ни
        в один Kafka-факт.
        """
        return V2Event.create(
            operation_id=command.payment_operation_id,
            event_type=V2EventType.BALANCE_CREDIT_APPLIED,
            producer_id="server:deposit",
            client_id=command.client_id,
            session_id=command.session_id,
            device_id=command.device_id,
            sequence=1,
            occurred_at=accepted_at,
            payload={
                "amount_delta_cents": command.amount_delta_cents,
                "currency": command.currency,
                "deposit_operation_id": str(command.payment_operation_id),
                "payment_parts": [
                    {"amount_cents": part.amount_cents, "method": part.method}
                    for part in command.payment_parts
                ],
            },
        )

    @staticmethod
    def _outgoing(event: V2Event, topic: str):
        from gameclub_backend.modules.eventing_v2.domain import V2OutgoingServerEvent

        return V2OutgoingServerEvent(
            event=event,
            topic=topic,
            partition_key=f"client-session:{event.client_id}:{event.session_id}",
            created_at=event.occurred_at,
            status=V2OutgoingEventStatus.PENDING,
        )
