from __future__ import annotations

import dataclasses
import datetime
import uuid
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, Boolean, CheckConstraint, DateTime, Integer, String, select, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from gameclub_backend.modules.clients.application.bonus import (
    BonusCommand,
    BonusEarningCommand,
    BonusOperation,
)
from gameclub_backend.modules.clients.bonus import (
    BonusAccrual,
    BonusOperationKind,
    BonusPolicy,
    BonusWallet,
)
from gameclub_backend.modules.clients.domain import BalanceOperation

if TYPE_CHECKING:
    from gameclub_backend.modules.clients.infrastructure.postgres import ClientModel


class BonusBase(DeclarativeBase):
    pass


class BonusWalletModel(BonusBase):
    __tablename__ = "client_bonus_wallets"
    __table_args__ = (
        CheckConstraint(
            "total_cents >= 0 AND reserved_cents >= 0 AND reserved_cents <= total_cents"
        ),
    )

    client_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    total_cents: Mapped[int] = mapped_column(BigInteger)
    reserved_cents: Mapped[int] = mapped_column(BigInteger, default=0)

    def to_domain(self) -> BonusWallet:
        return BonusWallet(self.total_cents, self.reserved_cents)


class BonusReservationModel(BonusBase):
    __tablename__ = "client_bonus_reservations"
    __table_args__ = (CheckConstraint("remaining_cents >= 0"),)

    client_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    session_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    remaining_cents: Mapped[int] = mapped_column(BigInteger)


class BonusOperationModel(BonusBase):
    __tablename__ = "client_bonus_operations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    client_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    kind: Mapped[str] = mapped_column(String(32))
    amount_cents: Mapped[int] = mapped_column(BigInteger)
    actor_id: Mapped[str] = mapped_column(String(128))
    reason: Mapped[str] = mapped_column(String(255))
    idempotency_key: Mapped[str] = mapped_column(String(128), unique=True)
    session_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    total_after_cents: Mapped[int] = mapped_column(BigInteger)
    reserved_after_cents: Mapped[int] = mapped_column(BigInteger)
    session_reserved_after_cents: Mapped[int] = mapped_column(BigInteger)
    total_delta_cents: Mapped[int] = mapped_column(BigInteger)
    reserved_delta_cents: Mapped[int] = mapped_column(BigInteger)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True))

    def to_domain(self) -> BonusOperation:
        return BonusOperation(
            id=self.id,
            command=BonusCommand(
                self.client_id,
                BonusOperationKind(self.kind),
                self.amount_cents,
                self.actor_id,
                self.reason,
                self.idempotency_key,
                self.session_id,
            ),
            wallet_after=BonusWallet(self.total_after_cents, self.reserved_after_cents),
            session_reserved_after_cents=self.session_reserved_after_cents,
            total_delta_cents=self.total_delta_cents,
            reserved_delta_cents=self.reserved_delta_cents,
            created_at=self.created_at,
        )

    @classmethod
    def from_domain(cls, operation: BonusOperation) -> BonusOperationModel:
        return cls(
            id=operation.id,
            **dataclasses.asdict(operation.command),
            total_after_cents=operation.wallet_after.total_cents,
            reserved_after_cents=operation.wallet_after.reserved_cents,
            session_reserved_after_cents=operation.session_reserved_after_cents,
            total_delta_cents=operation.total_delta_cents,
            reserved_delta_cents=operation.reserved_delta_cents,
            created_at=operation.created_at,
        )


async def lock_bonus_wallet(
    session: AsyncSession, client_id: uuid.UUID, legacy_units: int
) -> BonusWalletModel:
    """Caller holds the client row lock, including before first wallet creation."""
    wallet = await session.get(BonusWalletModel, client_id)
    if wallet is None:
        initial = BonusWallet(legacy_units * 100)
        wallet = BonusWalletModel(
            client_id=client_id, total_cents=initial.total_cents, reserved_cents=0
        )
        session.add(wallet)
        if legacy_units:
            command = BonusCommand(
                client_id,
                BonusOperationKind.ADJUST,
                initial.total_cents,
                "bonus-migration",
                "Legacy bonus opening balance",
                f"bonus-opening:{client_id}",
            )
            session.add(
                BonusOperationModel.from_domain(
                    BonusOperation(
                        uuid.uuid4(),
                        command,
                        initial,
                        0,
                        initial.total_cents,
                        0,
                        datetime.datetime.now(datetime.UTC),
                    )
                )
            )
        await session.flush()
    return wallet


