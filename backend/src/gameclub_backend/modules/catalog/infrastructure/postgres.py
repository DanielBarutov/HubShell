import dataclasses
import datetime
import uuid

from sqlalchemy import DateTime, Integer, String, desc, select, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from gameclub_backend.infrastructure.database import EngineProvider, open_session
from gameclub_backend.modules.catalog.domain import (
    BillingMode,
    DiscountRule,
    Product,
    ProductCategory,
    Tariff,
    TariffLifecycle,
)


class CatalogBase(DeclarativeBase):
    pass


class ProductCategoryModel(CatalogBase):
    __tablename__ = "product_categories"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(128))
    kind: Mapped[str] = mapped_column(String(16), index=True)
    active: Mapped[bool] = mapped_column(default=True)

    def to_domain(self) -> ProductCategory:
        return ProductCategory(self.id, self.name, self.kind, self.active)

    @classmethod
    def from_domain(cls, category: ProductCategory) -> "ProductCategoryModel":
        return cls(id=category.id, name=category.name, kind=category.kind, active=category.active)


class ProductModel(CatalogBase):
    __tablename__ = "products"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    name: Mapped[str] = mapped_column(String(128))
    category: Mapped[str] = mapped_column(String(64), index=True)
    price_cents: Mapped[int] = mapped_column()
    active: Mapped[bool] = mapped_column(default=True)
    cost_price_cents: Mapped[int] = mapped_column(default=0)
    stock_quantity: Mapped[int] = mapped_column(default=0)

    def to_domain(self) -> Product:
        return Product(
            id=self.id,
            name=self.name,
            category=self.category,
            price_cents=self.price_cents,
            active=self.active,
            cost_price_cents=self.cost_price_cents,
            stock_quantity=self.stock_quantity,
        )

    @classmethod
    def from_domain(cls, product: Product) -> "ProductModel":
        return cls(
            id=product.id,
            name=product.name,
            category=product.category,
            price_cents=product.price_cents,
            active=product.active,
            cost_price_cents=product.cost_price_cents,
            stock_quantity=product.stock_quantity,
        )


class TariffModel(CatalogBase):
    __tablename__ = "tariffs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    name: Mapped[str] = mapped_column(String(128))
    group_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    duration_minutes: Mapped[int] = mapped_column()
    price_cents: Mapped[int] = mapped_column()
    valid_from: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True))
    valid_to: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    active: Mapped[bool] = mapped_column(default=True)
    tariff_key: Mapped[str] = mapped_column(String(128), index=True)
    version: Mapped[int] = mapped_column(default=1)
    lifecycle: Mapped[str] = mapped_column(String(16), index=True)
    billing_mode: Mapped[str] = mapped_column(String(16), default=BillingMode.BLOCK.value)
    price_per_minute_cents: Mapped[int] = mapped_column(default=0)
    free_minutes: Mapped[int] = mapped_column(default=0)

    def to_domain(self) -> Tariff:
        return Tariff(
            id=self.id,
            name=self.name,
            group_id=self.group_id,
            duration_minutes=self.duration_minutes,
            price_cents=self.price_cents,
            valid_from=self.valid_from,
            valid_to=self.valid_to,
            active=self.active,
            tariff_key=self.tariff_key,
            version=self.version,
            lifecycle=TariffLifecycle(self.lifecycle),
            billing_mode=BillingMode(self.billing_mode),
            price_per_minute_cents=self.price_per_minute_cents,
            free_minutes=self.free_minutes,
        )

    @classmethod
    def from_domain(cls, tariff: Tariff) -> "TariffModel":
        return cls(
            id=tariff.id,
            name=tariff.name,
            group_id=tariff.group_id,
            duration_minutes=tariff.duration_minutes,
            price_cents=tariff.price_cents,
            valid_from=tariff.valid_from,
            valid_to=tariff.valid_to,
            active=tariff.active,
            tariff_key=tariff.tariff_key,
            version=tariff.version,
            lifecycle=tariff.lifecycle.value,
            billing_mode=tariff.billing_mode.value,
            price_per_minute_cents=tariff.price_per_minute_cents,
            free_minutes=tariff.free_minutes,
        )


class DiscountRuleModel(CatalogBase):
    __tablename__ = "discount_rules"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    category: Mapped[str] = mapped_column(String(64), index=True)
    percent_bps: Mapped[int] = mapped_column(Integer())
    priority: Mapped[int] = mapped_column(Integer(), default=0)
    valid_from: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True))
    valid_to: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    active: Mapped[bool] = mapped_column(default=True)

    def to_domain(self) -> DiscountRule:
        return DiscountRule(
            id=self.id,
            category=self.category,
            percent_bps=self.percent_bps,
            priority=self.priority,
            valid_from=self.valid_from,
            valid_to=self.valid_to,
            active=self.active,
        )

    @classmethod
    def from_domain(cls, rule: DiscountRule) -> "DiscountRuleModel":
        return cls(
            id=rule.id,
            category=rule.category,
            percent_bps=rule.percent_bps,
            priority=rule.priority,
            valid_from=rule.valid_from,
            valid_to=rule.valid_to,
            active=rule.active,
        )


