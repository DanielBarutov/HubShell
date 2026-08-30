import uuid

from gameclub_backend.modules.catalog.domain import Product
from gameclub_backend.modules.catalog.infrastructure import postgres


class FakeSession:
    def __init__(self, model: postgres.ProductModel) -> None:
        self.model = model
        self.added: object | None = None
        self.committed = False

    async def get(self, _model_type: type[postgres.ProductModel], _product_id: uuid.UUID):
        return self.model

    def add(self, model: object) -> None:
        self.added = model

    async def commit(self) -> None:
        self.committed = True


class FakeSessionContext:
    def __init__(self, session: FakeSession) -> None:
        self.session = session

    async def __aenter__(self) -> FakeSession:
        return self.session

    async def __aexit__(self, *_args: object) -> None:
        return None


async def test_save_product_updates_existing_postgres_row(monkeypatch) -> None:
    product_id = uuid.uuid4()
    existing = postgres.ProductModel(
        id=product_id,
        name="Кофе",
        category="Напитки",
        price_cents=10000,
        active=True,
        cost_price_cents=6400,
        stock_quantity=10,
    )
    session = FakeSession(existing)

    def fake_open_session(_provider):
        return FakeSessionContext(session)

    monkeypatch.setattr(postgres, "open_session", fake_open_session)

    updated = Product(
        id=product_id,
        name="Кофе",
        category="Напитки",
        price_cents=12000,
        active=False,
        cost_price_cents=7000,
        stock_quantity=8,
    )

    result = await postgres.PostgresCatalogRepository(lambda: None).save_product(updated)

    assert result == updated
    assert session.added is None
    assert session.committed is True
    assert existing.name == updated.name
    assert existing.category == updated.category
    assert existing.price_cents == updated.price_cents
    assert existing.active == updated.active
    assert existing.cost_price_cents == updated.cost_price_cents
    assert existing.stock_quantity == updated.stock_quantity