async def find_bonus_operation(
    session: AsyncSession, command: BonusCommand
) -> BonusOperation | None:
    await session.execute(
        text("SELECT pg_advisory_xact_lock(hashtext(:key))"),
        {"key": f"bonus-operation:{command.idempotency_key}"},
    )
    existing = await session.scalar(
        select(BonusOperationModel).where(
            BonusOperationModel.idempotency_key == command.idempotency_key
        )
    )
    if existing is None:
        return None
    operation = existing.to_domain()
    if operation.command != command:
        raise ValueError("Idempotency key belongs to another bonus operation")
    return operation


async def apply_bonus_locked(
    session: AsyncSession, client: ClientModel, command: BonusCommand, now: datetime.datetime
) -> BonusOperation:
    existing = await find_bonus_operation(session, command)
    if existing is not None:
        return existing
    wallet = await lock_bonus_wallet(session, client.id, client.balance_bonus)
    before = wallet.to_domain()
    reservation = None
    if command.session_id is not None:
        reservation = await session.get(BonusReservationModel, (client.id, command.session_id))
    held = reservation.remaining_cents if reservation else 0
    after, next_held = command.apply(before, held, client.balance_cents)
    wallet.total_cents = after.total_cents
    wallet.reserved_cents = after.reserved_cents
    if command.session_id is not None:
        if reservation is None:
            reservation = BonusReservationModel(
                client_id=client.id, session_id=command.session_id, remaining_cents=next_held
            )
            session.add(reservation)
        else:
            reservation.remaining_cents = next_held
    client.balance_bonus = after.total_cents // 100
    client.updated_at = now
    operation = BonusOperation(
        uuid.uuid4(),
        command,
        after,
        next_held,
        after.total_cents - before.total_cents,
        after.reserved_cents - before.reserved_cents,
        now,
    )
    session.add(BonusOperationModel.from_domain(operation))
    await session.flush()
    return operation


class BonusProgramModel(BonusBase):
    __tablename__ = "client_bonus_program"
    __table_args__ = (CheckConstraint("id = 1"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    policy: Mapped[dict] = mapped_column(JSONB)


class BonusProgramChangeModel(BonusBase):
    __tablename__ = "client_bonus_program_changes"
    idempotency_key: Mapped[str] = mapped_column(String(128), primary_key=True)
    policy: Mapped[dict] = mapped_column(JSONB)
    actor_id: Mapped[str] = mapped_column(String(128))
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True))


class BonusSessionModel(BonusBase):
    __tablename__ = "client_bonus_sessions"
    session_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    client_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    policy: Mapped[dict] = mapped_column(JSONB)
    finished: Mapped[bool] = mapped_column(Boolean, default=False)


class BonusDebitModel(BonusBase):
    __tablename__ = "client_bonus_debits"
    __table_args__ = (CheckConstraint("money_cents >= 0 AND paid_cents BETWEEN 0 AND money_cents"),)
    operation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    client_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    money_cents: Mapped[int] = mapped_column(BigInteger)
    paid_cents: Mapped[int] = mapped_column(BigInteger)
    receipt_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    source_key: Mapped[str | None] = mapped_column(String(160), nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True))


class BonusEarningModel(BonusBase):
    __tablename__ = "client_bonus_earnings"
    __table_args__ = (
        CheckConstraint("rate_bps BETWEEN 0 AND 10000"),
        CheckConstraint("money_cents >= 0 AND paid_cents BETWEEN 0 AND money_cents"),
        CheckConstraint("released_bonus_cents >= 0"),
    )
    source_key: Mapped[str] = mapped_column(String(160), primary_key=True)
    client_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    source: Mapped[str] = mapped_column(String(32))
    session_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    rate_bps: Mapped[int] = mapped_column(Integer)
    money_cents: Mapped[int] = mapped_column(BigInteger, default=0)
    paid_cents: Mapped[int] = mapped_column(BigInteger, default=0)
    released_bonus_cents: Mapped[int] = mapped_column(BigInteger, default=0)

    def accrual(self) -> BonusAccrual:
        return BonusAccrual(
            self.rate_bps, self.money_cents, self.paid_cents, self.released_bonus_cents
        )


class BonusReceiptModel(BonusBase):
    __tablename__ = "client_bonus_receipts"
    receipt_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    client_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    payload: Mapped[dict] = mapped_column(JSONB)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True))


async def read_bonus_policy(session: AsyncSession) -> BonusPolicy:
    row = await session.get(BonusProgramModel, 1)
    return BonusPolicy(**row.policy) if row else BonusPolicy()


async def freeze_bonus_session(
    session: AsyncSession,
    client_id: uuid.UUID,
    session_id: uuid.UUID,
    policy: BonusPolicy | None = None,
) -> BonusSessionModel:
    row = await session.get(BonusSessionModel, session_id)
    if row is None:
        row = BonusSessionModel(
            session_id=session_id,
            client_id=client_id,
            policy=dataclasses.asdict(policy or BonusPolicy(enabled=False)),
            finished=False,
        )
        session.add(row)
        await session.flush()
    if row.client_id != client_id:
        raise ValueError("Bonus session belongs to another client")
    return row


