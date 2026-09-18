from __future__ import annotations

import dataclasses
import datetime
import typing
import uuid

from gameclub_backend.application.errors import ApplicationError, ErrorCode
from gameclub_backend.modules.billing.domain import SessionCharge
from gameclub_backend.modules.catalog.domain import (
    BillingMode,
    Tariff,
    TariffAudience,
    TariffLifecycle,
    TariffSaleChannel,
)
from gameclub_backend.modules.clients.application.service import ClientService
from gameclub_backend.modules.clients.domain import BalanceOperation, Client
from gameclub_backend.modules.entitlements.domain import Entitlement
from gameclub_backend.modules.payment_methods.domain import PaymentMethod
from gameclub_backend.modules.reservations.domain import Reservation, ReservationStatus
from gameclub_backend.modules.sales.domain import ProductSale
from gameclub_backend.modules.sessions.domain import Session
from gameclub_backend.modules.workstations.domain import (
    Workstation,
    effective_workstation_group_id,
)


class SessionHistoryReader(typing.Protocol):
    async def list_for_client(self, client_id: uuid.UUID, limit: int) -> list[Session]:
        """Return recent sessions for one client."""

    async def list(
        self,
        workstation_id: uuid.UUID | None = None,
        active_only: bool = False,
    ) -> list[Session]:
        """Return sessions for a workstation or operator display."""


class ChargeHistoryReader(typing.Protocol):
    async def list_charges_for_client(
        self,
        client_id: uuid.UUID,
        limit: int,
    ) -> list[SessionCharge]:
        """Return recent billing charges for one client."""


class ProductHistoryReader(typing.Protocol):
    async def list_sales(
        self,
        start_at: datetime.datetime | None = None,
        end_at: datetime.datetime | None = None,
        client_id: uuid.UUID | None = None,
        limit: int = 100,
    ) -> list[ProductSale]:
        """Return completed sales for one client."""


class TariffReader(typing.Protocol):
    async def list_tariffs(self) -> list[Tariff]:
        """Return current tariff versions."""

    async def get_tariff(self, tariff_id: uuid.UUID) -> Tariff | None:
        """Return one tariff version."""


class EntitlementReader(typing.Protocol):
    async def get(self, entitlement_id: uuid.UUID) -> Entitlement:
        """Return one package entitlement."""

    async def list_for_client(self, client_id: uuid.UUID) -> list[Entitlement]:
        """Return the ordered package queue for one client."""

    async def activate(self, entitlement_id: uuid.UUID, client_id: uuid.UUID) -> Entitlement:
        """Activate one package after an explicit client action."""

    async def next_compatible(
        self,
        client_id: uuid.UUID,
        zone_id: str | None,
        now: datetime.datetime | None = None,
    ) -> Entitlement | None:
        """Return the first queued package that can be consumed now."""

    async def purchase(
        self,
        client_id: uuid.UUID,
        tariff_id: uuid.UUID,
        actor_id: str,
        idempotency_key: str,
    ) -> Entitlement:
        """Purchase one tariff package for the client."""


class WorkstationReader(typing.Protocol):
    async def get(self, workstation_id: uuid.UUID) -> Workstation | None:
        """Return a workstation by its persistent identifier."""

    async def get_by_device_id(self, device_id: str) -> Workstation | None:
        """Return the workstation assigned to a device identity."""


class PaymentMethodReader(typing.Protocol):
    async def list(self) -> list[PaymentMethod]:
        """Return payment methods with their customer-facing names."""


class ReservationReader(typing.Protocol):
    async def list_for_client(
        self,
        client_id: uuid.UUID,
        start_at: datetime.datetime,
        limit: int,
    ) -> list[Reservation]:
        """Return future confirmed reservations for one client."""


class UtcClock:
    def now(self) -> datetime.datetime:
        return datetime.datetime.now(datetime.UTC)


@dataclasses.dataclass(frozen=True)
class ClientPortalSnapshot:
    client: Client
    balance_operations: tuple[BalanceOperation, ...]
    sessions: tuple[Session, ...]
    charges: tuple[SessionCharge, ...]
    purchases: tuple[ProductSale, ...]
    available_time_minutes: int
    tariff_names: dict[uuid.UUID, str] = dataclasses.field(default_factory=dict)
    workstation_names: dict[uuid.UUID, str] = dataclasses.field(default_factory=dict)
    session_duration_minutes: dict[uuid.UUID, int] = dataclasses.field(default_factory=dict)
    payment_method_names: dict[str, str] = dataclasses.field(default_factory=dict)
    entitlements: tuple[Entitlement, ...] = ()
    tariffs: tuple[Tariff, ...] = ()
    reservations: tuple[Reservation, ...] = ()


