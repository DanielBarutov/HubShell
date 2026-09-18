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
from gameclub_backend.modules.entitlements.application.service import EntitlementService
from gameclub_backend.modules.entitlements.domain import EntitlementStatus
from gameclub_backend.modules.entitlements.infrastructure.memory import (
    InMemoryEntitlementRepository,
)
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


class FixedClock:
    def __init__(self) -> None:
        self.current = datetime.datetime(2026, 9, 18, 12, tzinfo=datetime.UTC)

    def now(self) -> datetime.datetime:
        return self.current


async def test_workstation_enrollment_normalizes_mac_and_binds_installation() -> None:
    """
    Проверяет сценарий «test_workstation_enrollment_normalizes_mac_and_binds_installation» и
    подтверждает ожидаемый публичный результат согласно соответствующему бизнес-правилу.
    """
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
    """
    Проверяет сценарий «test_device_enrollment_http_covers_pending_approved_and_disabled» и
    подтверждает ожидаемый публичный результат согласно соответствующему бизнес-правилу.
    """
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
    """
    Проверяет сценарий «test_client_portal_is_scoped_and_reports_balance_time_and_purchases» и
    подтверждает ожидаемый публичный результат согласно соответствующему бизнес-правилу.
    """
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


async def test_portal_activates_first_usable_package_when_night_package_is_queued() -> None:
    """
    Проверяет, что ночной пакет вне окна не блокирует запуск следующего доступного пакета.
    """
    clock = FixedClock()
    clients = ClientService(InMemoryClientRepository(), clock=clock)
    catalog = CatalogService(InMemoryCatalogRepository())
    workstations = InMemoryWorkstationRepository()
    await WorkstationService(workstations).register("portal-vip", "VIP-01", group_id="vip")
    entitlements = EntitlementService(
        InMemoryEntitlementRepository(),
        tariffs=catalog,
        clients=clients,
        workstations=workstations,
        clock=clock,
    )
    sales = ProductSaleService(
        InMemoryProductSaleRepository(),
        products=catalog,
        clients=clients,
    )
    portal = ClientPortalService(
        clients,
        InMemorySessionRepository(),
        ChargeHistoryReader(InMemoryChargeRepository()),
        sales,
        catalog,
        entitlements=entitlements,
        workstations=workstations,
        clock=clock,
    )
    client = await clients.register_portal("NightFox", "+7 999 123-45-67", "1234")
    await clients.top_up(client.id, 1_000, 0, "Пополнение", "operator", "night-top-up")
    night = await catalog.create_tariff(
        "Ночной пакет",
        "vip",
        660,
        300,
        clock.current,
        None,
        time_restricted=True,
        sale_window_start_minute=0,
        sale_window_end_minute=1439,
        usage_window_start_minute=22 * 60,
        usage_window_end_minute=8 * 60,
        window_timezone="Europe/Moscow",
    )
    normal = await catalog.create_tariff("Обычный пакет", "vip", 3, 50, clock.current, None)
    waiting = await entitlements.purchase(client.id, night.id, "operator", "night-package")
    available = await entitlements.purchase(client.id, normal.id, "operator", "normal-package")

    snapshot = await portal.activate_entitlement(client.id, waiting.id, "portal-vip")

    waiting_snapshot = next(item for item in snapshot.entitlements if item.id == waiting.id)
    available_snapshot = next(item for item in snapshot.entitlements if item.id == available.id)
    assert waiting_snapshot.status is EntitlementStatus.QUEUED
    assert available_snapshot.status is EntitlementStatus.ACTIVE

async def test_password_reset_allows_one_passwordless_login_until_new_password_is_set() -> None:
    """
    Проверяет сценарий
    «test_password_reset_allows_one_passwordless_login_until_new_password_is_set» и подтверждает
    ожидаемый публичный результат согласно соответствующему бизнес-правилу.
    """
    clients = ClientService(InMemoryClientRepository())
    client = await clients.register_portal("ResetFox", "+7 999 111-22-33", "old-pass")

    await clients.reset_password(client.id)
    reset_client = await clients.get(client.id)
    assert reset_client.password_hash is None
    assert reset_client.password_reset_required is True

    passwordless = await clients.authenticate_portal("ResetFox", "")
    assert passwordless.password_reset_required is True

    with pytest.raises(ApplicationError) as error:
        await clients.authenticate_portal("ResetFox", "")
    assert error.value.code is ErrorCode.UNAUTHENTICATED

    with pytest.raises(ApplicationError) as error:
        await clients.authenticate_portal("ResetFox", "old-pass")
    assert error.value.code is ErrorCode.UNAUTHENTICATED

    await clients.set_portal_password(client.id, "new-pass")
    updated = await clients.authenticate_portal("ResetFox", "new-pass")
    assert updated.password_reset_required is False

    with pytest.raises(ApplicationError) as error:
        await clients.authenticate_portal("ResetFox", "")
    assert error.value.code is ErrorCode.INVALID_ARGUMENT
