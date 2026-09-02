import datetime
import uuid

from sqlalchemy import DateTime, Integer, String, select
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from gameclub_backend.infrastructure.database import EngineProvider, open_session
from gameclub_backend.modules.direct_payments.domain import (
    DirectPaymentStatus,
    GuestSessionPayment,
)
from gameclub_backend.modules.payment_methods.domain import PaymentPart


class DirectPaymentBase(DeclarativeBase):
    pass


class GuestSessionPaymentModel(DirectPaymentBase):
    __tablename__ = "guest_session_payments"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    workstation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    tariff_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    tariff_quantity: Mapped[int] = mapped_column(Integer())
    guest_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True, index=True
    )
    guest_name: Mapped[str] = mapped_column(String(128))
    total_price_cents: Mapped[int] = mapped_column(Integer())
    payment_parts: Mapped[list[dict[str, object]]] = mapped_column(JSONB)
    cash_shift_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    status: Mapped[str] = mapped_column(String(16))
    idempotency_key: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True))

    def to_domain(self) -> GuestSessionPayment:
        return GuestSessionPayment(
            id=self.id,
            workstation_id=self.workstation_id,
            tariff_id=self.tariff_id,
            tariff_quantity=self.tariff_quantity,
            guest_id=self.guest_id,
            guest_name=self.guest_name,
            total_price_cents=self.total_price_cents,
            payment_parts=tuple(PaymentPart.from_dict(item) for item in self.payment_parts),
            cash_shift_id=self.cash_shift_id,
            status=DirectPaymentStatus(self.status),
            idempotency_key=self.idempotency_key,
            created_at=self.created_at,
        )

    @classmethod
    def from_domain(cls, payment: GuestSessionPayment) -> "GuestSessionPaymentModel":
        return cls(
            id=payment.id,
            workstation_id=payment.workstation_id,
            tariff_id=payment.tariff_id,
            tariff_quantity=payment.tariff_quantity,
            guest_id=payment.guest_id,
            guest_name=payment.guest_name,
            total_price_cents=payment.total_price_cents,
            payment_parts=[part.as_dict() for part in payment.payment_parts],
            cash_shift_id=payment.cash_shift_id,
            status=payment.status.value,
            idempotency_key=payment.idempotency_key,
            created_at=payment.created_at,
        )


class PostgresGuestSessionPaymentRepository:
    def __init__(self, engine_provider: EngineProvider) -> None:
        self._engine_provider = engine_provider

    async def get(self, payment_id: uuid.UUID) -> GuestSessionPayment | None:
        async with open_session(self._engine_provider) as session:
            model = await session.get(GuestSessionPaymentModel, payment_id)
            return model.to_domain() if model else None

    async def get_by_idempotency_key(self, key: str) -> GuestSessionPayment | None:
        async with open_session(self._engine_provider) as session:
            model = await session.scalar(
                select(GuestSessionPaymentModel).where(
                    GuestSessionPaymentModel.idempotency_key == key
                )
            )
            return model.to_domain() if model else None

    async def save(self, payment: GuestSessionPayment) -> GuestSessionPayment:
        async with open_session(self._engine_provider) as session:
            async with session.begin():
                model = await session.scalar(
                    select(GuestSessionPaymentModel).where(
                        GuestSessionPaymentModel.idempotency_key == payment.idempotency_key
                    )
                )
                if model is not None:
                    return model.to_domain()
                session.add(GuestSessionPaymentModel.from_domain(payment))
                return payment
