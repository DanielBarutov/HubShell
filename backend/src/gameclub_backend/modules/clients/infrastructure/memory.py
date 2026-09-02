import asyncio
import dataclasses
import uuid

from gameclub_backend.modules.clients.domain import BalanceOperation, Client


class InMemoryClientRepository:
    def __init__(self) -> None:
        self._items: dict[uuid.UUID, Client] = {}
        self._operations: dict[str, BalanceOperation] = {}
        self._balance_lock = asyncio.Lock()

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
        self._items[client.id] = client
        return client

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
    ) -> tuple[Client, BalanceOperation]:
        async with self._balance_lock:
            existing = self._operations.get(operation.idempotency_key)
            if existing is not None:
                return self._items[existing.client_id], existing
            current = self._items.get(client.id)
            if current is None:
                raise ValueError("Client not found")
            next_balance = current.balance_cents + operation.amount_cents
            if next_balance < 0:
                raise ValueError("Insufficient balance")
            updated = dataclasses.replace(
                current,
                balance_cents=next_balance,
                balance_bonus=current.balance_bonus + operation.bonus_amount,
                updated_at=operation.created_at,
            )
            self._items[client.id] = updated
            self._operations[operation.idempotency_key] = operation
            return updated, operation
