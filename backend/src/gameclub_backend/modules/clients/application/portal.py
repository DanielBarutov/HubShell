from __future__ import annotations

import dataclasses
import datetime
import typing
import uuid

from gameclub_backend.application.errors import ApplicationError, ErrorCode
from gameclub_backend.modules.billing.domain import SessionCharge
from gameclub_backend.modules.catalog.domain import BillingMode, Tariff, TariffLifecycle
from gameclub_backend.modules.clients.application.service import ClientService
from gameclub_backend.modules.clients.domain import BalanceOperation, Client
from gameclub_backend.modules.entitlements.domain import Entitlement
from gameclub_backend.modules.reservations.domain import Reservation, ReservationStatus
from gameclub_backend.modules.sales.domain import ProductSale
from gameclub_backend.modules.sessions.domain import Session
from gameclub_backend.modules.workstations.domain import Workstation


class SessionHistoryReader(typing.Protocol):
    async def list_for_client(self, client_id: uuid.UUID, limit: int) -> list[Session]:
        """Return recent sessions for one client."""


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


class EntitlementReader(typing.Protocol):
    async def get(self, entitlement_id: uuid.UUID) -> Entitlement:
        """Return one package entitlement."""

    async def list_for_client(self, client_id: uuid.UUID) -> list[Entitlement]:
        """Return the ordered package queue for one client."""

    async def activate(self, entitlement_id: uuid.UUID, client_id: uuid.UUID) -> Entitlement:
        """Activate one package after an explicit client action."""

    async def purchase(
        self,
        client_id: uuid.UUID,
        tariff_id: uuid.UUID,
        actor_id: str,
        idempotency_key: str,
    ) -> Entitlement:
        """Purchase one tariff package for the client."""


class WorkstationReader(typing.Protocol):
    async def get_by_device_id(self, device_id: str) -> Workstation | None:
        """Return the workstation assigned to a device identity."""


class ReservationReader(typing.Protocol):
    async def list_for_client(
        self,
        client_id: uuid.UUID,
        start_at: datetime.datetime,
        limit: int,
    ) -> list[Reservation]:
        """Return future confirmed reservations for one client."""


@dataclasses.dataclass(frozen=True)
class ClientPortalSnapshot:
    client: Client
    balance_operations: tuple[BalanceOperation, ...]
    sessions: tuple[Session, ...]
    charges: tuple[SessionCharge, ...]
    purchases: tuple[ProductSale, ...]
    available_time_minutes: int
    tariff_names: dict[uuid.UUID, str] = dataclasses.field(default_factory=dict)
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
        reservations: ReservationReader | None = None,
    ) -> None:
        self._clients = clients
        self._sessions = sessions
        self._charges = charges
        self._sales = sales
        self._tariffs = tariffs
        self._entitlements = entitlements
        self._workstations = workstations
        self._reservations = reservations

    async def register(self, nickname: str, phone: str, password: str) -> Client:
        return await self._clients.register_portal(nickname, phone, password)

    async def authenticate(self, identifier: str, password: str) -> Client:
        return await self._clients.authenticate_portal(identifier, password)

    async def snapshot(self, client_id: uuid.UUID, limit: int = 50) -> ClientPortalSnapshot:
        client = await self._clients.get(client_id)
        if client.blocked_at is not None:
            raise ApplicationError(ErrorCode.UNAUTHENTICATED, "Invalid client credentials")
        operations = await self._clients.list_operations(client_id, limit)
        sessions = await self._sessions.list_for_client(client_id, limit)
        charges = await self._charges.list_charges_for_client(client_id, limit)
        purchases = await self._sales.list_sales(client_id=client_id, limit=limit)
        tariffs = await self._tariffs.list_tariffs()
        package_queue = (
            await self._entitlements.list_for_client(client_id)
            if self._entitlements is not None
            else []
        )
        available_tariffs = tuple(
            tariff
            for tariff in tariffs
            if tariff.active and tariff.lifecycle is TariffLifecycle.PUBLISHED
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
            available_time_minutes=self._available_time_minutes(client.balance_cents, tariffs),
            tariff_names={tariff.id: tariff.name for tariff in tariffs},
            entitlements=tuple(package_queue[: max(1, min(limit, 100))]),
            tariffs=available_tariffs,
            reservations=tuple(
                item for item in upcoming_reservations if item.status is ReservationStatus.CONFIRMED
            ),
        )

    async def purchase_entitlement(
        self,
        client_id: uuid.UUID,
        tariff_id: uuid.UUID,
        idempotency_key: str,
    ) -> ClientPortalSnapshot:
        if self._entitlements is None:
            raise ApplicationError(
                ErrorCode.DEPENDENCY_UNAVAILABLE,
                "Entitlement service is not configured",
            )
        await self._entitlements.purchase(
            client_id=client_id,
            tariff_id=tariff_id,
            actor_id=f"client:{client_id}",
            idempotency_key=idempotency_key,
        )
        return await self.snapshot(client_id)

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
            if not entitlement.is_compatible(workstation.group_id):
                raise ApplicationError(
                    ErrorCode.CONFLICT,
                    "Package is incompatible with this workstation zone",
                )
        await self._entitlements.activate(entitlement_id, client_id)
        return await self.snapshot(client_id)

    @staticmethod
    def _available_time_minutes(balance_cents: int, tariffs: list[Tariff]) -> int:
        available = 0
        for tariff in tariffs:
            if not tariff.active or tariff.lifecycle is not TariffLifecycle.PUBLISHED:
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
