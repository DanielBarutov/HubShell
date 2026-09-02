from __future__ import annotations

import dataclasses
import datetime
import uuid

from gameclub_backend.application.errors import ApplicationError, ErrorCode
from gameclub_backend.modules.entitlements.application.ports import (
    ActiveSessionLookup,
    ClientEntitlementDebit,
    Clock,
    EntitlementRepository,
    TariffLookup,
    WorkstationLookup,
)
from gameclub_backend.modules.entitlements.domain import Entitlement, EntitlementStatus


class UtcClock:
    def now(self) -> datetime.datetime:
        return datetime.datetime.now(datetime.UTC)


@dataclasses.dataclass(frozen=True)
class EntitlementConsumption:
    consumed_minutes: int
    active_entitlement_id: uuid.UUID | None
    active_remaining_minutes: int
    exhausted_entitlement_ids: tuple[uuid.UUID, ...] = ()


class EntitlementService:
    def __init__(
        self,
        repository: EntitlementRepository,
        tariffs: TariffLookup,
        clients: ClientEntitlementDebit,
        clock: Clock | None = None,
        active_sessions: ActiveSessionLookup | None = None,
        workstations: WorkstationLookup | None = None,
    ) -> None:
        self._repository = repository
        self._tariffs = tariffs
        self._clients = clients
        self._clock = clock or UtcClock()
        self._active_sessions = active_sessions
        self._workstations = workstations

    async def list_for_client(self, client_id: uuid.UUID) -> list[Entitlement]:
        return await self._repository.list_for_client(client_id)

    async def get(self, entitlement_id: uuid.UUID) -> Entitlement:
        entitlement = await self._repository.get(entitlement_id)
        if entitlement is None:
            raise ApplicationError(ErrorCode.NOT_FOUND, "Entitlement not found")
        return entitlement

    async def get_active_for_client(self, client_id: uuid.UUID) -> Entitlement | None:
        return await self._repository.get_active_for_client(client_id)

    async def burn_active_for_client(
        self,
        client_id: uuid.UUID,
        reason: str,
    ) -> Entitlement | None:
        active = await self._repository.get_active_for_client(client_id)
        if active is None:
            return None
        return await self.burn(active.id, client_id, reason)

    async def purchase(
        self,
        client_id: uuid.UUID,
        tariff_id: uuid.UUID,
        actor_id: str,
        idempotency_key: str,
    ) -> Entitlement:
        key = idempotency_key.strip()
        actor = actor_id.strip()
        if not key or len(key) > 128:
            raise ApplicationError(ErrorCode.INVALID_ARGUMENT, "Idempotency key is required")
        if not actor:
            raise ApplicationError(ErrorCode.INVALID_ARGUMENT, "Purchase author is required")
        existing = await self._repository.get_by_idempotency_key(key)
        if existing is not None:
            if existing.client_id != client_id or existing.tariff_id != tariff_id:
                raise ApplicationError(
                    ErrorCode.CONFLICT,
                    "Idempotency key belongs to another package",
                )
            return existing
        tariff = await self._tariffs.get_tariff(tariff_id)
        if tariff is None:
            raise ApplicationError(ErrorCode.NOT_FOUND, "Tariff not found")
        if not tariff.active:
            raise ApplicationError(ErrorCode.CONFLICT, "Tariff is inactive")
        now = self._clock.now()
        try:
            queued = await self._repository.list_for_client(client_id)
            position = max((item.queue_position for item in queued), default=0) + 1
            entitlement = Entitlement(
                id=uuid.uuid4(),
                client_id=client_id,
                tariff_id=tariff.id,
                zone_id=tariff.group_id,
                duration_minutes=tariff.duration_minutes,
                remaining_minutes=tariff.duration_minutes,
                price_cents=tariff.price_cents,
                queue_position=position,
                status=EntitlementStatus.QUEUED,
                idempotency_key=key,
                purchased_at=now,
                window_start_minute=tariff.window_start_minute,
                window_end_minute=tariff.window_end_minute,
                window_timezone=tariff.window_timezone,
            )
        except ValueError as error:
            raise ApplicationError(ErrorCode.INVALID_ARGUMENT, str(error)) from error
        await self._clients.debit(
            client_id=client_id,
            amount_cents=tariff.price_cents,
            reason=f"Package purchase {entitlement.id}",
            actor_id=actor,
            idempotency_key=f"entitlement-purchase:{key}",
        )
        try:
            created = await self._repository.create(entitlement)
        except ValueError as error:
            raise ApplicationError(ErrorCode.CONFLICT, str(error)) from error
        if (
            self._active_sessions is not None
            and self._workstations is not None
            and not any(item.status is EntitlementStatus.QUEUED for item in queued)
        ):
            active_session = await self._active_sessions.get_active_for_client(client_id)
            if active_session is not None:
                workstation = await self._workstations.get(active_session.workstation_id)
                if workstation is not None and created.is_compatible(workstation.group_id):
                    try:
                        if created.is_available_at(now):
                            return await self._repository.activate_for_client(
                                created.id,
                                client_id,
                                now,
                                workstation.group_id,
                            )
                    except ValueError as error:
                        raise ApplicationError(ErrorCode.CONFLICT, str(error)) from error
        return created

    async def activate(self, entitlement_id: uuid.UUID, client_id: uuid.UUID) -> Entitlement:
        entitlement = await self.get(entitlement_id)
        if entitlement.client_id != client_id:
            raise ApplicationError(
                ErrorCode.PERMISSION_DENIED,
                "Entitlement belongs to another client",
            )
        active = await self._repository.get_active_for_client(client_id)
        if active is not None and active.id != entitlement_id:
            raise ApplicationError(ErrorCode.CONFLICT, "Client already has an active package")
        now = self._clock.now()
        try:
            return await self._repository.activate_for_client(
                entitlement_id,
                client_id,
                now,
            )
        except ValueError as error:
            raise ApplicationError(ErrorCode.CONFLICT, str(error)) from error

    async def consume(
        self,
        entitlement_id: uuid.UUID,
        client_id: uuid.UUID,
        minutes: int,
    ) -> Entitlement:
        entitlement = await self.get(entitlement_id)
        if entitlement.client_id != client_id:
            raise ApplicationError(
                ErrorCode.PERMISSION_DENIED,
                "Entitlement belongs to another client",
            )
        try:
            return await self._repository.consume_for_client(
                entitlement_id,
                client_id,
                minutes,
                self._clock.now(),
            )
        except ValueError as error:
            raise ApplicationError(ErrorCode.CONFLICT, str(error)) from error

    async def burn(
        self,
        entitlement_id: uuid.UUID,
        client_id: uuid.UUID,
        reason: str,
    ) -> Entitlement:
        entitlement = await self.get(entitlement_id)
        if entitlement.client_id != client_id:
            raise ApplicationError(
                ErrorCode.PERMISSION_DENIED,
                "Entitlement belongs to another client",
            )
        try:
            return await self._repository.burn_for_client(
                entitlement_id,
                client_id,
                reason,
                self._clock.now(),
            )
        except ValueError as error:
            raise ApplicationError(ErrorCode.INVALID_ARGUMENT, str(error)) from error

    async def next_compatible(
        self,
        client_id: uuid.UUID,
        zone_id: str | None,
        now: datetime.datetime | None = None,
    ) -> Entitlement | None:
        return await self._repository.next_compatible(
            client_id,
            zone_id,
            now=now or self._clock.now(),
        )

    async def consume_for_session(
        self,
        client_id: uuid.UUID,
        zone_id: str | None,
        minutes: int,
        now: datetime.datetime | None = None,
        initial_entitlement_id: uuid.UUID | None = None,
    ) -> EntitlementConsumption:
        """Consume active package minutes and auto-start the next compatible item."""
        if minutes < 0:
            raise ApplicationError(
                ErrorCode.INVALID_ARGUMENT,
                "Consumed minutes cannot be negative",
            )
        if minutes == 0:
            active = await self._repository.get_active_for_client(client_id)
            return EntitlementConsumption(
                consumed_minutes=0,
                active_entitlement_id=active.id if active else None,
                active_remaining_minutes=active.remaining_minutes if active else 0,
            )
        moment = now or self._clock.now()
        remaining_to_consume = minutes
        consumed = 0
        exhausted: list[uuid.UUID] = []
        active = await self._repository.get_active_for_client(client_id)
        if initial_entitlement_id is not None:
            if active is None or active.id != initial_entitlement_id:
                raise ApplicationError(ErrorCode.CONFLICT, "Session package is not active")
        if active is None:
            return EntitlementConsumption(
                consumed_minutes=0,
                active_entitlement_id=None,
                active_remaining_minutes=0,
            )
        while remaining_to_consume:
            active = await self._repository.get_active_for_client(client_id)
            if active is None:
                next_item = await self.next_compatible(client_id, zone_id, moment)
                if next_item is None:
                    break
                try:
                    active = await self._repository.activate_for_client(
                        next_item.id,
                        client_id,
                        moment,
                        zone_id,
                    )
                except ValueError as error:
                    raise ApplicationError(ErrorCode.CONFLICT, str(error)) from error
            if not active.is_compatible(zone_id) or not active.is_available_at(moment):
                break
            take = min(remaining_to_consume, active.remaining_minutes)
            if take <= 0:
                exhausted.append(active.id)
                continue
            try:
                updated = await self._repository.consume_for_client(
                    active.id,
                    client_id,
                    take,
                    moment,
                )
            except ValueError as error:
                raise ApplicationError(ErrorCode.CONFLICT, str(error)) from error
            consumed += take
            remaining_to_consume -= take
            if updated.status is EntitlementStatus.EXHAUSTED:
                exhausted.append(updated.id)
        active = await self._repository.get_active_for_client(client_id)
        return EntitlementConsumption(
            consumed_minutes=consumed,
            active_entitlement_id=active.id if active else None,
            active_remaining_minutes=active.remaining_minutes if active else 0,
            exhausted_entitlement_ids=tuple(exhausted),
        )
