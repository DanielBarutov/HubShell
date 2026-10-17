import asyncio
import dataclasses
import datetime
import uuid

from gameclub_backend.modules.clients.application.bonus import (
    BonusCommand,
    BonusDebt,
    BonusEarningCommand,
    BonusOperation,
    BonusPaymentState,
)
from gameclub_backend.modules.clients.application.bonus_reporting import (
    BonusPeriodTotals,
    BonusReport,
)
from gameclub_backend.modules.clients.bonus import (
    BonusAccrual,
    BonusOperationKind,
    BonusPolicy,
    BonusWallet,
)
from gameclub_backend.modules.clients.domain import BalanceOperation, Client


class InMemoryClientRepository:
    async def read_bonus_report(
        self, start_at: datetime.datetime, end_at: datetime.datetime
    ) -> BonusReport:
        async with self._balance_lock:
            totals = BonusPeriodTotals()
            for operation in self._bonus_operations.values():
                if start_at <= operation.created_at < end_at:
                    totals = totals.record(
                        operation.command.kind,
                        operation.command.idempotency_key,
                        operation.total_delta_cents,
                        operation.reserved_delta_cents,
                    )
            wallets = dict(self._bonus_wallets)
            for client in self._items.values():
                wallets.setdefault(client.id, BonusWallet(client.balance_bonus * 100))
            total = sum(wallet.total_cents for wallet in wallets.values())
            reserved = sum(wallet.reserved_cents for wallet in wallets.values())
            pending = sum(
                accrual.pending_bonus_cents for _, accrual in self._bonus_earnings.values()
            )
            return BonusReport(
                start_at,
                end_at,
                datetime.datetime.now(datetime.UTC),
                totals,
                total,
                total - reserved,
                reserved,
                pending,
            )

    def __init__(self) -> None:
        self._items: dict[uuid.UUID, Client] = {}
        self._operations: dict[str, BalanceOperation] = {}
        self._balance_lock = asyncio.Lock()
        self._bonus_wallets: dict[uuid.UUID, BonusWallet] = {}
        self._bonus_reservations: dict[tuple[uuid.UUID, uuid.UUID], int] = {}
        self._bonus_operations: dict[str, BonusOperation] = {}
        self._bonus_policy = BonusPolicy()
        self._bonus_policy_changes: dict[str, tuple[str, BonusPolicy]] = {}
        self._bonus_sessions: dict[uuid.UUID, tuple[uuid.UUID, BonusPolicy, bool]] = {}
        self._bonus_debits: dict[uuid.UUID, BonusDebt] = {}
        self._bonus_earnings: dict[str, tuple[BonusEarningCommand, BonusAccrual]] = {}
        self._bonus_receipts: dict[uuid.UUID, dict[str, object]] = {}

    async def get(self, client_id: uuid.UUID) -> Client | None:
        return self._items.get(client_id)

    async def get_by_nickname(self, nickname: str) -> Client | None:
        normalized = nickname.strip().lower()
        return next(
            (item for item in self._items.values() if item.nickname.lower() == normalized),
            None,
        )

    async def get_by_phone(self, phone: str) -> Client | None:
        return next((item for item in self._items.values() if item.phone == phone), None)

    async def list_clients(self) -> list[Client]:
        return sorted(
            (item for item in self._items.values() if item.blocked_at is None),
            key=lambda item: item.nickname.lower(),
        )

    async def search(self, query: str, field: str) -> list[Client]:
        if field == "nickname":
            result = [
                item
                for item in self._items.values()
                if item.blocked_at is None and query in item.nickname.lower()
            ]
        else:
            result = [
                item
                for item in self._items.values()
                if item.blocked_at is None and item.phone and query in item.phone
            ]
        return sorted(result, key=lambda item: item.nickname.lower())

    async def save(self, client: Client) -> Client:
        async with self._balance_lock:
            current = self._items.get(client.id)
            if current is not None:
                client = dataclasses.replace(
                    client,
                    balance_cents=current.balance_cents,
                    balance_bonus=current.balance_bonus,
                    created_at=current.created_at,
                )
            if current is None and client.balance_cents < 0:
                self._bonus_debits[client.id] = BonusDebt(
                    client.id, client.id, -client.balance_cents, 0, client.created_at
                )
            self._items[client.id] = client
            return client

    async def consume_password_reset_login(
        self,
        client_id: uuid.UUID,
        now: datetime.datetime,
    ) -> Client:
        current = self._items.get(client_id)
        if current is None:
            raise ValueError("Client not found")
        if not current.password_reset_required or current.password_reset_login_used:
            raise ValueError("Passwordless reset login already used")
        updated = dataclasses.replace(current, password_reset_login_used=True, updated_at=now)
        self._items[client_id] = updated
        return updated

    async def delete(self, client_id: uuid.UUID) -> None:
        self._items.pop(client_id, None)

    async def add_operation(self, operation: BalanceOperation) -> BalanceOperation:
        self._operations[operation.idempotency_key] = operation
        return operation

    async def get_operation_by_key(self, idempotency_key: str) -> BalanceOperation | None:
        return self._operations.get(idempotency_key)

    async def list_operations(
        self,
        client_id: uuid.UUID,
        limit: int,
    ) -> list[BalanceOperation]:
        operations = [item for item in self._operations.values() if item.client_id == client_id]
        operations.sort(key=lambda item: item.created_at, reverse=True)
        return operations[:limit]

    async def apply_balance_operation(
        self,
        client: Client,
        operation: BalanceOperation,
        minimum_balance_cents: int = 0,
    ) -> tuple[Client, BalanceOperation]:
        async with self._balance_lock:
            existing = self._operations.get(operation.idempotency_key)
            if existing is not None:
                if (
                    existing.client_id != client.id
                    or existing.amount_cents != operation.amount_cents
                    or existing.bonus_amount != operation.bonus_amount
                    or existing.reason != operation.reason
                    or existing.actor_id != operation.actor_id
                    or existing.operation_type != operation.operation_type
                    or existing.payment_parts != operation.payment_parts
                ):
                    raise ValueError("Idempotency key belongs to another balance operation")
                return self._items[existing.client_id], existing
            current = self._items.get(client.id)
            if current is None:
                raise ValueError("Client not found")
            next_balance = current.balance_cents + operation.amount_cents
            if operation.amount_cents < 0 and next_balance < minimum_balance_cents:
                raise ValueError("Insufficient balance")
            bonus_command = None
            if operation.bonus_amount:
                bonus_command = BonusCommand(
                    client.id,
                    BonusOperationKind.ADJUST,
                    operation.bonus_amount * 100,
                    operation.actor_id,
                    operation.reason,
                    f"legacy-top-up:{operation.id}",
                )
            self._record_bonus_balance_movement(current, operation)
            if bonus_command is not None:
                self._apply_bonus_locked(bonus_command, operation.created_at)
            updated = dataclasses.replace(
                current,
                balance_cents=next_balance,
                balance_bonus=self._items[client.id].balance_bonus,
                updated_at=operation.created_at,
            )
            self._items[client.id] = updated
            self._operations[operation.idempotency_key] = operation
            return updated, operation

    async def get_bonus_wallet(self, client_id: uuid.UUID) -> BonusWallet:
        async with self._balance_lock:
            current = self._items.get(client_id)
            if current is None:
                raise ValueError("Client not found")
            return self._bonus_wallets.get(client_id, BonusWallet(current.balance_bonus * 100))

    async def apply_bonus_operation(
        self, command: BonusCommand, now: datetime.datetime
    ) -> BonusOperation:
        async with self._balance_lock:
            return self._apply_bonus_locked(command, now)

    def _apply_bonus_locked(self, command: BonusCommand, now: datetime.datetime) -> BonusOperation:
        existing = self._bonus_operations.get(command.idempotency_key)
        if existing is not None:
            if existing.command != command:
                raise ValueError("Idempotency key belongs to another bonus operation")
            return existing
        client = self._items.get(command.client_id)
        if client is None:
            raise ValueError("Client not found")
        before = self._bonus_wallets.get(client.id, BonusWallet(client.balance_bonus * 100))
        held = self._bonus_reservations.get((client.id, command.session_id), 0)
        after, next_held = command.apply(before, held, client.balance_cents)
        updated_client = dataclasses.replace(
            client, balance_bonus=after.total_cents // 100, updated_at=now
        )
        if client.id not in self._bonus_wallets and before.total_cents:
            opening = BonusCommand(
                client.id,
                BonusOperationKind.ADJUST,
                before.total_cents,
                "bonus-migration",
                "Legacy bonus opening balance",
                f"bonus-opening:{client.id}",
            )
            self._bonus_operations[opening.idempotency_key] = BonusOperation(
                uuid.uuid4(), opening, before, 0, before.total_cents, 0, now
            )
        operation = BonusOperation(
            uuid.uuid4(),
            command,
            after,
            next_held,
            after.total_cents - before.total_cents,
            after.reserved_cents - before.reserved_cents,
            now,
        )
        self._bonus_wallets[client.id] = after
        if command.session_id is not None:
            self._bonus_reservations[(client.id, command.session_id)] = next_held
        self._items[client.id] = updated_client
        self._bonus_operations[command.idempotency_key] = operation
        return operation

    async def list_bonus_operations(
        self, client_id: uuid.UUID, limit: int = 100
    ) -> list[BonusOperation]:
        async with self._balance_lock:
            rows = [
                op for op in self._bonus_operations.values() if op.command.client_id == client_id
            ]
            return sorted(rows, key=lambda op: (op.created_at, op.id), reverse=True)[
                : max(1, min(limit, 100))
            ]

    def _freeze_bonus_session(
        self, client_id: uuid.UUID, session_id: uuid.UUID, policy: BonusPolicy | None = None
    ) -> tuple[uuid.UUID, BonusPolicy, bool]:
        if client_id not in self._items:
            raise ValueError("Client not found")
        previous = self._bonus_sessions.get(session_id)
        if previous is not None and previous[0] != client_id:
            raise ValueError("Bonus session belongs to another client")
        if previous is None:
            previous = (client_id, policy or BonusPolicy(enabled=False), False)
            self._bonus_sessions[session_id] = previous
        return previous

    async def begin_bonus_session(self, client_id: uuid.UUID, session_id: uuid.UUID) -> BonusPolicy:
        async with self._balance_lock:
            return self._freeze_bonus_session(client_id, session_id, self._bonus_policy)[1]

    async def get_bonus_policy(
        self, client_id: uuid.UUID | None = None, session_id: uuid.UUID | None = None
    ) -> BonusPolicy:
        async with self._balance_lock:
            if session_id is None:
                if client_id is not None and client_id not in self._items:
                    raise ValueError("Client not found")
                return self._bonus_policy
            return self._freeze_bonus_session(client_id, session_id)[1]

    async def update_bonus_policy(
        self, policy: BonusPolicy, actor_id: str, idempotency_key: str, now: datetime.datetime
    ) -> BonusPolicy:
        async with self._balance_lock:
            previous = self._bonus_policy_changes.get(idempotency_key)
            if previous is not None:
                if previous != (actor_id, policy):
                    raise ValueError("Idempotency key belongs to another bonus settings change")
                return previous[1]
            self._bonus_policy = policy
            self._bonus_policy_changes[idempotency_key] = (actor_id, policy)
            return policy

    def _release_bonus_earning(
        self, command: BonusEarningCommand, accrual: BonusAccrual, now: datetime.datetime
    ) -> BonusAccrual:
        eligible = command.session_id is None
        if command.session_id is not None:
            gate = self._bonus_sessions.get(command.session_id)
            eligible = gate is not None and gate[2]
        after, delta = accrual.release(session_finished=eligible)
        if delta:
            key = uuid.uuid5(
                uuid.NAMESPACE_URL, f"bonus:{command.source_key}:{after.released_bonus_cents}"
            )
            self._apply_bonus_locked(
                BonusCommand(
                    command.client_id,
                    BonusOperationKind.ADJUST,
                    delta,
                    "bonus-program",
                    f"Начисление бонусов: {command.source_key}",
                    f"bonus-earning:{key}",
                ),
                now,
            )
        return after

    def _record_bonus_balance_movement(self, client: Client, operation: BalanceOperation) -> None:
        if operation.amount_cents < 0:
            amount = -operation.amount_cents
            self._bonus_debits[operation.id] = BonusDebt(
                operation.id,
                client.id,
                amount,
                min(amount, max(client.balance_cents, 0)),
                operation.created_at,
            )
            return
        repayment = min(operation.amount_cents, max(-client.balance_cents, 0))
        if not repayment:
            return
        debts = sorted(
            (
                debt
                for debt in self._bonus_debits.values()
                if debt.client_id == client.id and debt.paid_cents < debt.money_cents
            ),
            key=lambda item: (item.created_at, item.operation_id),
        )
        if sum(debt.money_cents - debt.paid_cents for debt in debts) < repayment:
            raise ValueError("Monetary debt has no matching bonus debt ledger")
        debt_updates = {}
        earning_updates = {}
        for debt in debts:
            paid = min(repayment, debt.money_cents - debt.paid_cents)
            debt_updates[debt.operation_id] = dataclasses.replace(
                debt, paid_cents=debt.paid_cents + paid
            )
            repayment -= paid
            if debt.source_key:
                source, accrual = earning_updates.get(
                    debt.source_key, self._bonus_earnings[debt.source_key]
                )
                earning_updates[debt.source_key] = (source, accrual.repay(paid))
            if not repayment:
                break
        pending_credit = 0
        for source, accrual in earning_updates.values():
            finished = source.session_id is None or self._bonus_sessions[source.session_id][2]
            pending_credit += accrual.release(session_finished=finished)[1]
        wallet = self._bonus_wallets.get(client.id, BonusWallet(client.balance_bonus * 100))
        BonusWallet(
            wallet.total_cents + pending_credit + operation.bonus_amount * 100,
            wallet.reserved_cents,
        )
        for key, (source, accrual) in earning_updates.items():
            self._bonus_earnings[key] = (
                source,
                self._release_bonus_earning(source, accrual, operation.created_at),
            )
        self._bonus_debits.update(debt_updates)

    async def confirm_bonus_earning(
        self, command: BonusEarningCommand, now: datetime.datetime
    ) -> None:
        async with self._balance_lock:
            previous = self._bonus_receipts.get(command.receipt_id)
            if previous is not None:
                if previous != command.payload():
                    raise ValueError("Bonus receipt belongs to another confirmed earning")
                return
            if command.client_id not in self._items:
                raise ValueError("Client not found")
            existing = self._bonus_earnings.get(command.source_key)
            rate = command.policy.rate(command.source)
            if existing:
                original, accrual = existing
                if (
                    original.client_id != command.client_id
                    or original.source != command.source
                    or original.session_id != command.session_id
                    or accrual.rate_bps != rate
                ):
                    raise ValueError("Bonus source policy or identity has changed")
            else:
                original, accrual = command, BonusAccrual(rate)
            debits = []
            for operation_id in command.debit_operation_ids:
                debit = self._bonus_debits.get(operation_id)
                if (
                    debit is None
                    or debit.client_id != command.client_id
                    or debit.receipt_id is not None
                ):
                    raise ValueError("Bonus source does not match its monetary debit")
                debits.append(debit)
            money = command.external_paid_cents + sum(debit.money_cents for debit in debits)
            paid = command.external_paid_cents + sum(debit.paid_cents for debit in debits)
            accrual = accrual.record(money, paid)
            if command.session_id is not None:
                self._freeze_bonus_session(command.client_id, command.session_id)
            accrual = self._release_bonus_earning(command, accrual, now)
            for debit in debits:
                self._bonus_debits[debit.operation_id] = dataclasses.replace(
                    debit, source_key=command.source_key, receipt_id=command.receipt_id
                )
            self._bonus_earnings[command.source_key] = (original, accrual)
            self._bonus_receipts[command.receipt_id] = command.payload()

    async def finish_bonus_session(
        self, client_id: uuid.UUID, session_id: uuid.UUID, now: datetime.datetime
    ) -> None:
        async with self._balance_lock:
            _, policy, _ = self._freeze_bonus_session(client_id, session_id)
            sources = [
                (key, source, accrual)
                for key, (source, accrual) in self._bonus_earnings.items()
                if source.client_id == client_id and source.session_id == session_id
            ]
            credit = sum(accrual.release(session_finished=True)[1] for _, _, accrual in sources)
            wallet = self._bonus_wallets.get(
                client_id, BonusWallet(self._items[client_id].balance_bonus * 100)
            )
            BonusWallet(wallet.total_cents + credit, wallet.reserved_cents)
            self._bonus_sessions[session_id] = (client_id, policy, True)
            for key, source, accrual in sources:
                self._bonus_earnings[key] = (
                    source,
                    self._release_bonus_earning(source, accrual, now),
                )

    async def get_pending_bonus_cents(self, client_id: uuid.UUID) -> int:
        async with self._balance_lock:
            return sum(
                accrual.pending_bonus_cents
                for source, accrual in self._bonus_earnings.values()
                if source.client_id == client_id
            )

    async def get_bonus_payment_state(
        self, client_id: uuid.UUID, session_id: uuid.UUID | None = None
    ) -> BonusPaymentState:
        async with self._balance_lock:
            client = self._items.get(client_id)
            if client is None:
                raise ValueError("Client not found")
            policy = self._bonus_policy
            if session_id is not None:
                policy = self._freeze_bonus_session(client_id, session_id)[1]
            minute_earning = self._bonus_earnings.get(f"minutes:{session_id}")
            return BonusPaymentState(
                client.balance_cents,
                self._bonus_wallets.get(client_id, BonusWallet(client.balance_bonus * 100)),
                policy,
                self._bonus_policy.enabled,
                self._bonus_reservations.get((client_id, session_id), 0),
                minute_earning[1].money_cents if minute_earning is not None else 0,
            )