class PostgresCatalogRepository:
    def __init__(self, engine_provider: EngineProvider) -> None:
        self._engine_provider = engine_provider

    async def save_product(self, product: Product) -> Product:
        async with open_session(self._engine_provider) as session:
            model = await session.get(ProductModel, product.id)
            if model is None:
                session.add(ProductModel.from_domain(product))
            else:
                model.name = product.name
                model.category = product.category
                model.price_cents = product.price_cents
                model.active = product.active
                model.cost_price_cents = product.cost_price_cents
                model.stock_quantity = product.stock_quantity
            await session.commit()
            return product

    async def save_category(self, category: ProductCategory) -> ProductCategory:
        async with open_session(self._engine_provider) as session:
            model = await session.get(ProductCategoryModel, category.id)
            if model is None:
                session.add(ProductCategoryModel.from_domain(category))
            else:
                model.name = category.name
                model.kind = category.kind
                model.active = category.active
            await session.commit()
            return category

    async def list_categories(self) -> list[ProductCategory]:
        async with open_session(self._engine_provider) as session:
            result = await session.scalars(
                select(ProductCategoryModel).order_by(ProductCategoryModel.name)
            )
            return [model.to_domain() for model in result]

    async def get_category(self, category_id: str) -> ProductCategory | None:
        async with open_session(self._engine_provider) as session:
            model = await session.get(ProductCategoryModel, category_id)
            return model.to_domain() if model else None

    async def delete_category(self, category_id: str) -> None:
        async with open_session(self._engine_provider) as session:
            model = await session.get(ProductCategoryModel, category_id)
            if model is not None:
                await session.delete(model)
                await session.commit()

    async def list_products(self) -> list[Product]:
        async with open_session(self._engine_provider) as session:
            result = await session.scalars(select(ProductModel).order_by(ProductModel.name))
            return [model.to_domain() for model in result]

    async def get_product(self, product_id: uuid.UUID) -> Product | None:
        async with open_session(self._engine_provider) as session:
            model = await session.get(ProductModel, product_id)
            return model.to_domain() if model else None

    async def delete_product(self, product_id: uuid.UUID) -> None:
        async with open_session(self._engine_provider) as session:
            model = await session.get(ProductModel, product_id)
            if model is not None:
                await session.delete(model)
                await session.commit()

    async def save_tariff(self, tariff: Tariff) -> Tariff:
        async with open_session(self._engine_provider) as session:
            model = await session.get(TariffModel, tariff.id)
            if model is None:
                session.add(TariffModel.from_domain(tariff))
            else:
                self._copy_tariff_values(model, tariff)
            await session.commit()
            return tariff

    async def create_tariff(self, tariff: Tariff) -> Tariff:
        async with open_session(self._engine_provider) as session:
            async with session.begin():
                await session.execute(
                    text("SELECT pg_advisory_xact_lock(hashtext(:lock_key))"),
                    {"lock_key": f"tariff-key:{tariff.tariff_key}"},
                )
                latest = await session.scalar(
                    select(TariffModel.version)
                    .where(TariffModel.tariff_key == tariff.tariff_key)
                    .order_by(desc(TariffModel.version))
                    .limit(1)
                )
                created = dataclasses.replace(tariff, version=(latest or 0) + 1)
                session.add(TariffModel.from_domain(created))
                return created

    async def list_tariffs(self) -> list[Tariff]:
        async with open_session(self._engine_provider) as session:
            result = await session.scalars(
                select(TariffModel).order_by(TariffModel.name, TariffModel.duration_minutes)
            )
            return [model.to_domain() for model in result]

    async def get_tariff(self, tariff_id: uuid.UUID) -> Tariff | None:
        async with open_session(self._engine_provider) as session:
            model = await session.get(TariffModel, tariff_id)
            return model.to_domain() if model else None

    async def find_tariffs(
        self,
        group_id: str | None,
        moment: datetime.datetime,
    ) -> list[Tariff]:
        async with open_session(self._engine_provider) as session:
            result = await session.scalars(
                select(TariffModel).where(
                    TariffModel.active.is_(True),
                    TariffModel.valid_from <= moment,
                    (TariffModel.valid_to.is_(None) | (TariffModel.valid_to > moment)),
                    (TariffModel.group_id.is_(None) | (TariffModel.group_id == group_id)),
                    TariffModel.lifecycle == TariffLifecycle.PUBLISHED.value,
                )
            )
            return [model.to_domain() for model in result]

    @staticmethod
    def _copy_tariff_values(model: TariffModel, tariff: Tariff) -> None:
        values = TariffModel.from_domain(tariff).__dict__
        for key, value in values.items():
            if not key.startswith("_"):
                setattr(model, key, value)

    async def save_discount_rule(self, rule: DiscountRule) -> DiscountRule:
        async with open_session(self._engine_provider) as session:
            session.add(DiscountRuleModel.from_domain(rule))
            await session.commit()
            return rule

    async def list_discount_rules(self) -> list[DiscountRule]:
        async with open_session(self._engine_provider) as session:
            result = await session.scalars(
                select(DiscountRuleModel).order_by(
                    DiscountRuleModel.priority.desc(),
                    DiscountRuleModel.category,
                )
            )
            return [model.to_domain() for model in result]

    async def find_discount_rules(
        self,
        category: str | None,
        moment: datetime.datetime,
    ) -> list[DiscountRule]:
        async with open_session(self._engine_provider) as session:
            result = await session.scalars(
                select(DiscountRuleModel).where(
                    DiscountRuleModel.active.is_(True),
                    DiscountRuleModel.valid_from <= moment,
                    (DiscountRuleModel.valid_to.is_(None) | (DiscountRuleModel.valid_to > moment)),
                    DiscountRuleModel.category == category,
                )
            )
            return [model.to_domain() for model in result]
