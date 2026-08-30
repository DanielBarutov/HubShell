import asyncio
import datetime

import httpx
import pytest

from gameclub_backend.config import Settings
from gameclub_backend.modules.analytics.application.service import AnalyticsService
from gameclub_backend.modules.analytics.infrastructure.memory import InMemoryAnalyticsRepository
from gameclub_backend.modules.cash_shifts.application.service import CashShiftService
from gameclub_backend.modules.cash_shifts.infrastructure.memory import InMemoryCashShiftRepository
from gameclub_backend.modules.catalog.application.service import CatalogService
from gameclub_backend.modules.catalog.infrastructure.memory import InMemoryCatalogRepository
from gameclub_backend.modules.clients.application.service import ClientService
from gameclub_backend.modules.clients.infrastructure.memory import InMemoryClientRepository
from gameclub_backend.modules.sales.application.service import ProductSaleService
from gameclub_backend.modules.sales.infrastructure.cash import CashShiftSaleSettlement
from gameclub_backend.modules.sales.infrastructure.memory import InMemoryProductSaleRepository
from gameclub_backend.presentation.http.app import create_app


async def test_product_sale_debits_client_once_and_is_idempotent() -> None:
    catalog = CatalogService(InMemoryCatalogRepository())
    product = await catalog.create_product("Coffee", "drinks", 250, stock_quantity=5)
    clients = ClientService(InMemoryClientRepository())
    client = await clients.create("SaleClient")
    await clients.top_up(client.id, 1_000, 0, "Deposit", "operator", "deposit-sale-test")
    service = ProductSaleService(InMemoryProductSaleRepository(), catalog, clients)

    sale = await service.sell(
        product.id,
        quantity=2,
        client_id=client.id,
        payment_method="balance",
        cash_shift_id=None,
        sold_by="operator",
        idempotency_key="sale-001",
    )
    repeated = await service.sell(
        product.id,
        quantity=2,
        client_id=client.id,
        payment_method="balance",
        cash_shift_id=None,
        sold_by="operator",
        idempotency_key="sale-001",
    )

    assert sale.status.value == "completed"
    assert repeated.id == sale.id
    assert (await clients.get(client.id)).balance_cents == 500
    assert len(await clients.list_operations(client.id)) == 2


async def test_concurrent_product_sale_requests_settle_once() -> None:
    catalog = CatalogService(InMemoryCatalogRepository())
    product = await catalog.create_product("Snack", "food", 300, stock_quantity=2)
    clients = ClientService(InMemoryClientRepository())
    client = await clients.create("ConcurrentSaleClient")
    await clients.top_up(client.id, 1_000, 0, "Deposit", "operator", "deposit-concurrent-sale")
    service = ProductSaleService(InMemoryProductSaleRepository(), catalog, clients)

    results = await asyncio.gather(
        *(
            service.sell(
                product.id,
                quantity=1,
                client_id=client.id,
                payment_method="balance",
                cash_shift_id=None,
                sold_by="operator",
                idempotency_key="sale-concurrent-001",
            )
            for _ in range(2)
        )
    )

    assert {result.id for result in results} == {results[0].id}
    assert (await clients.get(client.id)).balance_cents == 700
    assert len(await clients.list_operations(client.id)) == 2


async def test_guest_product_sale_is_settled_in_cash_shift() -> None:
    catalog = CatalogService(InMemoryCatalogRepository())
    product = await catalog.create_product("Water", "drinks", 100, stock_quantity=3)
    cash_shifts = CashShiftService(InMemoryCashShiftRepository())
    shift = await cash_shifts.open("front-desk", 0, "operator", "cash-open-sale-test")
    service = ProductSaleService(
        InMemoryProductSaleRepository(),
        catalog,
        ClientService(InMemoryClientRepository()),
        cash=CashShiftSaleSettlement(cash_shifts),
    )

    sale = await service.sell(
        product.id,
        quantity=1,
        client_id=None,
        payment_method="cash",
        cash_shift_id=shift.id,
        sold_by="operator",
        idempotency_key="sale-cash-001",
    )

    assert sale.guest_name == "Гость"
    assert (await cash_shifts.get(shift.id)).expected_close_cents == 100


async def test_analytics_service_rejects_naive_period() -> None:
    service = AnalyticsService(InMemoryAnalyticsRepository())
    with pytest.raises(Exception, match="aware"):
        await service.overview(
            datetime.datetime(2026, 8, 28),
            datetime.datetime(2026, 8, 29, tzinfo=datetime.UTC),
        )


async def test_sales_and_analytics_routes_are_available_to_operator() -> None:
    application = create_app(
        Settings(
            jwt_secret="test-secret-with-at-least-32-bytes-long",
            dev_operator_username="operator",
            dev_operator_password="password",
        )
    )
    async with application.router.lifespan_context(application):
        transport = httpx.ASGITransport(app=application)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            token = await client.post(
                "/api/v1/auth/token",
                json={"username": "operator", "password": "password"},
            )
            headers = {"Authorization": f"Bearer {token.json()['access_token']}"}
            product = await client.post(
                "/api/v1/catalog/products",
                headers=headers,
                json={
                    "name": "Juice",
                    "category": "drinks",
                    "price_cents": 180,
                    "stock_quantity": 2,
                },
            )
            customer = await client.post(
                "/api/v1/clients",
                headers=headers,
                json={"nickname": "ApiSaleClient"},
            )
            client_id = customer.json()["id"]
            await client.post(
                f"/api/v1/clients/{client_id}/top-up",
                headers={**headers, "Idempotency-Key": "api-sale-deposit"},
                json={"amount_cents": 500, "bonus_amount": 0, "reason": "Sale test"},
            )
            sale = await client.post(
                "/api/v1/sales",
                headers={**headers, "Idempotency-Key": "api-sale-001"},
                json={
                    "product_id": product.json()["id"],
                    "quantity": 1,
                    "client_id": client_id,
                    "payment_method": "balance",
                },
            )
            overview = await client.get(
                "/api/v1/analytics/overview",
                headers=headers,
                params={
                    "start_at": "2026-08-27T00:00:00Z",
                    "end_at": "2026-08-29T00:00:00Z",
                },
            )
            export = await client.get(
                "/api/v1/analytics/overview.csv",
                headers=headers,
                params={
                    "start_at": "2026-08-27T00:00:00Z",
                    "end_at": "2026-08-29T00:00:00Z",
                },
            )

    assert sale.status_code == 201
    assert sale.json()["guest_name"] is None
    assert overview.status_code == 200
    assert overview.json()["total_revenue_cents"] == 0
    assert export.status_code == 200
    assert "section,key,label" in export.text
    assert "overview,period" in export.text
    assert "attachment" in export.headers["content-disposition"]
