import datetime

import httpx
import pytest

from gameclub_backend.application.errors import ApplicationError, ErrorCode
from gameclub_backend.config import Settings
from gameclub_backend.modules.billing.infrastructure.memory import InMemoryChargeRepository
from gameclub_backend.modules.catalog.application.service import CatalogService
from gameclub_backend.modules.catalog.infrastructure.memory import InMemoryCatalogRepository
from gameclub_backend.modules.clients.application.portal import ClientPortalService
from gameclub_backend.modules.clients.application.service import ClientService
from gameclub_backend.modules.clients.infrastructure.memory import InMemoryClientRepository
from gameclub_backend.modules.sales.application.service import ProductSaleService
from gameclub_backend.modules.sales.infrastructure.memory import InMemoryProductSaleRepository
from gameclub_backend.modules.sessions.infrastructure.memory import InMemorySessionRepository
from gameclub_backend.modules.workstations.application.service import WorkstationService
from gameclub_backend.modules.workstations.infrastructure.memory import (
    InMemoryWorkstationRepository,
)
from gameclub_backend.presentation.http.app import create_app


class ChargeHistoryReader:
    def __init__(self, repository: InMemoryChargeRepository) -> None:
        self._repository = repository

    async def list_charges_for_client(self, client_id, limit):
        return await self._repository.list_for_client(client_id, limit)


async def test_workstation_enrollment_normalizes_mac_and_binds_installation() -> None:
    repository = InMemoryWorkstationRepository()
    service = WorkstationService(repository)
    workstation = await service.register(
        None,
        "VIP-01",
        group_id="vip",
        mac_address="aa-bb-cc-dd-ee-ff",
    )

    assert workstation.device_id == "mac-aabbccddeeff"
    assert workstation.mac_address == "AA:BB:CC:DD:EE:FF"

    enrolled = await service.enroll_by_mac(["aabb.ccdd.eeff"], "installation-01")

    assert enrolled is not None
    assert enrolled.installation_id == "installation-01"

    with pytest.raises(ApplicationError) as error:
        await service.update(
            workstation.id,
            "VIP-01",
            None,
            None,
            mac_address="11:22:33:44:55:66",
        )
    assert error.value.code is ErrorCode.CONFLICT

    with pytest.raises(ApplicationError) as error:
        await service.enroll_by_mac(["AA:BB:CC:DD:EE:FF"], "another-installation")
    assert error.value.code is ErrorCode.PERMISSION_DENIED


async def test_device_enrollment_http_covers_pending_approved_and_disabled() -> None:
    application = create_app(Settings(jwt_secret="test-secret-with-at-least-32-bytes-long"))
    async with application.router.lifespan_context(application):
        transport = httpx.ASGITransport(app=application)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            pending = await client.post(
                "/api/v1/auth/device-enrollment",
                json={
                    "mac_addresses": ["AA-BB-CC-DD-EE-FF"],
                    "installation_id": "installation-01",
                },
            )
            workstation = await application.state.workstations.register(
                None,
                "VIP-01",
                mac_address="AA:BB:CC:DD:EE:FF",
            )
            approved = await client.post(
                "/api/v1/auth/device-enrollment",
                json={
                    "mac_addresses": ["aabb.ccdd.eeff"],
                    "installation_id": "installation-01",
                },
            )
            mismatch = await client.post(
                "/api/v1/auth/device-enrollment",
                json={
                    "mac_addresses": ["AA:BB:CC:DD:EE:FF"],
                    "installation_id": "another-installation",
                },
            )
            await application.state.workstations.disable(workstation.id, "test")
            disabled = await client.post(
                "/api/v1/auth/device-enrollment",
                json={
                    "mac_addresses": ["AA:BB:CC:DD:EE:FF"],
                    "installation_id": "installation-01",
                },
            )

    assert pending.status_code == 202
    assert pending.json() == {
        "state": "pending",
        "device_id": None,
        "workstation_id": None,
        "name": None,
        "group_id": None,
        "theme": None,
        "access_token": None,
        "expires_in": None,
    }
    assert approved.status_code == 200
    assert approved.json()["state"] == "approved"
    assert approved.json()["device_id"] == "mac-aabbccddeeff"
    assert approved.json()["access_token"]
    assert mismatch.status_code == 403
    assert disabled.status_code == 409
    assert disabled.json()["state"] == "disabled"


async def test_client_portal_is_scoped_and_reports_balance_time_and_purchases() -> None:
    client_service = ClientService(InMemoryClientRepository())
    catalog = CatalogService(InMemoryCatalogRepository())
    session_repository = InMemorySessionRepository()
    charge_repository = InMemoryChargeRepository()
    sales_repository = InMemoryProductSaleRepository()

    first = await client_service.register_portal("NightFox", "+7 999 123-45-67", "1234")
    second = await client_service.register_portal("DayFox", "+7 999 765-43-21", "5678")
    await client_service.top_up(
        first.id,
        5_000,
        0,
        "Пополнение",
        "operator",
        "portal-top-up-1",
    )
    await catalog.create_tariff(
        "Поминутный тариф",
        None,
        60,
        6_000,
        datetime.datetime.now(datetime.UTC) - datetime.timedelta(minutes=1),
        None,
        billing_mode="per_minute",
        price_per_minute_cents=100,
    )
    product = await catalog.create_product("Кофе", "drinks", 300, stock_quantity=5)

    sales = ProductSaleService(
        sales_repository,
        products=catalog,
        clients=client_service,
    )
    await sales.sell(
        product.id,
        1,
        first.id,
        "balance",
        None,
        "operator",
        "portal-sale-1",
    )
    portal = ClientPortalService(
        client_service,
        session_repository,
        ChargeHistoryReader(charge_repository),
        sales,
        catalog,
    )

    authenticated = await portal.authenticate("79991234567", "1234")
    snapshot = await portal.snapshot(authenticated.id)

    assert authenticated.id == first.id
    assert authenticated.id != second.id
    assert snapshot.client.id == first.id
    assert snapshot.client.balance_cents == 4_700
    assert snapshot.available_time_minutes == 47
    assert [sale.product_name for sale in snapshot.purchases] == ["Кофе"]
    assert all(operation.client_id == first.id for operation in snapshot.balance_operations)

    with pytest.raises(ApplicationError) as error:
        await portal.authenticate("NightFox", "9999")
    assert error.value.code is ErrorCode.UNAUTHENTICATED

    await client_service.delete(first.id)
    with pytest.raises(ApplicationError) as error:
        await portal.snapshot(first.id)
    assert error.value.code is ErrorCode.UNAUTHENTICATED
