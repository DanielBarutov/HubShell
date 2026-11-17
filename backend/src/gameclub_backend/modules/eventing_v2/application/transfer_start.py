from __future__ import annotations

import datetime
import hashlib
import json
import re
import typing
import uuid
from dataclasses import dataclass

from gameclub_backend.application.errors import ApplicationError, ErrorCode
from gameclub_backend.modules.catalog.application.service import CatalogService
from gameclub_backend.modules.catalog.domain import BillingMode
from gameclub_backend.modules.clients.application.portal import (
    ClientPortalService,
    ClientPortalSnapshot,
)
from gameclub_backend.modules.entitlements.domain import EntitlementStatus
from gameclub_backend.modules.eventing_v2.application.guest_transfer_time import (
    GuestTransferClock,
    GuestTransferTime,
)
from gameclub_backend.modules.sessions.application.service import SessionService
from gameclub_backend.modules.sessions.application.v2_transfer import (
    V2TransferReservation,
    V2TransferTargetService,
)
from gameclub_backend.modules.sessions.domain import Session
from gameclub_backend.modules.workstations.application.service import WorkstationService
from gameclub_backend.modules.workstations.domain import Workstation


class TransferStartRepository(typing.Protocol):
    async def prepare(
        self,
        operation_id: uuid.UUID,
        session_id: uuid.UUID,
        source_workstation_id: uuid.UUID,
        target_workstation_id: uuid.UUID,
        quote_token: str,
    ) -> V2TransferReservation: ...

    async def get_for_workstation(
        self, operation_id: uuid.UUID, workstation_id: uuid.UUID
    ) -> V2TransferReservation: ...


@dataclass(frozen=True)
class V2TransferQuote:
    token: str
    per_minute_price_cents: int | None
    burned_package_id: uuid.UUID | None
    burned_package_name: str | None
    burned_package_minutes: int | None
    fallback_grant_minutes: int | None


