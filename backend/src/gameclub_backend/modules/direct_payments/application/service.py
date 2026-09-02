from __future__ import annotations

import asyncio
import datetime
import logging
import uuid
from collections.abc import Mapping, Sequence

from gameclub_backend.application.audit import AuditEvent, AuditRepository
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
        audit: AuditRepository | None = None,
    ) -> None:
        self._repository = repository
        self._tariffs = tariffs
        self._cash = cash
        self._clock = clock or UtcClock()
        self._audit = audit
        self._reconciliation_lock = asyncio.Lock()

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
            try:
                expected_parts = normalize_payment_parts(
                    payment_parts,
                    existing.total_price_cents,
                )
            except ValueError as error:
                raise ApplicationError(ErrorCode.INVALID_ARGUMENT, str(error)) from error
            if not self._matches_request(
                existing,
                workstation_id=workstation_id,
                tariff_id=tariff_id,
                tariff_quantity=tariff_quantity,
                guest_id=guest_id,
                guest_name=guest_name,
                cash_shift_id=cash_shift_id,
                payment_parts=expected_parts,
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
                status=DirectPaymentStatus.PENDING,
                idempotency_key=key,
                created_at=self._clock.now(),
                created_by=actor,
            )
        except ValueError as error:
            raise ApplicationError(ErrorCode.INVALID_ARGUMENT, str(error)) from error
        try:
            pending = await self._repository.save(payment)
        except ValueError as error:
            raise ApplicationError(ErrorCode.CONFLICT, str(error)) from error
        if pending.status is DirectPaymentStatus.CONFIRMED:
            return pending
        if pending.status is DirectPaymentStatus.NEEDS_REVIEW:
            return pending
        return await self._settle_pending(pending, actor)

    async def retry_pending(self, payment_id: uuid.UUID) -> GuestSessionPayment:
        payment = await self.get(payment_id)
        if payment.status is DirectPaymentStatus.NEEDS_REVIEW:
            raise ApplicationError(
                ErrorCode.CONFLICT,
                "Guest payment requires explicit supervisor review",
            )
        if payment.status is DirectPaymentStatus.CONFIRMED:
            return payment
        async with self._reconciliation_lock:
            payment = await self.get(payment_id)
            if payment.status is DirectPaymentStatus.CONFIRMED:
                return payment
            return await self._settle_pending(payment, payment.created_by)

    async def retry_reconciliation(
        self,
        payment_id: uuid.UUID,
        reviewed_by: str,
    ) -> GuestSessionPayment:
        if not reviewed_by.strip():
            raise ApplicationError(ErrorCode.INVALID_ARGUMENT, "Review author is required")
        payment = await self.get(payment_id)
        if payment.status is DirectPaymentStatus.CONFIRMED:
            return payment
        if payment.status is DirectPaymentStatus.NEEDS_REVIEW:
            payment = await self._repository.save(payment.reopen_for_review(self._clock.now()))
        result = await self.retry_pending(payment.id)
        await self._record_audit(
            action="guest_payment.review_retry",
            payment=result,
            actor_id=reviewed_by,
            outcome="success" if result.status is DirectPaymentStatus.CONFIRMED else "pending",
            status_code=200,
        )
        return result

    async def _settle_pending(
        self,
        payment: GuestSessionPayment,
        actor_id: str,
    ) -> GuestSessionPayment:
        now = self._clock.now()
        try:
            await self._cash.settle(
                shift_id=payment.cash_shift_id,
                amount_cents=payment.total_price_cents,
                payment_idempotency_key=payment.idempotency_key,
                actor_id=payment.created_by or actor_id,
            )
            result = await self._repository.save(payment.mark_confirmed(now))
            await self._record_audit(
                action="guest_payment.settlement",
                payment=result,
                actor_id=payment.created_by or actor_id,
                outcome="success",
                status_code=200,
            )
            return result
        except Exception as error:
            try:
                message = str(error) or error.__class__.__name__
                if self._is_retryable(error):
                    updated = payment.schedule_retry(message, now)
                else:
                    updated = payment.mark_needs_review(message, now)
                await self._repository.save(updated)
            except Exception:
                pass
            await self._record_audit(
                action="guest_payment.settlement",
                payment=payment,
                actor_id=payment.created_by or actor_id,
                outcome="retryable" if self._is_retryable(error) else "needs_review",
                status_code=500,
            )
            raise

    @staticmethod
    def _is_retryable(error: Exception) -> bool:
        return isinstance(error, ApplicationError) and error.code in {
            ErrorCode.DEPENDENCY_UNAVAILABLE,
            ErrorCode.INTERNAL,
        }

    async def _record_audit(
        self,
        *,
        action: str,
        payment: GuestSessionPayment,
        actor_id: str,
        outcome: str,
        status_code: int,
    ) -> None:
        if self._audit is None:
            return
        event = AuditEvent(
            id=uuid.uuid4(),
            actor_id=actor_id.strip() or None,
            action=action,
            resource_path=f"/api/v1/guest-payments/{payment.id}",
            outcome=outcome,
            status_code=status_code,
            request_id=payment.idempotency_key,
            created_at=self._clock.now(),
        )
        try:
            await self._audit.record(event)
        except Exception:
            logging.getLogger(__name__).warning(
                "guest_payment_audit_write_failed payment_id=%s",
                payment.id,
            )

    @staticmethod
    def _matches_request(
        payment: GuestSessionPayment,
        *,
        workstation_id: uuid.UUID,
        tariff_id: uuid.UUID,
        tariff_quantity: int,
        guest_id: uuid.UUID | None,
        guest_name: str,
        cash_shift_id: uuid.UUID | None,
        payment_parts: tuple[PaymentPart, ...],
    ) -> bool:
        return (
            payment.workstation_id == workstation_id
            and payment.tariff_id == tariff_id
            and payment.tariff_quantity == tariff_quantity
            and payment.guest_id == guest_id
            and payment.guest_name == guest_name.strip()
            and payment.cash_shift_id == cash_shift_id
            and payment.payment_parts == payment_parts
        )
