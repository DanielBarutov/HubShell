"""The Clients-owned writer for V2 facts in a caller-owned PostgreSQL transaction."""

import datetime
import uuid

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from gameclub_backend.modules.clients.application.bonus import (
    BonusCommand,
    BonusEarningCommand,
    BonusMinutePayment,
)
from gameclub_backend.modules.clients.bonus import BonusOperationKind, BonusPolicy, BonusSource
from gameclub_backend.modules.clients.domain import BalanceOperation, BalanceOperationType, Client
from gameclub_backend.modules.clients.infrastructure.bonus_postgres import (
    BonusEarningModel,
    BonusReservationModel,
    apply_bonus_locked,
    confirm_bonus_earning,
    freeze_bonus_session,
    record_bonus_balance_movement,
    release_bonus_earning,
)
from gameclub_backend.modules.clients.infrastructure.postgres import (
    BalanceOperationModel,
    ClientModel,
)


class PostgresClientBalanceTransactionWriter:
    async def apply_bonus_minute(
        self, transaction: AsyncSession, payment: BonusMinutePayment
    ) -> bool:
        client = await transaction.get(
            ClientModel, payment.client_id, with_for_update=True, populate_existing=True
        )
        if client is None:
            return False
        gate = await freeze_bonus_session(
            transaction, payment.client_id, payment.session_id, policy=BonusPolicy(enabled=False)
        )
        policy = BonusPolicy(**gate.policy)
        if (
            gate.finished
            or not policy.enabled
            or policy.payment_limit_bps != payment.payment_limit_bps
        ):
            return False
        reservation = await transaction.get(
            BonusReservationModel, (payment.client_id, payment.session_id)
        )
        held = reservation.remaining_cents if reservation else 0
        expected_bonus = (
            min(held, payment.price_cents * payment.payment_limit_bps // 10000)
            if client.balance_cents >= 0
            else 0
        )
        if (
            payment.bonus_cents != expected_bonus
            or client.balance_cents - payment.money_cents < payment.minimum_balance_cents
        ):
            return False
        if payment.bonus_cents:
            await apply_bonus_locked(
                transaction,
                client,
                BonusCommand(
                    payment.client_id,
                    BonusOperationKind.CONSUME,
                    payment.bonus_cents,
                    payment.actor_id,
                    "Оплата поминутной игры бонусами",
                    f"v2-minute-bonus:{payment.operation_id}",
                    payment.session_id,
                ),
                payment.occurred_at,
            )
        if payment.money_cents:
            operation = BalanceOperation(
                id=uuid.uuid5(payment.operation_id, "v2-per-minute-balance-operation"),
                client_id=payment.client_id,
                amount_cents=-payment.money_cents,
                bonus_amount=0,
                reason=f"Поминутное списание за сессию {payment.session_id}",
                actor_id=payment.actor_id,
                idempotency_key=f"v2-per-minute-debit:{payment.operation_id}",
                created_at=payment.occurred_at,
                operation_type=BalanceOperationType.DEBIT,
            )
            if await self.apply(transaction, operation, payment.minimum_balance_cents) is None:
                raise RuntimeError("Locked minute payment changed after validation")
            await self.confirm_minute(
                transaction,
                payment.client_id,
                payment.session_id,
                operation.id,
                payment.operation_id,
                payment.actor_id,
                payment.occurred_at,
            )
        await transaction.flush()
        return True

    async def release_bonus_reservation(
        self,
        transaction: AsyncSession,
        client_id: uuid.UUID,
        session_id: uuid.UUID,
        operation_id: uuid.UUID,
        now: datetime.datetime,
    ) -> None:
        client = await transaction.get(ClientModel, client_id, with_for_update=True)
        if client is None:
            raise ValueError("Client not found")
        await apply_bonus_locked(
            transaction,
            client,
            BonusCommand(
                client_id,
                BonusOperationKind.RELEASE,
                0,
                "bonus-program",
                "Освобождение бонусов после отключения оплаты",
                f"v2-bonus-disable:{operation_id}",
                session_id,
            ),
            now,
        )

    async def apply(
        self,
        transaction: AsyncSession,
        operation: BalanceOperation,
        minimum_balance_cents: int = 0,
        *,
        accepted_at: datetime.datetime | None = None,
    ) -> Client | None:
        if operation.bonus_amount:
            raise ValueError("V2 monetary writer cannot issue manual bonus adjustments")
        await transaction.execute(
            text("SELECT pg_advisory_xact_lock(hashtext(:key))"), {"key": operation.idempotency_key}
        )
        client = await transaction.get(ClientModel, operation.client_id, with_for_update=True)
        if client is None:
            return None
        previous = await transaction.scalar(
            select(BalanceOperationModel).where(
                BalanceOperationModel.idempotency_key == operation.idempotency_key
            )
        )
        if previous is not None:
            stored = previous.to_domain()
            if (
                stored.client_id != operation.client_id
                or stored.amount_cents != operation.amount_cents
                or stored.bonus_amount != operation.bonus_amount
                or stored.reason != operation.reason
                or stored.actor_id != operation.actor_id
                or stored.operation_type != operation.operation_type
                or stored.payment_parts != operation.payment_parts
            ):
                raise ValueError("Idempotency key belongs to another balance operation")
            return client.to_domain()
        next_balance = client.balance_cents + operation.amount_cents
        if operation.amount_cents < 0 and next_balance < minimum_balance_cents:
            return None
        previous_balance = client.balance_cents
        client.balance_cents = next_balance
        client.updated_at = accepted_at or operation.created_at
        await record_bonus_balance_movement(transaction, client, operation, previous_balance)
        transaction.add(BalanceOperationModel.from_domain(operation))
        await transaction.flush()
        return client.to_domain()

    async def confirm_minute(
        self,
        transaction: AsyncSession,
        client_id: uuid.UUID,
        session_id: uuid.UUID,
        operation_id: uuid.UUID,
        receipt_id: uuid.UUID,
        actor_id: str,
        now: datetime.datetime,
    ) -> None:
        client = await transaction.get(ClientModel, client_id, with_for_update=True)
        if client is None:
            raise ValueError("Client not found")
        # Pre-upgrade sessions did not accept the new program and do not earn retroactively.
        gate = await freeze_bonus_session(
            transaction, client_id, session_id, policy=BonusPolicy(enabled=False)
        )
        await confirm_bonus_earning(
            transaction,
            client,
            BonusEarningCommand(
                receipt_id=receipt_id,
                client_id=client_id,
                source_key=f"minutes:{session_id}",
                source=BonusSource.GAME,
                policy=BonusPolicy(**gate.policy),
                debit_operation_ids=(operation_id,),
                session_id=session_id,
                actor_id=actor_id,
            ),
            now,
        )

    async def finish_session(
        self,
        transaction: AsyncSession,
        client_id: uuid.UUID,
        session_id: uuid.UUID,
        now: datetime.datetime,
    ) -> None:
        client = await transaction.get(ClientModel, client_id, with_for_update=True)
        if client is None:
            raise ValueError("Client not found")
        gate = await freeze_bonus_session(
            transaction, client_id, session_id, policy=BonusPolicy(enabled=False)
        )
        gate.finished = True
        earnings = (
            await transaction.scalars(
                select(BonusEarningModel).where(
                    BonusEarningModel.client_id == client_id,
                    BonusEarningModel.session_id == session_id,
                )
            )
        ).all()
        for earning in earnings:
            await release_bonus_earning(transaction, client, earning, now)
        held = await transaction.get(BonusReservationModel, (client_id, session_id))
        if held is not None and held.remaining_cents:
            await apply_bonus_locked(
                transaction,
                client,
                BonusCommand(
                    client_id,
                    BonusOperationKind.RELEASE,
                    0,
                    "bonus-program",
                    "Освобождение бонусов после завершения сессии",
                    f"bonus-session-release:{session_id}",
                    session_id,
                ),
                now,
            )
