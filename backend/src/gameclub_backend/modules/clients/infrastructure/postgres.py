import datetime
import uuid

from sqlalchemy import DateTime, String, func, select, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from gameclub_backend.infrastructure.database import EngineProvider, open_session
from gameclub_backend.modules.clients.domain import (
    BalanceOperation,
    BalanceOperationType,
    Client,
    Guest,
)
from gameclub_backend.modules.payment_methods.domain import PaymentPart


class ClientBase(DeclarativeBase):
    pass


class ClientModel(ClientBase):
    __tablename__ = "clients"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    nickname: Mapped[str] = mapped_column(String(64), index=True)
    phone: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    discount_category: Mapped[str | None] = mapped_column(String(64), nullable=True)
    balance_cents: Mapped[int] = mapped_column(default=0)
    balance_bonus: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True))
    blocked_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)

    def to_domain(self) -> Client:
        return Client(
            id=self.id,
            nickname=self.nickname,
            phone=self.phone,
            discount_category=self.discount_category,
            balance_cents=self.balance_cents,
            balance_bonus=self.balance_bonus,
            created_at=self.created_at,
            updated_at=self.updated_at,
            blocked_at=self.blocked_at,
            password_hash=self.password_hash,
        )

    @classmethod
    def from_domain(cls, client: Client) -> "ClientModel":
        return cls(
            id=client.id,
            nickname=client.nickname,
            phone=client.phone,
            discount_category=client.discount_category,
            balance_cents=client.balance_cents,
            balance_bonus=client.balance_bonus,
            created_at=client.created_at,
            updated_at=client.updated_at,
            blocked_at=client.blocked_at,
            password_hash=client.password_hash,
        )


class BalanceOperationModel(ClientBase):
    __tablename__ = "balance_operations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    client_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    amount_cents: Mapped[int] = mapped_column()
    bonus_amount: Mapped[int] = mapped_column()
    reason: Mapped[str] = mapped_column(String(255))
    actor_id: Mapped[str] = mapped_column(String(128))
    idempotency_key: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True))
    operation_type: Mapped[str] = mapped_column(
        String(32), default=BalanceOperationType.TOP_UP.value
    )
    payment_parts: Mapped[list[dict[str, object]]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )

    def to_domain(self) -> BalanceOperation:
        return BalanceOperation(
            id=self.id,
            client_id=self.client_id,
            amount_cents=self.amount_cents,
            bonus_amount=self.bonus_amount,
            reason=self.reason,
            actor_id=self.actor_id,
            idempotency_key=self.idempotency_key,
            created_at=self.created_at,
            operation_type=BalanceOperationType(self.operation_type),
            payment_parts=tuple(PaymentPart.from_dict(part) for part in (self.payment_parts or [])),
        )

    @classmethod
    def from_domain(cls, operation: BalanceOperation) -> "BalanceOperationModel":
        return cls(
            id=operation.id,
            client_id=operation.client_id,
            amount_cents=operation.amount_cents,
            bonus_amount=operation.bonus_amount,
            reason=operation.reason,
            actor_id=operation.actor_id,
            idempotency_key=operation.idempotency_key,
            created_at=operation.created_at,
            operation_type=operation.operation_type.value,
            payment_parts=[part.as_dict() for part in operation.payment_parts],
        )


class GuestModel(ClientBase):
    __tablename__ = "guests"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    nickname: Mapped[str] = mapped_column(String(64), index=True)
    phone: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    discount_category: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True))

    def to_domain(self) -> Guest:
        return Guest(
            id=self.id,
            nickname=self.nickname,
            phone=self.phone,
            discount_category=self.discount_category,
            created_at=self.created_at,
            updated_at=self.updated_at,
        )

    @classmethod
    def from_domain(cls, guest: Guest) -> "GuestModel":
        return cls(
            id=guest.id,
            nickname=guest.nickname,
            phone=guest.phone,
            discount_category=guest.discount_category,
            created_at=guest.created_at,
            updated_at=guest.updated_at,
        )


