from __future__ import annotations

import datetime
import uuid

from gameclub_backend.application.errors import ApplicationError, ErrorCode
from gameclub_backend.modules.direct_payments.domain import DirectPaymentStatus
from gameclub_backend.modules.reservations.domain import ReservationStatus
from gameclub_backend.modules.sessions.application.ports import (
    ClientLookup,
    Clock,
    EntitlementLookup,
    GuestLookup,
    GuestPaymentLookup,
    MeterLookup,
    ReservationLookup,
    SessionRepository,
    WorkstationLookup,
)
from gameclub_backend.modules.sessions.domain import Session, SessionSnapshot, SessionStatus
from gameclub_backend.modules.workstations.domain import WorkstationStatus


class UtcClock:
    def now(self) -> datetime.datetime:
        return datetime.datetime.now(datetime.UTC)


class SessionService:
    LOGIN_GRANT_MINUTES = 5

    def __init__(
        self,
        repository: SessionRepository,
        workstations: WorkstationLookup,
        clients: ClientLookup,
        reservations: ReservationLookup | None = None,
        clock: Clock | None = None,
        guests: GuestLookup | None = None,
        guest_payments: GuestPaymentLookup | None = None,
        entitlements: EntitlementLookup | None = None,
        meters: MeterLookup | None = None,
    ) -> None:
        self._repository = repository
        self._workstations = workstations
        self._clients = clients
        self._guests = guests
        self._guest_payments = guest_payments
        self._reservations = reservations
        self._entitlements = entitlements
        self._meters = meters
        self._clock = clock or UtcClock()

    async def start(
        self,
        workstation_id: uuid.UUID,
        created_by: str,
        client_id: uuid.UUID | None = None,
        guest_name: str | None = None,
        source: str = "operator",
        reservation_id: uuid.UUID | None = None,
        idempotency_key: str | None = None,
        device_id: str | None = None,
        guest_id: uuid.UUID | None = None,
        tariff_id: uuid.UUID | None = None,
        tariff_quantity: int = 1,
        guest_payment_id: uuid.UUID | None = None,
        entitlement_id: uuid.UUID | None = None,
    ) -> Session:
        normalized_idempotency_key = idempotency_key.strip() if idempotency_key else None
        if idempotency_key is not None and (
            not normalized_idempotency_key or len(normalized_idempotency_key) > 128
        ):
            raise ApplicationError(ErrorCode.INVALID_ARGUMENT, "Idempotency key is required")
        normalized_created_by = created_by.strip()
        if not normalized_created_by:
            raise ApplicationError(ErrorCode.INVALID_ARGUMENT, "Session author is required")
        normalized_guest_name = guest_name.strip() if guest_name else None
        normalized_source = source.strip() or "operator"
        login_grant_minutes = self.LOGIN_GRANT_MINUTES if normalized_source == "device" else 0
        if tariff_quantity <= 0:
            raise ApplicationError(ErrorCode.INVALID_ARGUMENT, "Tariff quantity must be positive")
        workstation = await self._workstations.get(workstation_id)
        if workstation is None:
            raise ApplicationError(ErrorCode.NOT_FOUND, "Workstation not found")
        if workstation.status is WorkstationStatus.DISABLED:
            raise ApplicationError(ErrorCode.CONFLICT, "Workstation is disabled")
        if device_id is not None and workstation.device_id != device_id:
            raise ApplicationError(
                ErrorCode.PERMISSION_DENIED,
                "Device identity does not match workstation",
            )
        if client_id is not None and guest_id is not None:
            raise ApplicationError(
                ErrorCode.INVALID_ARGUMENT,
                "Client and guest cannot be used together",
            )
        if guest_id is not None:
            if self._guests is None:
                raise ApplicationError(
                    ErrorCode.DEPENDENCY_UNAVAILABLE,
                    "Guest lookup is not configured",
                )
            guest = await self._guests.get(guest_id)
            if guest is None:
                raise ApplicationError(ErrorCode.NOT_FOUND, "Guest not found")
            if guest_name and guest_name.strip() != guest.nickname:
                raise ApplicationError(
                    ErrorCode.INVALID_ARGUMENT,
                    "Guest name does not match guest profile",
                )
            normalized_guest_name = guest.nickname
        if client_id is None and guest_id is None:
            normalized_guest_name = normalized_guest_name or "Гость"
        if client_id is not None and await self._clients.get(client_id) is None:
            raise ApplicationError(ErrorCode.NOT_FOUND, "Client not found")
        if client_id is not None and self._entitlements is not None:
            active_entitlement = await self._entitlements.get_active_for_client(client_id)
            if entitlement_id is not None:
                selected_entitlement = await self._entitlements.get(entitlement_id)
                if selected_entitlement is None:
                    raise ApplicationError(ErrorCode.NOT_FOUND, "Entitlement not found")
                if selected_entitlement.client_id != client_id:
                    raise ApplicationError(
                        ErrorCode.PERMISSION_DENIED,
                        "Entitlement belongs to another client",
                    )
                if active_entitlement is None or active_entitlement.id != entitlement_id:
                    raise ApplicationError(ErrorCode.CONFLICT, "Session package is not active")
            elif active_entitlement is not None:
                entitlement_id = active_entitlement.id
            if active_entitlement is not None:
                if tariff_id is None:
                    tariff_id = active_entitlement.tariff_id
                elif tariff_id != active_entitlement.tariff_id:
                    raise ApplicationError(
                        ErrorCode.CONFLICT,
                        "Selected tariff conflicts with the active package",
                    )
        if client_id is not None and guest_payment_id is not None:
            raise ApplicationError(
                ErrorCode.INVALID_ARGUMENT,
                "Guest payment cannot be used for a client session",
            )
        if client_id is None and tariff_id is not None:
            if guest_payment_id is None:
                raise ApplicationError(
                    ErrorCode.CONFLICT,
                    "Confirmed guest payment is required before starting a tariff session",
                )
            if self._guest_payments is None:
                raise ApplicationError(
                    ErrorCode.DEPENDENCY_UNAVAILABLE,
                    "Guest payment lookup is not configured",
                )
            payment = await self._guest_payments.get(guest_payment_id)
            if payment is None:
                raise ApplicationError(ErrorCode.NOT_FOUND, "Guest payment not found")
            if (
                payment.workstation_id != workstation_id
                or payment.tariff_id != tariff_id
                or payment.tariff_quantity != tariff_quantity
                or payment.guest_id != guest_id
            ):
                raise ApplicationError(ErrorCode.CONFLICT, "Guest payment does not match session")
            if payment.status is not DirectPaymentStatus.CONFIRMED:
                raise ApplicationError(
                    ErrorCode.CONFLICT,
                    "Guest payment has not been confirmed",
                )
        if reservation_id is not None:
            if self._reservations is None:
                raise ApplicationError(
                    ErrorCode.DEPENDENCY_UNAVAILABLE,
                    "Reservation lookup is not configured",
                )
            reservation = await self._reservations.get(reservation_id)
            if reservation is None:
                raise ApplicationError(ErrorCode.NOT_FOUND, "Reservation not found")
            if workstation_id not in reservation.workstation_ids or reservation.status not in {
                ReservationStatus.CONFIRMED,
                ReservationStatus.ACTIVE,
            }:
                raise ApplicationError(
                    ErrorCode.CONFLICT,
                    "Reservation cannot be used for this session",
                )
        if normalized_idempotency_key:
            existing = await self._repository.get_by_idempotency_key(normalized_idempotency_key)
            if existing is not None:
                self._validate_idempotent_session(
                    existing,
                    workstation_id=workstation_id,
                    client_id=client_id,
                    guest_id=guest_id,
                    guest_name=normalized_guest_name,
                    source=normalized_source,
                    reservation_id=reservation_id,
                    created_by=normalized_created_by,
                    tariff_id=tariff_id,
                    tariff_quantity=tariff_quantity,
                    guest_payment_id=guest_payment_id,
                    login_grant_minutes=login_grant_minutes,
                    entitlement_id=entitlement_id,
                )
                return existing
        if self._reservations is not None and hasattr(self._reservations, "check_entry"):
            decision = await self._reservations.check_entry(
                workstation_id=workstation_id,
                client_id=client_id,
                guest_id=guest_id,
                now=self._clock.now(),
            )
            if not decision.allowed:
                raise ApplicationError(
                    ErrorCode.CONFLICT,
                    f"Entry denied: {decision.reason}",
                )
        if await self._repository.get_active_for_workstation(workstation_id) is not None:
            if normalized_idempotency_key:
                repeated = await self._repository.get_by_idempotency_key(normalized_idempotency_key)
                if repeated is not None:
                    self._validate_idempotent_session(
                        repeated,
                        workstation_id=workstation_id,
                        client_id=client_id,
                        guest_id=guest_id,
                        guest_name=normalized_guest_name,
                        source=normalized_source,
                        reservation_id=reservation_id,
                        created_by=normalized_created_by,
                        tariff_id=tariff_id,
                        tariff_quantity=tariff_quantity,
                        guest_payment_id=guest_payment_id,
                        login_grant_minutes=login_grant_minutes,
                        entitlement_id=entitlement_id,
                    )
                    return repeated
            raise ApplicationError(ErrorCode.CONFLICT, "Workstation already has an active session")
        if client_id is not None and await self._repository.get_active_for_client(client_id):
            raise ApplicationError(ErrorCode.CONFLICT, "Client already has an active session")

        now = self._clock.now()
        session = Session(
            id=uuid.uuid4(),
            workstation_id=workstation_id,
            client_id=client_id,
            guest_name=normalized_guest_name,
            status=SessionStatus.ACTIVE,
            started_at=now,
            ended_at=None,
            source=normalized_source,
            created_by=normalized_created_by,
            created_at=now,
            reservation_id=reservation_id,
            idempotency_key=normalized_idempotency_key,
            guest_id=guest_id,
            tariff_id=tariff_id,
            tariff_quantity=tariff_quantity,
            guest_payment_id=guest_payment_id,
            login_grant_minutes=login_grant_minutes,
            entitlement_id=entitlement_id,
        )
        try:
            saved = await self._repository.save(session)
        except ValueError as error:
            raise ApplicationError(ErrorCode.CONFLICT, str(error)) from error
        if saved.id != session.id and normalized_idempotency_key:
            self._validate_idempotent_session(
                saved,
                workstation_id=workstation_id,
                client_id=client_id,
                guest_id=guest_id,
                guest_name=normalized_guest_name,
                source=normalized_source,
                reservation_id=reservation_id,
                created_by=normalized_created_by,
                tariff_id=tariff_id,
                tariff_quantity=tariff_quantity,
                guest_payment_id=guest_payment_id,
                login_grant_minutes=login_grant_minutes,
                entitlement_id=entitlement_id,
            )
        return saved

    async def get(self, session_id: uuid.UUID) -> Session:
        session = await self._repository.get(session_id)
        if session is None:
            raise ApplicationError(ErrorCode.NOT_FOUND, "Session not found")
        return session

    async def list(
        self,
        workstation_id: uuid.UUID | None = None,
        active_only: bool = False,
    ) -> list[Session]:
        return await self._repository.list(workstation_id, active_only)

    async def list_for_client(self, client_id: uuid.UUID, limit: int = 50) -> list[Session]:
        return await self._repository.list_for_client(client_id, max(1, min(limit, 100)))

    async def snapshot(
        self,
        session_id: uuid.UUID,
        now: datetime.datetime | None = None,
    ) -> SessionSnapshot:
        session = await self.get(session_id)
        workstation = await self._workstations.get(session.workstation_id)
        if workstation is None:
            raise ApplicationError(ErrorCode.NOT_FOUND, "Workstation not found")
        client = await self._clients.get(session.client_id) if session.client_id else None
        active_entitlement = None
        entitlements = ()
        if session.client_id is not None and self._entitlements is not None:
            active_entitlement = await self._entitlements.get_active_for_client(session.client_id)
            entitlements = tuple(await self._entitlements.list_for_client(session.client_id))
        meter = await self._meters.get(session.id) if self._meters is not None else None
        server_time = now or self._clock.now()
        if server_time.tzinfo is None:
            raise ApplicationError(
                ErrorCode.INVALID_ARGUMENT,
                "Session snapshot time must include timezone",
            )
        return SessionSnapshot(
            schema_version=1,
            server_time=server_time,
            session=session,
            workstation_id=workstation.id,
            device_id=workstation.device_id,
            zone_id=workstation.group_id,
            client_id=session.client_id,
            balance_cents=client.balance_cents if client else None,
            balance_bonus=client.balance_bonus if client else None,
            active_entitlement=active_entitlement,
            entitlements=entitlements,
            meter=meter,
            allowed_actions=("stop",) if session.status is SessionStatus.ACTIVE else (),
        )

    @staticmethod
    def _validate_idempotent_session(
        existing: Session,
        *,
        workstation_id: uuid.UUID,
        client_id: uuid.UUID | None,
        guest_id: uuid.UUID | None,
        guest_name: str | None,
        source: str,
        reservation_id: uuid.UUID | None,
        created_by: str,
        tariff_id: uuid.UUID | None,
        tariff_quantity: int,
        guest_payment_id: uuid.UUID | None,
        login_grant_minutes: int,
        entitlement_id: uuid.UUID | None,
    ) -> None:
        if (
            existing.workstation_id != workstation_id
            or existing.client_id != client_id
            or existing.guest_id != guest_id
            or existing.guest_name != guest_name
            or existing.source != source
            or existing.reservation_id != reservation_id
            or existing.created_by != created_by
            or existing.tariff_id != tariff_id
            or existing.tariff_quantity != tariff_quantity
            or existing.guest_payment_id != guest_payment_id
            or existing.login_grant_minutes != login_grant_minutes
            or existing.entitlement_id != entitlement_id
        ):
            raise ApplicationError(
                ErrorCode.CONFLICT,
                "Idempotency key belongs to another session",
            )

    async def stop(self, session_id: uuid.UUID, device_id: str | None = None) -> Session:
        session = await self.get(session_id)
        if device_id is not None:
            workstation = await self._workstations.get(session.workstation_id)
            if workstation is None or workstation.device_id != device_id:
                raise ApplicationError(
                    ErrorCode.PERMISSION_DENIED,
                    "Device identity does not match workstation",
                )
        try:
            saved = await self._repository.save(session.stop(self._clock.now()))
        except ValueError as error:
            raise ApplicationError(ErrorCode.CONFLICT, str(error)) from error
        if saved.client_id is not None and self._entitlements is not None:
            await self._entitlements.burn_active_for_client(saved.client_id, "session_stop")
        return saved

    async def interrupt(
        self,
        session_id: uuid.UUID,
        interrupted_by: str,
        reason: str,
        idempotency_key: str,
    ) -> Session:
        """Operator action for an early finish; repeated completion is harmless."""
        if not interrupted_by.strip():
            raise ApplicationError(ErrorCode.INVALID_ARGUMENT, "Session interrupter is required")
        normalized_reason = reason.strip()
        if not normalized_reason or len(normalized_reason) > 256:
            raise ApplicationError(ErrorCode.INVALID_ARGUMENT, "Interruption reason is required")
        normalized_idempotency_key = idempotency_key.strip()
        if not normalized_idempotency_key or len(normalized_idempotency_key) > 128:
            raise ApplicationError(ErrorCode.INVALID_ARGUMENT, "Idempotency key is required")

        session = await self.get(session_id)
        try:
            saved = await self._repository.save(session.interrupt(self._clock.now()))
        except ValueError as error:
            raise ApplicationError(ErrorCode.CONFLICT, str(error)) from error
        if saved.client_id is not None and self._entitlements is not None:
            await self._entitlements.burn_active_for_client(saved.client_id, normalized_reason)
        return saved
