import dataclasses
import datetime
import uuid

from sqlalchemy import BigInteger, DateTime, Numeric, Select, String, cast, func, select, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from gameclub_backend.infrastructure.database import EngineProvider, begin_session, open_session
from gameclub_backend.modules.clients.application.bonus import (
    BonusCommand,
    BonusEarningCommand,
    BonusOperation,
    BonusPaymentState,
)
from gameclub_backend.modules.clients.application.bonus_reporting import (
    BonusPeriodTotals,
    BonusReport,
)
from gameclub_backend.modules.clients.bonus import BonusOperationKind, BonusPolicy, BonusWallet
from gameclub_backend.modules.clients.domain import (
    BalanceOperation,
    BalanceOperationType,
    Client,
    Guest,
)
from gameclub_backend.modules.clients.infrastructure.bonus_postgres import (
    BonusDebitModel,
    BonusEarningModel,
    BonusOperationModel,
    BonusProgramChangeModel,
    BonusProgramModel,
    BonusReservationModel,
    BonusWalletModel,
    apply_bonus_locked,
    confirm_bonus_earning,
    freeze_bonus_session,
    read_bonus_policy,
    record_bonus_balance_movement,
    release_bonus_earning,
)
from gameclub_backend.modules.payment_methods.domain import PaymentPart


def _pending_bonus_statement(client_id: uuid.UUID | None = None) -> Select:
    statement = select(
        func.coalesce(
            func.sum(
                func.floor(
                    cast(BonusEarningModel.money_cents, Numeric)
                    * BonusEarningModel.rate_bps
                    / 10000
                )
                - BonusEarningModel.released_bonus_cents,
            ),
            0,
        )
    )
    return (
        statement.where(BonusEarningModel.client_id == client_id)
        if client_id is not None
        else statement
    )


class ClientBase(DeclarativeBase):
    pass


class ClientModel(ClientBase):
    __tablename__ = "clients"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    nickname: Mapped[str] = mapped_column(String(64), index=True)
    phone: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    discount_category: Mapped[str | None] = mapped_column(String(64), nullable=True)
    balance_cents: Mapped[int] = mapped_column(default=0)
    balance_bonus: Mapped[int] = mapped_column(BigInteger, default=0)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True))
    blocked_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    password_reset_required: Mapped[bool] = mapped_column(default=False, server_default="false")
    password_reset_login_used: Mapped[bool] = mapped_column(default=False, server_default="false")
    client_group_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)

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
            password_reset_required=self.password_reset_required,
            password_reset_login_used=self.password_reset_login_used,
            client_group_id=self.client_group_id,
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
            password_reset_required=client.password_reset_required,
            password_reset_login_used=client.password_reset_login_used,
            client_group_id=client.client_group_id,
        )