class V2TransferStartService:
    def __init__(
        self,
        sessions: SessionService,
        workstations: WorkstationService,
        targets: V2TransferTargetService,
        operations: TransferStartRepository,
        portal: ClientPortalService,
        catalog: CatalogService,
        login_grant_minutes: int,
        clock: typing.Callable[[], datetime.datetime] | None = None,
        guest_clock: GuestTransferClock | None = None,
    ) -> None:
        self._sessions = sessions
        self._workstations = workstations
        self._targets = targets
        self._operations = operations
        self._portal = portal
        self._catalog = catalog
        self._login_grant_minutes = login_grant_minutes
        self._clock = clock or (lambda: datetime.datetime.now(datetime.UTC))
        self._guest_clock = guest_clock

    async def quote(
        self, device_id: str, session_id: uuid.UUID, target_id: uuid.UUID
    ) -> V2TransferQuote:
        targets = await self._targets.list_targets(device_id, session_id)
        if not any(target.workstation_id == target_id for target in targets):
            raise ApplicationError(ErrorCode.CONFLICT, "Transfer target is no longer available")
        session = await self._sessions.get(session_id)
        target = await self._workstations.get(target_id)
        if target is None or target.device_id is None:
            raise ApplicationError(ErrorCode.CONFLICT, "Transfer target is no longer available")
        return await self.quote_for_target(session, target)

    async def quote_for_target(
        self, session: Session, target: Workstation, snapshot: ClientPortalSnapshot | None = None
    ) -> V2TransferQuote:
        if session.source == SessionService.GUEST_LOCAL_LEDGER_SOURCE:
            quote, _ = await self.guest_transfer_terms(session, target, self._clock())
            return quote
        if session.source != SessionService.LOCAL_LEDGER_SOURCE or session.client_id is None:
            raise ApplicationError(ErrorCode.CONFLICT, "Transfer requires an active V2 session")
        if target.device_id is None:
            raise ApplicationError(ErrorCode.CONFLICT, "Transfer target has no assigned device")
        if snapshot is None:
            snapshot = await self._portal.v2_offline_snapshot_for_device(
                session.client_id, target.device_id
            )
        now = self._clock()
        active = next(
            (item for item in snapshot.entitlements if item.status is EntitlementStatus.ACTIVE),
            None,
        )
        burned = (
            active if active is not None and not active.is_compatible(target.group_id) else None
        )
        burned_tariff = await self._catalog.get_tariff(burned.tariff_id) if burned else None
        per_minute = next(
            (item for item in snapshot.tariffs if item.billing_mode is BillingMode.PER_MINUTE),
            None,
        )
        has_package = any(
            item.remaining_minutes > 0
            and item.is_compatible(target.group_id)
            and item.is_available_at(now)
            for item in snapshot.entitlements
        )
        price = per_minute.price_per_minute_cents if per_minute else None
        grant = self._login_grant_minutes if per_minute is None and not has_package else None
        terms = (
            str(session.id),
            str(session.workstation_id),
            str(target.id),
            target.device_id,
            target.group_id,
            str(per_minute.id) if per_minute else None,
            price,
            str(burned.id) if burned else None,
            burned.remaining_minutes if burned else None,
            grant,
        )
        token = hashlib.sha256(json.dumps(terms, separators=(",", ":")).encode()).hexdigest()
        return V2TransferQuote(
            token,
            price,
            burned.id if burned else None,
            burned_tariff.name if burned_tariff else ("Пакет" if burned else None),
            burned.remaining_minutes if burned else None,
            grant,
        )

    async def guest_transfer_terms(
        self, session: Session, target: Workstation, now: datetime.datetime
    ) -> tuple[V2TransferQuote, GuestTransferTime]:
        if self._guest_clock is None:
            raise ApplicationError(
                ErrorCode.DEPENDENCY_UNAVAILABLE, "Guest transfer terms are unavailable"
            )
        source = await self._workstations.get(session.workstation_id)
        if source is None:
            raise ApplicationError(ErrorCode.CONFLICT, "Guest transfer source is unavailable")
        state = await self._guest_clock.at(session, source.group_id, now)
        if state.exhausted:
            raise ApplicationError(ErrorCode.CONFLICT, "Guest source has no time left")
        moved, burned = state.move(target.group_id, self._login_grant_minutes)
        has_package = any(
            item.status in (EntitlementStatus.ACTIVE, EntitlementStatus.QUEUED)
            and item.remaining_minutes > 0
            and item.compatible_with(target.group_id)
            for item in moved.packages
        )
        grant = None if has_package else moved.grant_minutes
        terms = (
            str(session.id),
            str(source.id),
            str(target.id),
            target.device_id,
            target.group_id,
            str(burned.grant_id) if burned else None,
            burned.remaining_minutes if burned else None,
            grant,
        )
        token = hashlib.sha256(json.dumps(terms, separators=(",", ":")).encode()).hexdigest()
        return V2TransferQuote(
            token,
            None,
            burned.grant_id if burned else None,
            burned.tariff_name if burned else None,
            burned.remaining_minutes if burned else None,
            grant,
        ), moved

    async def begin(
        self,
        device_id: str,
        session_id: uuid.UUID,
        target_id: uuid.UUID,
        operation_id: uuid.UUID,
        quote_token: str,
    ) -> V2TransferReservation:
        if not re.fullmatch(r"[0-9a-f]{64}", quote_token):
            raise ApplicationError(ErrorCode.INVALID_ARGUMENT, "Transfer quote is required")
        source = await self._workstations.get_by_device_id(device_id)
        existing = await self._replay(operation_id, source.id, session_id, target_id, quote_token)
        if existing is not None:
            return existing

        try:
            quote = await self.quote(device_id, session_id, target_id)
        except ApplicationError as error:
            if error.code is not ErrorCode.CONFLICT:
                raise
            existing = await self._replay(
                operation_id, source.id, session_id, target_id, quote_token
            )
            if existing is not None:
                return existing
            raise

        if quote.token != quote_token:
            raise ApplicationError(
                ErrorCode.CONFLICT, "Transfer terms changed; request a new quote"
            )
        return await self._operations.prepare(
            operation_id, session_id, source.id, target_id, quote_token
        )

    async def _replay(
        self,
        operation_id: uuid.UUID,
        source_id: uuid.UUID,
        session_id: uuid.UUID,
        target_id: uuid.UUID,
        quote_token: str,
    ) -> V2TransferReservation | None:
        try:
            existing = await self._operations.get_for_workstation(operation_id, source_id)
        except ApplicationError as error:
            if error.code is ErrorCode.NOT_FOUND:
                return None
            raise
        if (
            existing.source_workstation_id != source_id
            or existing.session_id != session_id
            or existing.target_workstation_id != target_id
            or existing.quote_token != quote_token
        ):
            raise ApplicationError(ErrorCode.CONFLICT, "Transfer operation parameters changed")
        return existing