class ClientPortalService:
    def __init__(
        self,
        clients: ClientService,
        sessions: SessionHistoryReader,
        charges: ChargeHistoryReader,
        sales: ProductHistoryReader,
        tariffs: TariffReader,
        entitlements: EntitlementReader | None = None,
        workstations: WorkstationReader | None = None,
        payment_methods: PaymentMethodReader | None = None,
        reservations: ReservationReader | None = None,
        clock: UtcClock | None = None,
    ) -> None:
        self._clients = clients
        self._sessions = sessions
        self._charges = charges
        self._sales = sales
        self._tariffs = tariffs
        self._entitlements = entitlements
        self._workstations = workstations
        self._payment_methods = payment_methods
        self._reservations = reservations
        self._clock = clock or UtcClock()

    async def register(self, nickname: str, phone: str, password: str) -> Client:
        return await self._clients.register_portal(nickname, phone, password)

    async def authenticate(self, identifier: str, password: str) -> Client:
        return await self._clients.authenticate_portal(identifier, password)

    async def set_password(self, client_id: uuid.UUID, password: str) -> Client:
        return await self._clients.set_portal_password(client_id, password)

    async def snapshot(
        self,
        client_id: uuid.UUID,
        limit: int = 50,
        group_id: str | None = None,
    ) -> ClientPortalSnapshot:
        client = await self._clients.get(client_id)
        if client.blocked_at is not None:
            raise ApplicationError(ErrorCode.UNAUTHENTICATED, "Invalid client credentials")
        operations = await self._clients.list_operations(client_id, limit)
        sessions = await self._sessions.list_for_client(client_id, limit)
        charges = await self._charges.list_charges_for_client(client_id, limit)
        purchases = await self._sales.list_sales(client_id=client_id, limit=limit)
        tariffs = await self._tariffs.list_tariffs()
        payment_methods = (
            await self._payment_methods.list() if self._payment_methods is not None else []
        )
        package_queue = (
            await self._entitlements.list_for_client(client_id)
            if self._entitlements is not None
            else []
        )
        normalized_group_id = group_id.strip().lower() if group_id else None
        now = self._clock.now()
        available_tariffs = tuple(
            tariff
            for tariff in tariffs
            if tariff.active
            and tariff.lifecycle is TariffLifecycle.PUBLISHED
            and tariff.billing_mode is BillingMode.BLOCK
            and (
                normalized_group_id is None
                or tariff.group_id is None
                or tariff.group_id.strip().lower() == normalized_group_id
            )
            and tariff.is_visible_to(now, TariffAudience.REGISTERED)
            and tariff.is_sellable_through(TariffSaleChannel.SELF_SERVICE)
        )
        upcoming_reservations = (
            await self._reservations.list_for_client(
                client_id,
                datetime.datetime.now(datetime.UTC),
                max(1, min(limit, 100)),
            )
            if self._reservations is not None
            else []
        )
        return ClientPortalSnapshot(
            client=client,
            balance_operations=tuple(operations),
            sessions=tuple(sessions),
            charges=tuple(charges),
            purchases=tuple(purchases),
            available_time_minutes=self._available_time_minutes(
                client.balance_cents,
                tariffs,
                group_id,
            ),
            tariff_names={tariff.id: tariff.name for tariff in tariffs},
            workstation_names=await self._workstation_names(sessions),
            session_duration_minutes={
                session.id: self._elapsed_minutes(session.started_at, session.ended_at)
                for session in sessions
            },
            payment_method_names={method.key: method.name for method in payment_methods},
            entitlements=tuple(package_queue[: max(1, min(limit, 100))]),
            tariffs=available_tariffs,
            reservations=tuple(
                item for item in upcoming_reservations if item.status is ReservationStatus.CONFIRMED
            ),
        )

    async def snapshot_for_device(
        self,
        client_id: uuid.UUID,
        device_id: str,
        limit: int = 50,
    ) -> ClientPortalSnapshot:
        if self._workstations is None:
            return await self.snapshot(client_id, limit)
        workstation = await self._workstation_for_device(device_id)
        return await self.snapshot(
            client_id,
            limit,
            group_id=effective_workstation_group_id(workstation.group_id),
        )

    async def resume_for_device(
        self,
        device_id: str,
        limit: int = 50,
    ) -> ClientPortalSnapshot | None:
        workstation = await self._workstation_for_device(device_id)
        active_sessions = await self._sessions.list(
            workstation_id=workstation.id,
            active_only=True,
        )
        active_client_id = next(
            (session.client_id for session in active_sessions if session.client_id is not None),
            None,
        )
        if active_client_id is None:
            return None
        return await self.snapshot(
            active_client_id,
            limit,
            group_id=effective_workstation_group_id(workstation.group_id),
        )

    async def _workstation_names(self, sessions: list[Session]) -> dict[uuid.UUID, str]:
        if self._workstations is None:
            return {}
        names: dict[uuid.UUID, str] = {}
        for workstation_id in {session.workstation_id for session in sessions}:
            workstation = await self._workstations.get(workstation_id)
            if workstation is not None:
                names[workstation_id] = workstation.name
        return names

    @staticmethod
    def _elapsed_minutes(
        started_at: datetime.datetime,
        ended_at: datetime.datetime | None,
    ) -> int:
        finish = ended_at or datetime.datetime.now(datetime.UTC)
        if finish <= started_at:
            return 0
        return max(1, int((finish - started_at).total_seconds() // 60))

    async def purchase_entitlement(
        self,
        client_id: uuid.UUID,
        tariff_id: uuid.UUID,
        idempotency_key: str,
        device_id: str | None = None,
    ) -> ClientPortalSnapshot:
        if self._entitlements is None:
            raise ApplicationError(
                ErrorCode.DEPENDENCY_UNAVAILABLE,
                "Entitlement service is not configured",
            )
        group_id = None
        if device_id is not None and self._workstations is not None:
            group_id = effective_workstation_group_id(
                (await self._workstation_for_device(device_id)).group_id
            )
            tariff = await self._tariffs.get_tariff(tariff_id)
            if tariff is None:
                raise ApplicationError(ErrorCode.NOT_FOUND, "Tariff not found")
            if (
                tariff.group_id is not None
                and tariff.group_id.strip().lower() != (group_id or "").strip().lower()
            ):
                raise ApplicationError(
                    ErrorCode.CONFLICT,
                    "Tariff is incompatible with this workstation zone",
                )
        await self._entitlements.purchase(
            client_id=client_id,
            tariff_id=tariff_id,
            actor_id=f"client:{client_id}",
            idempotency_key=idempotency_key,
        )
        return await self.snapshot(client_id, group_id=group_id)

    async def activate_entitlement(
        self,
        client_id: uuid.UUID,
        entitlement_id: uuid.UUID,
        device_id: str | None = None,
    ) -> ClientPortalSnapshot:
        if self._entitlements is None:
            raise ApplicationError(
                ErrorCode.DEPENDENCY_UNAVAILABLE,
                "Entitlement service is not configured",
            )
        if self._workstations is not None:
            workstation = (
                await self._workstations.get_by_device_id(device_id) if device_id else None
            )
            if workstation is None:
                raise ApplicationError(ErrorCode.PERMISSION_DENIED, "Device is not assigned")
            entitlement = await self._entitlements.get(entitlement_id)
            group_id = effective_workstation_group_id(workstation.group_id)
            now = self._clock.now()
            if not entitlement.is_compatible(group_id) or not entitlement.is_available_at(now):
                next_item = await self._entitlements.next_compatible(
                    client_id,
                    group_id,
                    now,
                )
                if next_item is None:
                    raise ApplicationError(
                        ErrorCode.CONFLICT,
                        "No queued package is available for this workstation now",
                    )
                entitlement_id = next_item.id
        await self._entitlements.activate(entitlement_id, client_id)
        if device_id is not None:
            return await self.snapshot_for_device(client_id, device_id)
        return await self.snapshot(client_id)

    async def _workstation_for_device(self, device_id: str) -> Workstation:
        if self._workstations is None:
            raise ApplicationError(
                ErrorCode.DEPENDENCY_UNAVAILABLE,
                "Workstation lookup is not configured",
            )
        workstation = await self._workstations.get_by_device_id(device_id.strip())
        if workstation is None:
            raise ApplicationError(ErrorCode.PERMISSION_DENIED, "Device is not assigned")
        return workstation

    @staticmethod
    def _available_time_minutes(
        balance_cents: int,
        tariffs: list[Tariff],
        group_id: str | None,
    ) -> int:
        available = 0
        normalized_group_id = group_id.strip().lower() if group_id else None
        for tariff in tariffs:
            if not tariff.active or tariff.lifecycle is not TariffLifecycle.PUBLISHED:
                continue
            if (
                normalized_group_id is not None
                and tariff.group_id is not None
                and tariff.group_id.strip().lower() != normalized_group_id
            ):
                continue
            if tariff.billing_mode is BillingMode.PER_MINUTE:
                if tariff.price_per_minute_cents > 0:
                    available = max(available, balance_cents // tariff.price_per_minute_cents)
            elif tariff.price_cents > 0 and tariff.duration_minutes > 0:
                available = max(
                    available,
                    (balance_cents // tariff.price_cents) * tariff.duration_minutes,
                )
        return available
