import datetime
import uuid

from sqlalchemy import Boolean, DateTime, Integer, String, select
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from gameclub_backend.infrastructure.database import EngineProvider, open_session
from gameclub_backend.modules.payment_methods.domain import PaymentMethod


class PaymentMethodBase(DeclarativeBase):
    pass


class PaymentMethodModel(PaymentMethodBase):
    __tablename__ = "payment_methods"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    key: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(128))
    active: Mapped[bool] = mapped_column(Boolean(), default=True)
    sort_order: Mapped[int] = mapped_column(Integer(), default=0)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True))

    def to_domain(self) -> PaymentMethod:
        return PaymentMethod(
            id=self.id,
            key=self.key,
            name=self.name,
            active=self.active,
            sort_order=self.sort_order,
            created_at=self.created_at,
            updated_at=self.updated_at,
        )

    @classmethod
    def from_domain(cls, method: PaymentMethod) -> "PaymentMethodModel":
        return cls(
            id=method.id,
            key=method.key,
            name=method.name,
            active=method.active,
            sort_order=method.sort_order,
            created_at=method.created_at,
            updated_at=method.updated_at,
        )


class PostgresPaymentMethodRepository:
    def __init__(self, engine_provider: EngineProvider) -> None:
        self._engine_provider = engine_provider

    async def get(self, method_id: uuid.UUID) -> PaymentMethod | None:
        async with open_session(self._engine_provider) as session:
            model = await session.get(PaymentMethodModel, method_id)
            return model.to_domain() if model else None

    async def get_by_key(self, key: str) -> PaymentMethod | None:
        async with open_session(self._engine_provider) as session:
            model = await session.scalar(
                select(PaymentMethodModel).where(PaymentMethodModel.key == key)
            )
            return model.to_domain() if model else None

    async def list(self) -> list[PaymentMethod]:
        async with open_session(self._engine_provider) as session:
            result = await session.scalars(
                select(PaymentMethodModel).order_by(
                    PaymentMethodModel.sort_order,
                    PaymentMethodModel.name,
                )
            )
            return [model.to_domain() for model in result]

    async def save(self, method: PaymentMethod) -> PaymentMethod:
        async with open_session(self._engine_provider) as session:
            model = await session.get(PaymentMethodModel, method.id)
            if model is None:
                session.add(PaymentMethodModel.from_domain(method))
            else:
                model.key = method.key
                model.name = method.name
                model.active = method.active
                model.sort_order = method.sort_order
                model.updated_at = method.updated_at
            await session.commit()
            return method

    async def delete(self, method_id: uuid.UUID) -> None:
        async with open_session(self._engine_provider) as session:
            model = await session.get(PaymentMethodModel, method_id)
            if model is not None:
                await session.delete(model)
                await session.commit()