class BalanceOperationModel(ClientBase):
    __tablename__ = "balance_operations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    client_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    amount_cents: Mapped[int] = mapped_column()
    bonus_amount: Mapped[int] = mapped_column(BigInteger)
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
    async def read_bonus_report(
        self, start_at: datetime.datetime, end_at: datetime.datetime
    ) -> BonusReport:
        engine = self._engine_provider()
        if engine is None:
            raise RuntimeError("PostgreSQL engine is not configured")
        async with engine.connect() as connection:
            connection = await connection.execution_options(isolation_level="REPEATABLE READ")
            async with connection.begin():
                await connection.exec_driver_sql("SET TRANSACTION READ ONLY")
                observed_at = await connection.scalar(select(func.transaction_timestamp()))
                totals = BonusPeriodTotals()
                rows = await connection.stream(
                    select(
                        BonusOperationModel.kind,
                        BonusOperationModel.idempotency_key,
                        BonusOperationModel.total_delta_cents,
                        BonusOperationModel.reserved_delta_cents,
                    ).where(
                        BonusOperationModel.created_at >= start_at,
                        BonusOperationModel.created_at < end_at,
                    )
                )
                async for row in rows:
                    totals = totals.record(
                        BonusOperationKind(row.kind),
                        row.idempotency_key,
                        row.total_delta_cents,
                        row.reserved_delta_cents,
                    )
                total, reserved = (
                    await connection.execute(
                        select(
                            func.coalesce(
                                func.sum(
                                    func.coalesce(
                                        BonusWalletModel.total_cents,
                                        cast(ClientModel.balance_bonus, Numeric) * 100,
                                        0,
                                    )
                                ),
                                0,
                            ),
                            func.coalesce(func.sum(BonusWalletModel.reserved_cents), 0),
                        ).select_from(
                            ClientModel.__table__.join(
                                BonusWalletModel.__table__,
                                ClientModel.id == BonusWalletModel.client_id,
                                full=True,
                            )
                        )
                    )
                ).one()
                pending = await connection.scalar(_pending_bonus_statement())
                return BonusReport(
                    start_at,
                    end_at,
                    observed_at,
                    totals,
                    int(total),
                    int(total - reserved),
                    int(reserved),
                    int(pending),
                )

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
                model = ClientModel.from_domain(client)
                session.add(model)
                if client.balance_cents < 0:
                    session.add(
                        BonusDebitModel(
                            operation_id=client.id,
                            client_id=client.id,
                            money_cents=-client.balance_cents,
                            paid_cents=0,
                            source_key=None,
                            receipt_id=None,
                            created_at=client.created_at,
                        )
                    )
            else:
                for key, value in ClientModel.from_domain(client).__dict__.items():
                    if not key.startswith("_") and key not in (
                        "balance_cents",
                        "balance_bonus",
                        "created_at",
                    ):
                        setattr(model, key, value)
            try:
                await session.commit()
            except IntegrityError as error:
                await session.rollback()
                raise ValueError("Client nickname or phone is already registered") from error
            return model.to_domain()

    async def consume_password_reset_login(
        self,
        client_id: uuid.UUID,
        now: datetime.datetime,
    ) -> Client:
        async with open_session(self._engine_provider) as session:
            async with session.begin():
                model = await session.scalar(
                    select(ClientModel).where(ClientModel.id == client_id).with_for_update()
                )
                if model is None:
                    raise ValueError("Client not found")
                if not model.password_reset_required or model.password_reset_login_used:
                    raise ValueError("Passwordless reset login already used")
                model.password_reset_login_used = True
                model.updated_at = now
                return model.to_domain()

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
        minimum_balance_cents: int = 0,
    ) -> tuple[Client, BalanceOperation]:
        async with open_session(self._engine_provider) as session:
            async with begin_session(session):
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
                    existing = existing_model.to_domain()
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
                    return client_model.to_domain(), existing

                next_balance = client_model.balance_cents + operation.amount_cents
                if operation.amount_cents < 0 and next_balance < minimum_balance_cents:
                    raise ValueError("Insufficient balance")
                previous_balance = client_model.balance_cents
                client_model.balance_cents = next_balance
                await record_bonus_balance_movement(
                    session, client_model, operation, previous_balance
                )
                if operation.bonus_amount:
                    command = BonusCommand(
                        client.id,
                        BonusOperationKind.ADJUST,
                        operation.bonus_amount * 100,
                        operation.actor_id,
                        operation.reason,
                        f"legacy-top-up:{operation.id}",
                    )
                    await apply_bonus_locked(session, client_model, command, operation.created_at)
                client_model.updated_at = operation.created_at
                session.add(BalanceOperationModel.from_domain(operation))
                updated = client_model.to_domain()
                return updated, operation

    async def get_bonus_wallet(self, client_id: uuid.UUID) -> BonusWallet:
        async with open_session(self._engine_provider) as session:
            client = await session.get(ClientModel, client_id)
            if client is None:
                raise ValueError("Client not found")
            wallet = await session.get(BonusWalletModel, client_id)
            return wallet.to_domain() if wallet else BonusWallet(client.balance_bonus * 100)

    async def apply_bonus_operation(
        self, command: BonusCommand, now: datetime.datetime
    ) -> BonusOperation:
        async with open_session(self._engine_provider) as session:
            async with begin_session(session):
                client = await session.scalar(
                    select(ClientModel).where(ClientModel.id == command.client_id).with_for_update()
                )
                if client is None:
                    raise ValueError("Client not found")
                return await apply_bonus_locked(session, client, command, now)

    async def list_bonus_operations(
        self, client_id: uuid.UUID, limit: int = 100
    ) -> list[BonusOperation]:
        async with open_session(self._engine_provider) as session:
            rows = await session.scalars(
                select(BonusOperationModel)
                .where(BonusOperationModel.client_id == client_id)
                .order_by(BonusOperationModel.created_at.desc(), BonusOperationModel.id.desc())
                .limit(max(1, min(limit, 100)))
            )
            return [row.to_domain() for row in rows]

    async def begin_bonus_session(self, client_id: uuid.UUID, session_id: uuid.UUID) -> BonusPolicy:
        async with open_session(self._engine_provider) as session:
            async with begin_session(session):
                client = await session.get(ClientModel, client_id, with_for_update=True)
                if client is None:
                    raise ValueError("Client not found")
                frozen = await freeze_bonus_session(
                    session, client_id, session_id, policy=await read_bonus_policy(session)
                )
                return BonusPolicy(**frozen.policy)

    async def get_bonus_policy(
        self, client_id: uuid.UUID | None = None, session_id: uuid.UUID | None = None
    ) -> BonusPolicy:
        async with open_session(self._engine_provider) as session:
            if session_id is None:
                if client_id is not None and await session.get(ClientModel, client_id) is None:
                    raise ValueError("Client not found")
                return await read_bonus_policy(session)
            async with begin_session(session):
                client = await session.scalar(
                    select(ClientModel).where(ClientModel.id == client_id).with_for_update()
                )
                if client is None:
                    raise ValueError("Client not found")
                frozen = await freeze_bonus_session(session, client.id, session_id)
                return BonusPolicy(**frozen.policy)

    async def update_bonus_policy(
        self, policy: BonusPolicy, actor_id: str, idempotency_key: str, now: datetime.datetime
    ) -> BonusPolicy:
        async with open_session(self._engine_provider) as session:
            async with begin_session(session):
                current = await session.get(BonusProgramModel, 1, with_for_update=True)
                previous = await session.get(BonusProgramChangeModel, idempotency_key)
                data = dataclasses.asdict(policy)
                if previous is not None:
                    if previous.actor_id != actor_id or previous.policy != data:
                        raise ValueError("Idempotency key belongs to another bonus settings change")
                    return BonusPolicy(**previous.policy)
                if current is None:
                    current = BonusProgramModel(id=1, policy=data)
                    session.add(current)
                else:
                    current.policy = data
                session.add(
                    BonusProgramChangeModel(
                        idempotency_key=idempotency_key,
                        policy=data,
                        actor_id=actor_id,
                        created_at=now,
                    )
                )
                return policy

    async def confirm_bonus_earning(
        self, command: BonusEarningCommand, now: datetime.datetime
    ) -> None:
        async with open_session(self._engine_provider) as session:
            async with begin_session(session):
                client = await session.scalar(
                    select(ClientModel).where(ClientModel.id == command.client_id).with_for_update()
                )
                if client is None:
                    raise ValueError("Client not found")
                await confirm_bonus_earning(session, client, command, now)

    async def finish_bonus_session(
        self, client_id: uuid.UUID, session_id: uuid.UUID, now: datetime.datetime
    ) -> None:
        async with open_session(self._engine_provider) as session:
            async with begin_session(session):
                client = await session.scalar(
                    select(ClientModel).where(ClientModel.id == client_id).with_for_update()
                )
                if client is None:
                    raise ValueError("Client not found")
                gate = await freeze_bonus_session(session, client_id, session_id)
                gate.finished = True
                earnings = (
                    await session.scalars(
                        select(BonusEarningModel).where(
                            BonusEarningModel.client_id == client_id,
                            BonusEarningModel.session_id == session_id,
                        )
                    )
                ).all()
                for earning in earnings:
                    await release_bonus_earning(session, client, earning, now)

    async def get_pending_bonus_cents(self, client_id: uuid.UUID) -> int:
        async with open_session(self._engine_provider) as session:
            amount = await session.scalar(_pending_bonus_statement(client_id))
            return int(amount)

    async def get_bonus_payment_state(
        self, client_id: uuid.UUID, session_id: uuid.UUID | None = None
    ) -> BonusPaymentState:
        async with open_session(self._engine_provider) as session:
            async with begin_session(session):
                client = await session.get(
                    ClientModel, client_id, with_for_update=True, populate_existing=True
                )
                if client is None:
                    raise ValueError("Client not found")
                current_policy = await read_bonus_policy(session)
                policy = current_policy
                if session_id is not None:
                    frozen = await freeze_bonus_session(session, client_id, session_id)
                    policy = BonusPolicy(**frozen.policy)
                wallet = await session.get(BonusWalletModel, client_id, populate_existing=True)
                held = (
                    await session.get(BonusReservationModel, (client_id, session_id))
                    if session_id is not None
                    else None
                )
                minute_earning = (
                    await session.get(BonusEarningModel, f"minutes:{session_id}")
                    if session_id is not None
                    else None
                )
                return BonusPaymentState(
                    client.balance_cents,
                    wallet.to_domain() if wallet else BonusWallet(client.balance_bonus * 100),
                    policy,
                    current_policy.enabled,
                    held.remaining_cents if held is not None else 0,
                    minute_earning.money_cents if minute_earning is not None else 0,
                )


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