class PostgresClientRepository:
    def __init__(self, engine_provider: EngineProvider) -> None:
        self._engine_provider = engine_provider

    async def get(self, client_id: uuid.UUID) -> Client | None:
        async with open_session(self._engine_provider) as session:
            model = await session.get(ClientModel, client_id)
            return model.to_domain() if model else None

    async def get_by_nickname(self, nickname: str) -> Client | None:
        async with open_session(self._engine_provider) as session:
            model = await session.scalar(
                select(ClientModel).where(
                    func.lower(ClientModel.nickname) == nickname.strip().lower()
                )
            )
            return model.to_domain() if model else None

    async def get_by_phone(self, phone: str) -> Client | None:
        async with open_session(self._engine_provider) as session:
            model = await session.scalar(select(ClientModel).where(ClientModel.phone == phone))
            return model.to_domain() if model else None

    async def list_clients(self) -> list[Client]:
        async with open_session(self._engine_provider) as session:
            result = await session.scalars(
                select(ClientModel)
                .where(ClientModel.blocked_at.is_(None))
                .order_by(ClientModel.nickname)
            )
            return [model.to_domain() for model in result]

    async def search(self, query: str, field: str) -> list[Client]:
        async with open_session(self._engine_provider) as session:
            column = ClientModel.nickname if field == "nickname" else ClientModel.phone
            result = await session.scalars(
                select(ClientModel)
                .where(ClientModel.blocked_at.is_(None), column.ilike(f"%{query}%"))
                .order_by(ClientModel.nickname)
            )
            return [model.to_domain() for model in result]

    async def save(self, client: Client) -> Client:
        async with open_session(self._engine_provider) as session:
            model = await session.get(ClientModel, client.id)
            if model is None:
                session.add(ClientModel.from_domain(client))
            else:
                for key, value in ClientModel.from_domain(client).__dict__.items():
                    if not key.startswith("_"):
                        setattr(model, key, value)
            await session.commit()
            return client

    async def delete(self, client_id: uuid.UUID) -> None:
        async with open_session(self._engine_provider) as session:
            model = await session.get(ClientModel, client_id)
            if model is not None:
                await session.delete(model)
                await session.commit()

    async def add_operation(self, operation: BalanceOperation) -> BalanceOperation:
        async with open_session(self._engine_provider) as session:
            session.add(BalanceOperationModel.from_domain(operation))
            await session.commit()
            return operation

    async def get_operation_by_key(self, idempotency_key: str) -> BalanceOperation | None:
        async with open_session(self._engine_provider) as session:
            model = await session.scalar(
                select(BalanceOperationModel).where(
                    BalanceOperationModel.idempotency_key == idempotency_key
                )
            )
            return model.to_domain() if model else None

    async def list_operations(
        self,
        client_id: uuid.UUID,
        limit: int,
    ) -> list[BalanceOperation]:
        bounded_limit = max(1, min(limit, 100))
        async with open_session(self._engine_provider) as session:
            result = await session.scalars(
                select(BalanceOperationModel)
                .where(BalanceOperationModel.client_id == client_id)
                .order_by(BalanceOperationModel.created_at.desc())
                .limit(bounded_limit)
            )
            return [model.to_domain() for model in result]

    async def apply_balance_operation(
        self,
        client: Client,
        operation: BalanceOperation,
    ) -> tuple[Client, BalanceOperation]:
        async with open_session(self._engine_provider) as session:
            async with session.begin():
                await session.execute(
                    text("SELECT pg_advisory_xact_lock(hashtext(:idempotency_key))"),
                    {"idempotency_key": operation.idempotency_key},
                )
                client_model = await session.scalar(
                    select(ClientModel).where(ClientModel.id == client.id).with_for_update()
                )
                if client_model is None:
                    raise ValueError("Client not found")
                existing_model = await session.scalar(
                    select(BalanceOperationModel).where(
                        BalanceOperationModel.idempotency_key == operation.idempotency_key
                    )
                )
                if existing_model is not None:
                    if existing_model.client_id != client.id:
                        raise ValueError("Idempotency key belongs to another client")
                    return client_model.to_domain(), existing_model.to_domain()

                next_balance = client_model.balance_cents + operation.amount_cents
                if next_balance < 0:
                    raise ValueError("Insufficient balance")
                client_model.balance_cents = next_balance
                client_model.balance_bonus += operation.bonus_amount
                client_model.updated_at = operation.created_at
                session.add(BalanceOperationModel.from_domain(operation))
                updated = client_model.to_domain()
                return updated, operation


class PostgresGuestRepository:
    def __init__(self, engine_provider: EngineProvider) -> None:
        self._engine_provider = engine_provider

    async def get(self, guest_id: uuid.UUID) -> Guest | None:
        async with open_session(self._engine_provider) as session:
            model = await session.get(GuestModel, guest_id)
            return model.to_domain() if model else None

    async def list_guests(self) -> list[Guest]:
        async with open_session(self._engine_provider) as session:
            result = await session.scalars(select(GuestModel).order_by(GuestModel.nickname))
            return [model.to_domain() for model in result]

    async def search(self, query: str, field: str) -> list[Guest]:
        async with open_session(self._engine_provider) as session:
            column = GuestModel.nickname if field == "nickname" else GuestModel.phone
            result = await session.scalars(
                select(GuestModel).where(column.ilike(f"%{query}%")).order_by(GuestModel.nickname)
            )
            return [model.to_domain() for model in result]

    async def save(self, guest: Guest) -> Guest:
        async with open_session(self._engine_provider) as session:
            model = await session.get(GuestModel, guest.id)
            if model is None:
                session.add(GuestModel.from_domain(guest))
            else:
                for key, value in GuestModel.from_domain(guest).__dict__.items():
                    if not key.startswith("_"):
                        setattr(model, key, value)
            await session.commit()
            return guest
