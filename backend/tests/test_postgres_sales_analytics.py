import asyncio
import os
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from gameclub_backend.application.errors import ApplicationError, ErrorCode
from gameclub_backend.modules.catalog.application.service import CatalogService
from gameclub_backend.modules.catalog.infrastructure.postgres import PostgresCatalogRepository
from gameclub_backend.modules.clients.application.service import ClientService
from gameclub_backend.modules.clients.infrastructure.postgres import PostgresClientRepository
from gameclub_backend.modules.sales.application.service import ProductSaleService
from gameclub_backend.modules.sales.infrastructure.postgres import PostgresProductSaleRepository


@pytest.fixture
def postgres_dsn() -> str:
    dsn = os.getenv("GAMECLUB_TEST_POSTGRES_DSN")
    if not dsn:
        pytest.skip("Set GAMECLUB_TEST_POSTGRES_DSN to run PostgreSQL integration tests")
    return dsn


async def test_postgres_product_sale_reserves_stock_and_debits_once(postgres_dsn: str) -> None:
    engine = create_async_engine(postgres_dsn, pool_pre_ping=True)
    product_id: uuid.UUID | None = None
    client_id: uuid.UUID | None = None
    try:
        catalog = CatalogService(PostgresCatalogRepository(lambda: engine))
        product = await catalog.create_product(
            f"PgSaleProduct{uuid.uuid4().hex[:8]}",
            "integration",
            300,
            cost_price_cents=120,
            stock_quantity=2,
        )
        product_id = product.id
        clients = ClientService(PostgresClientRepository(lambda: engine))
        client = await clients.create(f"PgSaleClient{uuid.uuid4().hex[:8]}")
        client_id = client.id
        await clients.top_up(
            client.id,
            1_000,
            0,
            "Product sale integration test",
            "integration-test",
            f"pg-sale-deposit-{uuid.uuid4()}",
        )
        sales = PostgresProductSaleRepository(lambda: engine)
        service = ProductSaleService(sales, catalog, clients)

        results = await asyncio.gather(
            *(
                service.sell(
                    product.id,
                    quantity=1,
                    client_id=client.id,
                    payment_method="balance",
                    cash_shift_id=None,
                    sold_by="integration-test",
                    idempotency_key="pg-sale-concurrent-001",
                )
                for _ in range(2)
            )
        )

        final_sale = await sales.get_by_idempotency_key("pg-sale-concurrent-001")
        final_product = await catalog.get_product(product.id)
        final_client = await clients.get(client.id)

        assert final_sale is not None
        assert final_product is not None
        assert {result.id for result in results} == {final_sale.id}
        assert final_sale.status.value == "completed"
        assert final_product.stock_quantity == 1
        assert final_client.balance_cents == 700
    finally:
        async with engine.begin() as connection:
            if product_id is not None:
                await connection.execute(
                    text("DELETE FROM product_sales WHERE product_id = :product_id"),
                    {"product_id": product_id},
                )
                await connection.execute(
                    text("DELETE FROM products WHERE id = :product_id"),
                    {"product_id": product_id},
                )
            if client_id is not None:
                await connection.execute(
                    text("DELETE FROM balance_operations WHERE client_id = :client_id"),
                    {"client_id": client_id},
                )
                await connection.execute(
                    text("DELETE FROM clients WHERE id = :client_id"),
                    {"client_id": client_id},
                )
        await engine.dispose()


@pytest.mark.asyncio
async def test_postgres_concurrent_sale_key_with_different_payload_is_conflict(
    postgres_dsn: str,
) -> None:
    engine = create_async_engine(postgres_dsn, pool_pre_ping=True)
    product_id: uuid.UUID | None = None
    client_id: uuid.UUID | None = None
    try:
        catalog = CatalogService(PostgresCatalogRepository(lambda: engine))
        product = await catalog.create_product(
            f"PgConflictProduct{uuid.uuid4().hex[:8]}",
            "integration",
            300,
            cost_price_cents=120,
            stock_quantity=3,
        )
        product_id = product.id
        clients = ClientService(PostgresClientRepository(lambda: engine))
        client = await clients.create(f"PgConflictClient{uuid.uuid4().hex[:8]}")
        client_id = client.id
        await clients.top_up(
            client.id,
            1_000,
            0,
            "Product sale conflict integration test",
            "integration-test",
            f"pg-conflict-deposit-{uuid.uuid4()}",
        )
        sales = PostgresProductSaleRepository(lambda: engine)
        service = ProductSaleService(sales, catalog, clients)
        results = await asyncio.gather(
            service.sell(
                product.id,
                quantity=1,
                client_id=client.id,
                payment_method="balance",
                cash_shift_id=None,
                sold_by="integration-test",
                idempotency_key="pg-sale-conflicting-payload",
            ),
            service.sell(
                product.id,
                quantity=2,
                client_id=client.id,
                payment_method="balance",
                cash_shift_id=None,
                sold_by="integration-test",
                idempotency_key="pg-sale-conflicting-payload",
            ),
            return_exceptions=True,
        )

        successful = [item for item in results if not isinstance(item, Exception)]
        failures = [item for item in results if isinstance(item, Exception)]
        assert len(successful) == 1
        assert len(failures) == 1
        assert isinstance(failures[0], ApplicationError)
        assert failures[0].code is ErrorCode.CONFLICT
        final_sale = await sales.get_by_idempotency_key("pg-sale-conflicting-payload")
        final_product = await catalog.get_product(product.id)
        final_client = await clients.get(client.id)
        assert final_sale is not None
        assert final_product is not None
        assert final_client.balance_cents == 1_000 - 300 * final_sale.quantity
        assert final_product.stock_quantity == 3 - final_sale.quantity
    finally:
        async with engine.begin() as connection:
            if product_id is not None:
                await connection.execute(
                    text("DELETE FROM product_sales WHERE product_id = :product_id"),
                    {"product_id": product_id},
                )
                await connection.execute(
                    text("DELETE FROM products WHERE id = :product_id"),
                    {"product_id": product_id},
                )
            if client_id is not None:
                await connection.execute(
                    text("DELETE FROM balance_operations WHERE client_id = :client_id"),
                    {"client_id": client_id},
                )
                await connection.execute(
                    text("DELETE FROM clients WHERE id = :client_id"),
                    {"client_id": client_id},
                )
        await engine.dispose()
