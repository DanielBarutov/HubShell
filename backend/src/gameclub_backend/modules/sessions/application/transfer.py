from __future__ import annotations

import asyncio
import datetime
import secrets
import uuid

from gameclub_backend.application.errors import ApplicationError, ErrorCode
from gameclub_backend.modules.reservations.application.ports import ReservationEntryLookup
from gameclub_backend.modules.sessions.application.ports import (
    Clock,
    EntitlementLookup,
    SessionRepository,
    SessionTransferRepository,
    WorkstationLookup,
)
from gameclub_backend.modules.sessions.domain import (
    Session,
    SessionTransferOffer,
    TransferStatus,
)
from gameclub_backend.modules.workstations.application.commands import WorkstationCommandService


class UtcClock:
    def now(self) -> datetime.datetime:
        return datetime.datetime.now(datetime.UTC)


class SessionTransferService:
    OFFER_MINUTES = 5

    def __init__(
        self,
        offers: SessionTransferRepository,
        sessions: SessionRepository,
        workstations: WorkstationLookup,
        reservations: ReservationEntryLookup | None = None,
        entitlements: EntitlementLookup | None = None,
        commands: WorkstationCommandService | None = None,
        clock: Clock | None = None,
    ) -> None:
        self._offers = offers
        self._sessions = sessions
        self._workstations = workstations
        self._reservations = reservations
        self._entitlements = entitlements
        self._commands = commands
        self._clock = clock or UtcClock()
        self._lock = asyncio.Lock()

    async def get(self, offer_id: uuid.UUID) -> SessionTransferOffer:
        offer = await self._offers.get(offer_id)
        if offer is None:
            raise ApplicationError(ErrorCode.NOT_FOUND, "Transfer offer not found")
        return offer

    async def restart_status(self, offer_id: uuid.UUID):
        if self._commands is None:
            raise ApplicationError(
                ErrorCode.DEPENDENCY_UNAVAILABLE,
                "Workstation command service is not configured",
            )
        command = await self._commands.get_by_idempotency_key(f"transfer-restart:{offer_id}")
        if command is None:
            raise ApplicationError(ErrorCode.NOT_FOUND, "Transfer restart command not found")
        return command

    async def create_offer(
        self,
        session_id: uuid.UUID,
        target_workstation_id: uuid.UUID,
        idempotency_key: str,
        actor_device_id: str | None = None,
    ) -> SessionTransferOffer:
        key = idempotency_key.strip()
        if not key or len(key) > 128:
            raise ApplicationError(ErrorCode.INVALID_ARGUMENT, "Idempotency key is required")
        existing = await self._offers.get_by_idempotency_key(key)
        if existing is not None:
            if (
                existing.session_id != session_id
                or existing.target_workstation_id != target_workstation_id
            ):
                raise ApplicationError(ErrorCode.CONFLICT, "Transfer key belongs to another offer")
            return existing
        session = await self._sessions.get(session_id)
        if session is None:
            raise ApplicationError(ErrorCode.NOT_FOUND, "Session not found")
        if session.status.value != "active" or session.client_id is None:
            raise ApplicationError(
                ErrorCode.CONFLICT,
                "Only an active client session can be transferred",
            )
        if actor_device_id is not None:
            source = await self._workstations.get(session.workstation_id)
            if source is None or source.device_id != actor_device_id.strip():
                raise ApplicationError(
                    ErrorCode.PERMISSION_DENIED,
                    "Transfer offer must be created by the source device",
                )
        if session.workstation_id == target_workstation_id:
            raise ApplicationError(
                ErrorCode.INVALID_ARGUMENT,
                "Transfer target must be another workstation",
            )
        target = await self._workstations.get(target_workstation_id)
        if target is None:
            raise ApplicationError(ErrorCode.NOT_FOUND, "Transfer target workstation not found")
        if target.status.value == "disabled":
            raise ApplicationError(ErrorCode.CONFLICT, "Transfer target workstation is disabled")
        if await self._sessions.get_active_for_workstation(target_workstation_id) is not None:
            raise ApplicationError(
                ErrorCode.CONFLICT,
                "Transfer target already has an active session",
            )
        if self._reservations is not None:
            decision = await self._reservations.check_entry(
                target_workstation_id,
                client_id=session.client_id,
                now=self._clock.now(),
            )
            if not decision.allowed:
                raise ApplicationError(
                    ErrorCode.CONFLICT,
                    f"Transfer entry denied: {decision.reason}",
                )
        requires_burn = False
        warning = None
        if self._entitlements is not None:
            active = await self._entitlements.get_active_for_client(session.client_id)
            requires_burn = active is not None and not active.is_compatible(target.group_id)
            if requires_burn:
                warning = "Активный пакет несовместим с новой зоной и сгорит после подтверждения"
        now = self._clock.now()
        offer = SessionTransferOffer(
            id=uuid.uuid4(),
            session_id=session.id,
            client_id=session.client_id,
            source_workstation_id=session.workstation_id,
            target_workstation_id=target_workstation_id,
            token=secrets.token_urlsafe(24),
            status=TransferStatus.PENDING,
            requires_package_burn=requires_burn,
            warning=warning,
            idempotency_key=key,
            confirm_idempotency_key=None,
            created_at=now,
            expires_at=now + datetime.timedelta(minutes=self.OFFER_MINUTES),
        )
        try:
            return await self._offers.save(offer)
        except ValueError as error:
            raise ApplicationError(ErrorCode.CONFLICT, str(error)) from error

    async def confirm(
        self,
        offer_id: uuid.UUID,
        idempotency_key: str,
        token: str | None = None,
        actor_device_id: str | None = None,
    ) -> tuple[SessionTransferOffer, Session]:
        key = idempotency_key.strip()
        if not key or len(key) > 128:
            raise ApplicationError(ErrorCode.INVALID_ARGUMENT, "Idempotency key is required")
        async with self._lock:
            offer = await self.get(offer_id)
            if token is not None and not secrets.compare_digest(token, offer.token):
                raise ApplicationError(ErrorCode.PERMISSION_DENIED, "Invalid transfer token")
            if actor_device_id is not None:
                target = await self._workstations.get(offer.target_workstation_id)
                if target is None or target.device_id != actor_device_id.strip():
                    raise ApplicationError(
                        ErrorCode.PERMISSION_DENIED,
                        "Transfer must be confirmed by the target device",
                    )
            now = self._clock.now()
            if offer.status is TransferStatus.CONFIRMED:
                if offer.confirm_idempotency_key != key:
                    raise ApplicationError(ErrorCode.CONFLICT, "Transfer already confirmed")
                session = await self._sessions.get(offer.session_id)
                if session is None:
                    raise ApplicationError(ErrorCode.NOT_FOUND, "Transferred session not found")
                return offer, session
            offer = offer.expire_if_needed(now)
            if offer.status is TransferStatus.EXPIRED:
                await self._offers.save(offer)
                raise ApplicationError(ErrorCode.CONFLICT, "Transfer offer has expired")
            session = await self._sessions.get(offer.session_id)
            if session is None:
                raise ApplicationError(ErrorCode.NOT_FOUND, "Session not found")
            if (
                session.status.value != "active"
                or session.workstation_id != offer.source_workstation_id
            ):
                raise ApplicationError(
                    ErrorCode.CONFLICT,
                    "Source session is no longer transferable",
                )
            target_session = await self._sessions.get_active_for_workstation(
                offer.target_workstation_id
            )
            if target_session is not None:
                raise ApplicationError(
                    ErrorCode.CONFLICT,
                    "Transfer target already has an active session",
                )
            try:
                transferred = session.transfer(offer.target_workstation_id)
                confirmed_offer = offer.confirm(key, now)
                commit_transfer = getattr(self._offers, "commit_transfer", None)
                if commit_transfer is not None:
                    confirmed, saved_session = await commit_transfer(
                        confirmed_offer,
                        transferred,
                    )
                else:
                    saved_session = await self._sessions.save(transferred)
                    confirmed = await self._offers.save(confirmed_offer)
            except ValueError as error:
                raise ApplicationError(ErrorCode.CONFLICT, str(error)) from error
            if offer.requires_package_burn and self._entitlements is not None:
                await self._entitlements.burn_active_for_client(
                    offer.client_id,
                    "transfer_zone_incompatible",
                )
            if self._commands is not None:
                try:
                    await self._commands.dispatch(
                        offer.source_workstation_id,
                        "system.restart",
                        '{"reason":"session_transfer"}',
                        f"transfer-restart:{offer.id}",
                    )
                except ApplicationError:
                    # Transfer ownership is committed; the old device can retry
                    # the duplicate-safe restart command independently.
                    pass
            return confirmed, saved_session
