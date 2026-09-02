import dataclasses
import datetime
import uuid

from sqlalchemy import DateTime, Integer, String, select, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from gameclub_backend.infrastructure.database import EngineProvider, open_session
from gameclub_backend.modules.entitlements.domain import Entitlement, EntitlementStatus


class EntitlementBase(DeclarativeBase):
    pass


class EntitlementModel(EntitlementBase):
    __tablename__ = "client_entitlements"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    client_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    tariff_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    zone_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    duration_minutes: Mapped[int] = mapped_column(Integer())
    remaining_minutes: Mapped[int] = mapped_column(Integer())
    price_cents: Mapped[int] = mapped_column(Integer())
    queue_position: Mapped[int] = mapped_column(Integer())
    status: Mapped[str] = mapped_column(String(16), index=True)
    idempotency_key: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    purchased_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True))
    activated_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    ended_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    burn_reason: Mapped[str | None] = mapped_column(String(256), nullable=True)
    window_start_minute: Mapped[int | None] = mapped_column(Integer(), nullable=True)
    window_end_minute: Mapped[int | None] = mapped_column(Integer(), nullable=True)
    window_timezone: Mapped[str | None] = mapped_column(String(64), nullable=True)

    def to_domain(self) -> Entitlement:
        return Entitlement(
            id=self.id,
            client_id=self.client_id,
            tariff_id=self.tariff_id,
            zone_id=self.zone_id,
            duration_minutes=self.duration_minutes,
            remaining_minutes=self.remaining_minutes,
            price_cents=self.price_cents,
            queue_position=self.queue_position,
            status=EntitlementStatus(self.status),
            idempotency_key=self.idempotency_key,
            purchased_at=self.purchased_at,
            activated_at=self.activated_at,
            ended_at=self.ended_at,
            burn_reason=self.burn_reason,
            window_start_minute=self.window_start_minute,
            window_end_minute=self.window_end_minute,
            window_timezone=self.window_timezone,
        )

    @classmethod
    def from_domain(cls, item: Entitlement) -> "EntitlementModel":
        return cls(
            id=item.id,
            client_id=item.client_id,
            tariff_id=item.tariff_id,
            zone_id=item.zone_id,
            duration_minutes=item.duration_minutes,
            remaining_minutes=item.remaining_minutes,
            price_cents=item.price_cents,
            queue_position=item.queue_position,
            status=item.status.value,
            idempotency_key=item.idempotency_key,
            purchased_at=item.purchased_at,
            activated_at=item.activated_at,
            ended_at=item.ended_at,
            burn_reason=item.burn_reason,
            window_start_minute=item.window_start_minute,
            window_end_minute=item.window_end_minute,
            window_timezone=item.window_timezone,
        )


