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
from gameclub_backend.modules.sales.domain import ProductSale
from gameclub_backend.modules.sessions.domain import Session


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


@dataclasses.dataclass(frozen=True)
class ClientPortalSnapshot:
    client: Client
    balance_operations: tuple[BalanceOperation, ...]
    sessions: tuple[Session, ...]
    charges: tuple[SessionCharge, ...]
    purchases: tuple[ProductSale, ...]
    available_time_minutes: int
    tariff_names: dict[uuid.UUID, str] = dataclasses.field(default_factory=dict)


class ClientPortalService:
    def __init__(
        self,
        clients: ClientService,
        sessions: SessionHistoryReader,
        charges: ChargeHistoryReader,
        sales: ProductHistoryReader,
        tariffs: TariffReader,
    ) -> None:
        self._clients = clients
        self._sessions = sessions
        self._charges = charges
        self._sales = sales
        self._tariffs = tariffs

    async def register(self, nickname: str, phone: str, pin: str) -> Client:
        return await self._clients.register_portal(nickname, phone, pin)

    async def authenticate(self, identifier: str, pin: str) -> Client:
        return await self._clients.authenticate_portal(identifier, pin)

    async def snapshot(self, client_id: uuid.UUID, limit: int = 50) -> ClientPortalSnapshot:
        client = await self._clients.get(client_id)
        if client.blocked_at is not None:
            raise ApplicationError(ErrorCode.UNAUTHENTICATED, "Invalid client credentials")
        operations = await self._clients.list_operations(client_id, limit)
        sessions = await self._sessions.list_for_client(client_id, limit)
        charges = await self._charges.list_charges_for_client(client_id, limit)
        purchases = await self._sales.list_sales(client_id=client_id, limit=limit)
        tariffs = await self._tariffs.list_tariffs()
        return ClientPortalSnapshot(
            client=client,
            balance_operations=tuple(operations),
            sessions=tuple(sessions),
            charges=tuple(charges),
            purchases=tuple(purchases),
            available_time_minutes=self._available_time_minutes(client.balance_cents, tariffs),
            tariff_names={tariff.id: tariff.name for tariff in tariffs},
        )

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
