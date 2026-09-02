from __future__ import annotations

import datetime
import uuid
from collections.abc import Mapping, Sequence

from gameclub_backend.application.errors import ApplicationError, ErrorCode
from gameclub_backend.modules.direct_payments.application.ports import (
    CashDirectSettlement,
    Clock,
    GuestSessionPaymentRepository,
    TariffLookup,
)
from gameclub_backend.modules.direct_payments.domain import (
    DirectPaymentStatus,
    GuestSessionPayment,
)
from gameclub_backend.modules.payment_methods.domain import PaymentPart, normalize_payment_parts


class UtcClock:
    def now(self) -> datetime.datetime:
        return datetime.datetime.now(datetime.UTC)


class GuestSessionPaymentService:
    def __init__(
        self,
        repository: GuestSessionPaymentRepository,
        tariffs: TariffLookup,
        cash: CashDirectSettlement,
        clock: Clock | None = None,
    ) -> None:
        self._repository = repository
        self._tariffs = tariffs
        self._cash = cash
        self._clock = clock or UtcClock()

    async def get(self, payment_id: uuid.UUID) -> GuestSessionPayment:
        payment = await self._repository.get(payment_id)
        if payment is None:
            raise ApplicationError(ErrorCode.NOT_FOUND, "Guest payment not found")
        return payment

    async def confirm(
        self,
        workstation_id: uuid.UUID,
        tariff_id: uuid.UUID,
        tariff_quantity: int,
        guest_name: str,
        actor_id: str,
        idempotency_key: str,
        payment_parts: Sequence[PaymentPart | Mapping[str, object]],
        guest_id: uuid.UUID | None = None,
        cash_shift_id: uuid.UUID | None = None,
    ) -> GuestSessionPayment:
        key = idempotency_key.strip()
        actor = actor_id.strip()
        if not key or len(key) > 128:
            raise ApplicationError(ErrorCode.INVALID_ARGUMENT, "Idempotency key is required")
        if not actor:
            raise ApplicationError(ErrorCode.INVALID_ARGUMENT, "Payment author is required")
        existing = await self._repository.get_by_idempotency_key(key)
        if existing is not None:
            if (
                existing.workstation_id != workstation_id
                or existing.tariff_id != tariff_id
                or existing.tariff_quantity != tariff_quantity
                or existing.guest_id != guest_id
            ):
                raise ApplicationError(
                    ErrorCode.CONFLICT,
                    "Idempotency key belongs to another payment",
                )
            return existing
        if tariff_quantity <= 0:
            raise ApplicationError(ErrorCode.INVALID_ARGUMENT, "Tariff quantity must be positive")
        tariff = await self._tariffs.get_tariff(tariff_id)
        if tariff is None:
            raise ApplicationError(ErrorCode.NOT_FOUND, "Tariff not found")
        if not tariff.active or tariff.price_cents <= 0:
            raise ApplicationError(ErrorCode.CONFLICT, "Tariff is not payable as a guest package")
        try:
            parts = normalize_payment_parts(
                payment_parts,
                tariff.price_cents * tariff_quantity,
            )
            payment = GuestSessionPayment(
                id=uuid.uuid4(),
                workstation_id=workstation_id,
                tariff_id=tariff_id,
                tariff_quantity=tariff_quantity,
                guest_id=guest_id,
                guest_name=guest_name,
                total_price_cents=tariff.price_cents * tariff_quantity,
                payment_parts=parts,
                cash_shift_id=cash_shift_id,
                status=DirectPaymentStatus.CONFIRMED,
                idempotency_key=key,
                created_at=self._clock.now(),
            )
        except ValueError as error:
            raise ApplicationError(ErrorCode.INVALID_ARGUMENT, str(error)) from error
        await self._cash.settle(
            shift_id=cash_shift_id,
            amount_cents=payment.total_price_cents,
            payment_idempotency_key=key,
            actor_id=actor,
        )
        try:
            return await self._repository.save(payment)
        except ValueError as error:
            raise ApplicationError(ErrorCode.CONFLICT, str(error)) from error