class PostgresEntitlementRepository:
    def __init__(self, engine_provider: EngineProvider) -> None:
        self._engine_provider = engine_provider

    async def get(self, entitlement_id: uuid.UUID) -> Entitlement | None:
        async with open_session(self._engine_provider) as session:
            model = await session.get(EntitlementModel, entitlement_id)
            return model.to_domain() if model else None

    async def get_by_idempotency_key(self, key: str) -> Entitlement | None:
        async with open_session(self._engine_provider) as session:
            model = await session.scalar(
                select(EntitlementModel).where(EntitlementModel.idempotency_key == key)
            )
            return model.to_domain() if model else None

    async def list_for_client(self, client_id: uuid.UUID) -> list[Entitlement]:
        async with open_session(self._engine_provider) as session:
            result = await session.scalars(
                select(EntitlementModel)
                .where(EntitlementModel.client_id == client_id)
                .order_by(EntitlementModel.queue_position)
            )
            return [model.to_domain() for model in result]

    async def get_active_for_client(self, client_id: uuid.UUID) -> Entitlement | None:
        async with open_session(self._engine_provider) as session:
            model = await session.scalar(
                select(EntitlementModel).where(
                    EntitlementModel.client_id == client_id,
                    EntitlementModel.status == EntitlementStatus.ACTIVE.value,
                )
            )
            return model.to_domain() if model else None

    async def create(self, item: Entitlement) -> Entitlement:
        async with open_session(self._engine_provider) as session:
            async with session.begin():
                await session.execute(
                    text("SELECT pg_advisory_xact_lock(hashtext(:lock_key))"),
                    {"lock_key": f"entitlement-client:{item.client_id}"},
                )
                existing = await session.scalar(
                    select(EntitlementModel).where(
                        EntitlementModel.idempotency_key == item.idempotency_key
                    )
                )
                if existing is not None:
                    return existing.to_domain()
                latest = await session.scalar(
                    select(EntitlementModel.queue_position)
                    .where(EntitlementModel.client_id == item.client_id)
                    .order_by(EntitlementModel.queue_position.desc())
                    .limit(1)
                )
                if latest is not None:
                    item = dataclasses.replace(item, queue_position=latest + 1)
                session.add(EntitlementModel.from_domain(item))
                return item

    async def save(self, item: Entitlement) -> Entitlement:
        async with open_session(self._engine_provider) as session:
            async with session.begin():
                model = await session.scalar(
                    select(EntitlementModel).where(EntitlementModel.id == item.id).with_for_update()
                )
                if model is None:
                    raise ValueError("Entitlement not found")
                if item.status is EntitlementStatus.ACTIVE:
                    active = await session.scalar(
                        select(EntitlementModel).where(
                            EntitlementModel.client_id == item.client_id,
                            EntitlementModel.status == EntitlementStatus.ACTIVE.value,
                            EntitlementModel.id != item.id,
                        )
                    )
                    if active is not None:
                        raise ValueError("Client already has an active package")
                for key, value in EntitlementModel.from_domain(item).__dict__.items():
                    if not key.startswith("_"):
                        setattr(model, key, value)
                return model.to_domain()

    async def next_compatible(
        self,
        client_id: uuid.UUID,
        zone_id: str | None,
        statuses: tuple[EntitlementStatus, ...] = (EntitlementStatus.QUEUED,),
        now: datetime.datetime | None = None,
    ) -> Entitlement | None:
        items = await self.list_for_client(client_id)
        moment = now or datetime.datetime.now(datetime.UTC)
        return next(
            (
                item
                for item in items
                if item.status in statuses
                and item.is_compatible(zone_id)
                and item.is_available_at(moment)
            ),
            None,
        )

    async def activate_for_client(
        self,
        entitlement_id: uuid.UUID,
        client_id: uuid.UUID,
        now: datetime.datetime,
        zone_id: str | None = None,
    ) -> Entitlement:
        async with open_session(self._engine_provider) as session:
            async with session.begin():
                model = await session.scalar(
                    select(EntitlementModel)
                    .where(
                        EntitlementModel.id == entitlement_id,
                        EntitlementModel.client_id == client_id,
                    )
                    .with_for_update()
                )
                if model is None:
                    raise ValueError("Entitlement not found")
                item = model.to_domain()
                if zone_id is not None and not item.is_compatible(zone_id):
                    raise ValueError("Package is incompatible with this workstation zone")
                if not item.is_available_at(now):
                    raise ValueError("Package is outside its time window")
                active = await session.scalar(
                    select(EntitlementModel).where(
                        EntitlementModel.client_id == client_id,
                        EntitlementModel.status == EntitlementStatus.ACTIVE.value,
                        EntitlementModel.id != entitlement_id,
                    )
                )
                if active is not None:
                    raise ValueError("Client already has an active package")
                updated = item.activate(now)
                model.status = updated.status.value
                model.activated_at = updated.activated_at
                return updated

    async def consume_for_client(
        self,
        entitlement_id: uuid.UUID,
        client_id: uuid.UUID,
        minutes: int,
        now: datetime.datetime,
    ) -> Entitlement:
        async with open_session(self._engine_provider) as session:
            async with session.begin():
                model = await session.scalar(
                    select(EntitlementModel)
                    .where(
                        EntitlementModel.id == entitlement_id,
                        EntitlementModel.client_id == client_id,
                    )
                    .with_for_update()
                )
                if model is None:
                    raise ValueError("Entitlement not found")
                item = model.to_domain()
                if not item.is_available_at(now):
                    raise ValueError("Package is outside its time window")
                updated = item.consume(minutes, now)
                model.remaining_minutes = updated.remaining_minutes
                model.status = updated.status.value
                model.ended_at = updated.ended_at
                return updated

    async def burn_for_client(
        self,
        entitlement_id: uuid.UUID,
        client_id: uuid.UUID,
        reason: str,
        now: datetime.datetime,
    ) -> Entitlement:
        async with open_session(self._engine_provider) as session:
            async with session.begin():
                model = await session.scalar(
                    select(EntitlementModel)
                    .where(
                        EntitlementModel.id == entitlement_id,
                        EntitlementModel.client_id == client_id,
                    )
                    .with_for_update()
                )
                if model is None:
                    raise ValueError("Entitlement not found")
                updated = model.to_domain().burn(reason, now)
                model.status = updated.status.value
                model.ended_at = updated.ended_at
                model.burn_reason = updated.burn_reason
                return updated
