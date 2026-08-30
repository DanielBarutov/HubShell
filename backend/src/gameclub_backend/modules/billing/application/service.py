from __future__ import annotations

import datetime
import uuid

from gameclub_backend.application.errors import ApplicationError, ErrorCode
from gameclub_backend.modules.billing.application.ports import (
    CatalogQuoter,
    ChargeReconciliationRepository,
    ChargeRepository,
    ClientBilling,
    Clock,
    MeterRepository,
    SessionLookup,
    WorkstationLookup,
)
from gameclub_backend.modules.billing.domain import (
    ChargeReconciliation,
    MeterStatus,
    ReconciliationStatus,
    RevenueSummary,
    SessionCharge,
    SessionMeter,
)
from gameclub_backend.modules.catalog.domain import BillingMode
from gameclub_backend.modules.clients.domain import Client
from gameclub_backend.modules.sessions.domain import SessionStatus


class UtcClock:
    def now(self) -> datetime.datetime:
        return datetime.datetime.now(datetime.UTC)


class BillingService:
    def __init__(
        self,
        repository: ChargeRepository,
        sessions: SessionLookup,
        workstations: WorkstationLookup,
        clients: ClientBilling,
        catalog: CatalogQuoter,
        clock: Clock | None = None,
        reconciliation: ChargeReconciliationRepository | None = None,
        meter_repository: MeterRepository | None = None,
    ) -> None:
        self._repository = repository
        self._sessions = sessions
        self._workstations = workstations
        self._clients = clients
        self._catalog = catalog
        self._clock = clock or UtcClock()
        self._reconciliation = reconciliation
        self._meter_repository = meter_repository

    async def get_meter(self, session_id: uuid.UUID) -> SessionMeter:
        if self._meter_repository is None:
            raise ApplicationError(
                ErrorCode.DEPENDENCY_UNAVAILABLE,
                "Session metering is not configured",
            )
        meter = await self._meter_repository.get(session_id)
        if meter is None:
            raise ApplicationError(ErrorCode.NOT_FOUND, "Session meter not found")
        return meter

    async def meter_session(
        self,
        session_id: uuid.UUID,
        now: datetime.datetime | None = None,
        charged_by: str = "system",
        allow_completed: bool = False,
    ) -> SessionMeter | None:
        if self._meter_repository is None:
            raise ApplicationError(
                ErrorCode.DEPENDENCY_UNAVAILABLE,
                "Session metering is not configured",
            )
        async with self._meter_repository.acquire(session_id):
            return await self._meter_session_locked(
                session_id=session_id,
                now=now,
                charged_by=charged_by,
                allow_completed=allow_completed,
            )

    async def _meter_session_locked(
        self,
        session_id: uuid.UUID,
        now: datetime.datetime | None = None,
        charged_by: str = "system",
        allow_completed: bool = False,
    ) -> SessionMeter | None:
        """Charge the monotonic per-minute delta for an active session."""
        if self._meter_repository is None:
            raise ApplicationError(
                ErrorCode.DEPENDENCY_UNAVAILABLE,
                "Session metering is not configured",
            )
        session = await self._sessions.get(session_id)
        if session is None:
            raise ApplicationError(ErrorCode.NOT_FOUND, "Session not found")
        if session.status is not SessionStatus.ACTIVE and not allow_completed:
            raise ApplicationError(ErrorCode.CONFLICT, "Only an active session can be metered")
        if session.client_id is None or session.tariff_id is None:
            return None
        tariff = await self._catalog.get_tariff(session.tariff_id)
        if tariff is None or tariff.billing_mode is not BillingMode.PER_MINUTE:
            return None
        workstation = await self._workstations.get(session.workstation_id)
        if workstation is None:
            raise ApplicationError(ErrorCode.NOT_FOUND, "Workstation not found")
        client = await self._clients.get(session.client_id)
        moment = now or self._clock.now()
        end_at = session.ended_at or moment
        elapsed_minutes = self._elapsed_minutes(session.started_at, end_at)
        billable_minutes = max(0, elapsed_minutes - tariff.free_minutes)
        quote = await self._catalog.quote_for_tariff(
            tariff_id=tariff.id,
            group_id=workstation.group_id,
            moment=session.started_at,
            discount_category=client.discount_category,
            duration_minutes=elapsed_minutes or 1,
        )
        current = await self._meter_repository.get(session.id)
        if current is None:
            current = await self._meter_repository.ensure(
                SessionMeter(
                    session_id=session.id,
                    client_id=session.client_id,
                    tariff_id=tariff.id,
                    billed_minutes=0,
                    billed_cents=0,
                    status=MeterStatus.RUNNING,
                    last_operation_id=None,
                    created_at=session.started_at,
                    updated_at=moment,
                )
            )
        if current.status is MeterStatus.EXHAUSTED:
            return current
        target_cents = quote.price_cents
        operation_id: uuid.UUID | None = current.last_operation_id
        if target_cents > current.billed_cents:
            client, operation = await self._debit_meter_delta(
                client_id=session.client_id,
                amount_cents=target_cents - current.billed_cents,
                session_id=session.id,
                billed_minutes=billable_minutes,
                charged_by=charged_by,
            )
            del client
            operation_id = operation.id
        status = (
            MeterStatus.SETTLED
            if session.status is SessionStatus.COMPLETED
            else MeterStatus.RUNNING
        )
        return await self._meter_repository.save(
            current.advance(
                billed_minutes=billable_minutes,
                billed_cents=target_cents,
                operation_id=operation_id,
                now=moment,
                status=status,
            )
        )

    async def _debit_meter_delta(
        self,
        client_id: uuid.UUID,
        amount_cents: int,
        session_id: uuid.UUID,
        billed_minutes: int,
        charged_by: str,
    ):
        try:
            return await self._clients.debit(
                client_id=client_id,
                amount_cents=amount_cents,
                reason=f"Per-minute session {session_id}",
                actor_id=charged_by or "system",
                idempotency_key=f"session-meter:{session_id}:{billed_minutes}",
            )
        except ApplicationError as error:
            if error.message == "Insufficient balance":
                meter = await self._meter_repository.get(session_id)
                if meter is not None:
                    await self._meter_repository.save(
                        meter.advance(
                            billed_minutes=meter.billed_minutes,
                            billed_cents=meter.billed_cents,
                            operation_id=None,
                            now=self._clock.now(),
                            status=MeterStatus.EXHAUSTED,
                        )
                    )
            raise

    async def get_by_session_id(self, session_id: uuid.UUID) -> SessionCharge:
        charge = await self._repository.get_by_session_id(session_id)
        if charge is None:
            raise ApplicationError(ErrorCode.NOT_FOUND, "Session charge not found")
        return charge

    async def get_session_charge(self, session_id: uuid.UUID) -> tuple[SessionCharge, Client]:
        charge = await self.get_by_session_id(session_id)
        return charge, await self._clients.get(charge.client_id)

    async def list_reconciliation(self, limit: int = 50) -> list[ChargeReconciliation]:
        if self._reconciliation is None:
            return []
        return await self._reconciliation.list_recent(max(1, min(limit, 500)))

    async def revenue_between(
        self,
        start_at: datetime.datetime,
        end_at: datetime.datetime,
    ) -> RevenueSummary:
        if start_at.tzinfo is None or end_at.tzinfo is None or start_at >= end_at:
            raise ApplicationError(
                ErrorCode.INVALID_ARGUMENT,
                "Revenue period must contain aware UTC timestamps with start before end",
            )
        start_at = start_at.astimezone(datetime.UTC)
        end_at = end_at.astimezone(datetime.UTC)
        if start_at >= end_at:
            raise ApplicationError(
                ErrorCode.INVALID_ARGUMENT,
                "Revenue period must contain aware UTC timestamps with start before end",
            )
        return await self._repository.revenue_between(start_at, end_at)

    async def charge_session(
        self,
        session_id: uuid.UUID,
        charged_by: str,
        idempotency_key: str,
    ) -> tuple[SessionCharge, Client]:
        normalized_key = idempotency_key.strip()
        if not normalized_key or len(normalized_key) > 128:
            raise ApplicationError(ErrorCode.INVALID_ARGUMENT, "Idempotency key is required")

        existing_by_key = await self._repository.get_by_idempotency_key(normalized_key)
        if existing_by_key is not None:
            if existing_by_key.session_id != session_id:
                raise ApplicationError(
                    ErrorCode.CONFLICT,
                    "Idempotency key belongs to another session",
                )
            client = await self._clients.get(existing_by_key.client_id)
            await self._complete_reconciliation(existing_by_key)
            return existing_by_key, client

        existing_by_session = await self._repository.get_by_session_id(session_id)
        if existing_by_session is not None:
            client = await self._clients.get(existing_by_session.client_id)
            await self._complete_reconciliation(existing_by_session)
            return existing_by_session, client

        session = await self._sessions.get(session_id)
        if session is None:
            raise ApplicationError(ErrorCode.NOT_FOUND, "Session not found")
        if session.status is not SessionStatus.COMPLETED or session.ended_at is None:
            raise ApplicationError(
                ErrorCode.CONFLICT,
                "Only a completed session can be charged",
            )
        if session.client_id is None:
            raise ApplicationError(
                ErrorCode.CONFLICT,
                "Guest sessions require a cashier flow before charging",
            )
        if session.ended_at <= session.started_at:
            raise ApplicationError(ErrorCode.CONFLICT, "Session duration is invalid")

        workstation = await self._workstations.get(session.workstation_id)
        if workstation is None:
            raise ApplicationError(ErrorCode.NOT_FOUND, "Workstation not found")
        client = await self._clients.get(session.client_id)
        duration_minutes = self._billable_minutes(session.started_at, session.ended_at)
        meter: SessionMeter | None = None
        if session.tariff_id is not None:
            tariff = await self._catalog.get_tariff(session.tariff_id)
            if tariff is not None and tariff.billing_mode is BillingMode.PER_MINUTE:
                meter = await self.meter_session(
                    session.id,
                    now=session.ended_at,
                    charged_by=charged_by,
                    allow_completed=True,
                )
            quote = await self._catalog.quote_for_tariff(
                tariff_id=session.tariff_id,
                group_id=workstation.group_id,
                moment=session.started_at,
                discount_category=client.discount_category,
                duration_minutes=duration_minutes,
                quantity=session.tariff_quantity,
            )
        else:
            quote = await self._catalog.quote(
                duration_minutes=duration_minutes,
                group_id=workstation.group_id,
                moment=session.started_at,
                discount_category=client.discount_category,
            )

        reconciliation = await self._ensure_reconciliation(
            session_id=session.id,
            charged_by=charged_by,
            idempotency_key=normalized_key,
        )
        if reconciliation is not None:
            if reconciliation.status is ReconciliationStatus.COMPLETED:
                raise ApplicationError(
                    ErrorCode.CONFLICT,
                    "Reconciliation is completed but its charge is missing",
                )
            if reconciliation.status is ReconciliationStatus.NEEDS_REVIEW:
                raise ApplicationError(
                    ErrorCode.CONFLICT,
                    reconciliation.last_error or "Billing reconciliation needs review",
                )
            normalized_key = reconciliation.idempotency_key
            charged_by = reconciliation.charged_by

        ledger_key = f"session-charge:{session.id}"
        try:
            if meter is None:
                charged_client, operation = await self._clients.debit(
                    client_id=client.id,
                    amount_cents=quote.price_cents,
                    reason=f"Gaming session {session.id}",
                    actor_id=charged_by,
                    idempotency_key=ledger_key,
                )
                if -operation.amount_cents != quote.price_cents:
                    raise ApplicationError(
                        ErrorCode.CONFLICT,
                        "Existing session debit does not match the current catalog quote",
                    )
                amount_cents = quote.price_cents
                balance_operation_id = operation.id
            else:
                charged_client = await self._clients.get(client.id)
                amount_cents = meter.billed_cents
                balance_operation_id = meter.last_operation_id or uuid.UUID(int=0)
            charge = SessionCharge(
                id=uuid.uuid4(),
                session_id=session.id,
                client_id=client.id,
                balance_operation_id=balance_operation_id,
                tariff_id=quote.tariff_id,
                duration_minutes=quote.duration_minutes,
                amount_cents=amount_cents,
                amount_before_discount_cents=quote.price_before_discount_cents,
                discount_amount_cents=quote.discount_amount_cents,
                discount_percent_bps=quote.discount_percent_bps,
                discount_category=quote.discount_category,
                charged_by=charged_by,
                idempotency_key=normalized_key,
                created_at=self._clock.now(),
            )
            saved = await self._repository.save(charge)
        except ValueError as error:
            application_error = ApplicationError(ErrorCode.CONFLICT, str(error))
            await self._record_reconciliation_failure(reconciliation, application_error)
            raise application_error from error
        except ApplicationError as error:
            await self._record_reconciliation_failure(reconciliation, error)
            raise
        except Exception as error:
            await self._record_reconciliation_failure(reconciliation, error)
            raise
        await self._complete_reconciliation(saved)
        return saved, charged_client

    async def _ensure_reconciliation(
        self,
        session_id: uuid.UUID,
        charged_by: str,
        idempotency_key: str,
    ) -> ChargeReconciliation | None:
        if self._reconciliation is None:
            return None
        now = self._clock.now()
        item = ChargeReconciliation(
            session_id=session_id,
            idempotency_key=idempotency_key,
            charged_by=charged_by,
            status=ReconciliationStatus.PENDING,
            attempts=0,
            next_attempt_at=now,
            last_error=None,
            charge_id=None,
            created_at=now,
            updated_at=now,
        )
        try:
            return await self._reconciliation.ensure_pending(item)
        except ValueError as error:
            raise ApplicationError(ErrorCode.CONFLICT, str(error)) from error

    async def _complete_reconciliation(self, charge: SessionCharge) -> None:
        if self._reconciliation is None:
            return
        item = await self._reconciliation.get_by_session_id(charge.session_id)
        if item is None:
            now = self._clock.now()
            item = ChargeReconciliation(
                session_id=charge.session_id,
                idempotency_key=charge.idempotency_key,
                charged_by=charge.charged_by,
                status=ReconciliationStatus.PENDING,
                attempts=0,
                next_attempt_at=now,
                last_error=None,
                charge_id=None,
                created_at=now,
                updated_at=now,
            )
            item = await self._reconciliation.ensure_pending(item)
        await self._reconciliation.save(item.mark_completed(charge.id, self._clock.now()))

    async def _record_reconciliation_failure(
        self,
        item: ChargeReconciliation | None,
        error: Exception,
    ) -> None:
        if item is None or self._reconciliation is None:
            return
        now = self._clock.now()
        message = str(error) or error.__class__.__name__
        retryable = not isinstance(error, ApplicationError)
        if isinstance(error, ApplicationError):
            retryable = (
                error.code
                in {
                    ErrorCode.DEPENDENCY_UNAVAILABLE,
                    ErrorCode.INTERNAL,
                }
                or error.message == "Insufficient balance"
            )
        updated = (
            item.schedule_retry(message, now) if retryable else item.mark_needs_review(message, now)
        )
        try:
            await self._reconciliation.save(updated)
        except Exception:
            # Keep the original billing error visible; the next API/worker attempt
            # will reconstruct the durable state if the repository is available.
            return

    @staticmethod
    def _elapsed_minutes(
        started_at: datetime.datetime,
        ended_at: datetime.datetime,
    ) -> int:
        elapsed = ended_at - started_at
        total_microseconds = (
            elapsed.days * 86_400 * 1_000_000 + elapsed.seconds * 1_000_000 + elapsed.microseconds
        )
        return max(0, (total_microseconds + 60_000_000 - 1) // 60_000_000)

    @staticmethod
    def _billable_minutes(
        started_at: datetime.datetime,
        ended_at: datetime.datetime,
    ) -> int:
        elapsed = ended_at - started_at
        elapsed_microseconds = (
            elapsed.days * 86_400 * 1_000_000 + elapsed.seconds * 1_000_000 + elapsed.microseconds
        )
        return max(1, (elapsed_microseconds + 60_000_000 - 1) // 60_000_000)