async def release_bonus_earning(
    session: AsyncSession, client: ClientModel, earning: BonusEarningModel, now: datetime.datetime
) -> None:
    eligible = earning.session_id is None
    if earning.session_id is not None:
        gate = await session.get(BonusSessionModel, earning.session_id)
        eligible = gate is not None and gate.finished
    after, delta = earning.accrual().release(session_finished=eligible)
    if not delta:
        return
    key = uuid.uuid5(uuid.NAMESPACE_URL, f"bonus:{earning.source_key}:{after.released_bonus_cents}")
    await apply_bonus_locked(
        session,
        client,
        BonusCommand(
            client.id,
            BonusOperationKind.ADJUST,
            delta,
            "bonus-program",
            f"Начисление бонусов: {earning.source_key}",
            f"bonus-earning:{key}",
        ),
        now,
    )
    earning.released_bonus_cents = after.released_bonus_cents


async def record_bonus_balance_movement(
    session: AsyncSession,
    client: ClientModel,
    operation: BalanceOperation,
    previous_balance_cents: int,
) -> None:
    """Track every monetary debt, including expenses that do not earn bonuses."""
    if operation.amount_cents < 0:
        amount = -operation.amount_cents
        session.add(
            BonusDebitModel(
                operation_id=operation.id,
                client_id=client.id,
                money_cents=amount,
                paid_cents=min(amount, max(previous_balance_cents, 0)),
                receipt_id=None,
                source_key=None,
                created_at=operation.created_at,
            )
        )
        return
    repayment = min(operation.amount_cents, max(-previous_balance_cents, 0))
    if not repayment:
        return
    debts = (
        await session.scalars(
            select(BonusDebitModel)
            .where(
                BonusDebitModel.client_id == client.id,
                BonusDebitModel.paid_cents < BonusDebitModel.money_cents,
            )
            .order_by(BonusDebitModel.created_at, BonusDebitModel.operation_id)
        )
    ).all()
    for debt in debts:
        paid = min(repayment, debt.money_cents - debt.paid_cents)
        debt.paid_cents += paid
        repayment -= paid
        if debt.source_key:
            earning = await session.get(BonusEarningModel, debt.source_key)
            earning.paid_cents += paid
            await release_bonus_earning(session, client, earning, operation.created_at)
        if not repayment:
            break
    if repayment:
        raise ValueError("Monetary debt has no matching bonus debt ledger")


async def confirm_bonus_earning(
    session: AsyncSession, client: ClientModel, command: BonusEarningCommand, now: datetime.datetime
) -> None:
    await session.execute(
        text("SELECT pg_advisory_xact_lock(hashtext(:key))"),
        {"key": f"bonus-receipt:{command.receipt_id}"},
    )
    existing = await session.get(BonusReceiptModel, command.receipt_id)
    if existing is not None:
        if existing.payload != command.payload():
            raise ValueError("Bonus receipt belongs to another confirmed earning")
        return
    if command.session_id is not None:
        await freeze_bonus_session(session, client.id, command.session_id)
    earning = await session.get(BonusEarningModel, command.source_key)
    rate = command.policy.rate(command.source)
    if earning is None:
        earning = BonusEarningModel(
            source_key=command.source_key,
            client_id=client.id,
            source=command.source.value,
            session_id=command.session_id,
            rate_bps=rate,
            money_cents=0,
            paid_cents=0,
            released_bonus_cents=0,
        )
        session.add(earning)
    elif (
        earning.client_id != client.id
        or earning.source != command.source.value
        or earning.session_id != command.session_id
        or earning.rate_bps != rate
    ):
        raise ValueError("Bonus source policy or identity has changed")
    money = paid = command.external_paid_cents
    for operation_id in command.debit_operation_ids:
        debit = await session.get(BonusDebitModel, operation_id)
        if debit is None or debit.client_id != client.id or debit.receipt_id is not None:
            raise ValueError("Bonus source does not match its monetary debit")
        debit.source_key = command.source_key
        debit.receipt_id = command.receipt_id
        money += debit.money_cents
        paid += debit.paid_cents
    earning.money_cents += money
    earning.paid_cents += paid
    session.add(
        BonusReceiptModel(
            receipt_id=command.receipt_id,
            client_id=client.id,
            payload=command.payload(),
            created_at=now,
        )
    )
    await release_bonus_earning(session, client, earning, now)
    await session.flush()
