from __future__ import annotations

import typing
import uuid

from gameclub_backend.application.audit import AuditEvent, AuditRepository
from gameclub_backend.application.errors import ApplicationError, ErrorCode
from gameclub_backend.domain.equipment import EquipmentType
from gameclub_backend.modules.direct_payments.application.ports import Clock, WorkstationLookup
from gameclub_backend.modules.direct_payments.application.service import GuestSessionPaymentService
from gameclub_backend.modules.direct_payments.domain import GuestSessionPayment
from gameclub_backend.modules.payment_methods.domain import PaymentPart
from gameclub_backend.modules.sessions.domain import Session, SessionStatus


class XboxSessions(typing.Protocol):
    async def apply_xbox_payment(self, payment: GuestSessionPayment) -> Session: ...
    async def get(self, session_id: uuid.UUID) -> Session: ...
    async def list(
        self, workstation_id: uuid.UUID | None = None, active_only: bool = False
    ) -> list[Session]: ...
    async def stop_xbox(self, session_id: uuid.UUID, expired_only: bool = False) -> Session: ...


class XboxTransaction(typing.Protocol):
    def __call__(self, workstation_id: uuid.UUID) -> typing.AsyncContextManager[None]: ...


class XboxService:
    def __init__(
        self,
        payments: GuestSessionPaymentService,
        sessions: XboxSessions,
        workstations: WorkstationLookup,
        transaction: XboxTransaction,
        clock: Clock,
        audit: AuditRepository | None = None,
    ) -> None:
        self._payments = payments
        self._sessions = sessions
        self._workstations = workstations
        self._transaction = transaction
        self._clock = clock
        self._audit = audit

    async def sell(
        self,
        *,
        workstation_id: uuid.UUID,
        tariff_id: uuid.UUID,
        actor_id: str,
        idempotency_key: str,
        payment_parts: typing.Sequence[PaymentPart | typing.Mapping[str, object]],
        cash_shift_id: uuid.UUID | None = None,
        session_id: uuid.UUID | None = None,
    ) -> GuestSessionPayment:
        async with self._transaction(workstation_id):
            workstation = await self._workstations.get(workstation_id)
            if (
                workstation is None
                or workstation.equipment_type is not EquipmentType.XBOX
                or workstation.status.value == "disabled"
            ):
                raise ApplicationError(ErrorCode.CONFLICT, "Available Xbox place is required")
            if session_id:
                session = await self._sessions.get(session_id)
                existing = await self._payments.get_by_idempotency_key(idempotency_key)
                if existing is None and (
                    session.status is not SessionStatus.ACTIVE
                    or session.expires_at is None
                    or session.expires_at <= self._clock.now()
                ):
                    raise ApplicationError(ErrorCode.CONFLICT, "Xbox session has already ended")
                # Repeated applied sales may be retried after completion; payment validation
                # happens before the immutable session application returns the old result.
                if session.workstation_id != workstation_id or session.source != "xbox":
                    raise ApplicationError(ErrorCode.CONFLICT, "Xbox session does not match place")
            payment = await self._payments.confirm(
                workstation_id=workstation_id,
                tariff_id=tariff_id,
                tariff_quantity=1,
                guest_name="Гость",
                actor_id=actor_id,
                idempotency_key=idempotency_key,
                payment_parts=payment_parts,
                cash_shift_id=cash_shift_id,
                session_id=session_id,
                xbox_sale=True,
            )
            await self._sessions.apply_xbox_payment(payment)
            return payment

    async def stop(self, session_id: uuid.UUID, actor_id: str = "system") -> Session:
        session = await self._sessions.get(session_id)
        async with self._transaction(session.workstation_id):
            before = await self._sessions.get(session_id)
            result = await self._sessions.stop_xbox(session_id)
            if before.status is SessionStatus.ACTIVE:
                await self._record_completion(result, actor_id, "operator_stop")
            return result

    async def expire(self) -> int:
        count = 0
        for session in await self._sessions.list(active_only=True):
            if (
                session.source == "xbox"
                and session.expires_at
                and session.expires_at <= self._clock.now()
            ):
                async with self._transaction(session.workstation_id):
                    before = await self._sessions.get(session.id)
                    updated = await self._sessions.stop_xbox(session.id, expired_only=True)
                    if (
                        before.status is SessionStatus.ACTIVE
                        and updated.status is SessionStatus.COMPLETED
                    ):
                        await self._record_completion(updated, "system", "time_expired")
                        count += 1
        return count

    async def _record_completion(self, session: Session, actor_id: str, reason: str) -> None:
        if self._audit is not None:
            await self._audit.record(
                AuditEvent(
                    id=uuid.uuid4(),
                    actor_id=actor_id,
                    action=f"xbox.{reason}",
                    resource_path=f"/api/v1/xbox/sessions/{session.id}/stop",
                    outcome="success",
                    status_code=200,
                    request_id=f"xbox-stop:{session.id}",
                    created_at=self._clock.now(),
                )
            )
