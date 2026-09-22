from __future__ import annotations

import datetime
import typing
import uuid

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.ext.asyncio import AsyncSession

from gameclub_backend.infrastructure.database import EngineProvider, open_session
from gameclub_backend.modules.analytics.read_v2 import (
    AnalyticsFilter,
    AnalyticsReadRepository,
    ProductAdjustmentFact,
    ProductSaleFact,
)

product_sales = sa.table(
    "product_sales",
    sa.column("id", UUID(as_uuid=True)),
    sa.column("product_id", UUID(as_uuid=True)),
    sa.column("product_name", sa.String()),
    sa.column("product_category", sa.String()),
    sa.column("quantity", sa.Integer()),
    sa.column("total_price_cents", sa.BigInteger()),
    sa.column("total_cost_price_cents", sa.BigInteger()),
    sa.column("created_at", sa.DateTime(timezone=True)),
    sa.column("status", sa.String()),
    sa.column("client_id", UUID(as_uuid=True)),
    sa.column("payment_method", sa.String()),
    sa.column("sold_by", sa.String()),
)


def _uuid(value: object) -> uuid.UUID | None:
    return value if isinstance(value, uuid.UUID) else None


def _int(value: object) -> int:
    return int(value) if isinstance(value, (int, float)) else 0


def build_product_read_snapshot(
    *,
    sale_rows: typing.Iterable[dict[str, object]],
    adjustment_rows: typing.Iterable[dict[str, object]] | None,
) -> tuple[tuple[ProductSaleFact, ...], tuple[ProductAdjustmentFact, ...] | None]:
    sales = tuple(
        ProductSaleFact(
            source_id=f"product_sale:{row['id']}",
            product_id=typing.cast(uuid.UUID, row["product_id"]),
            product_name=str(row.get("product_name") or ""),
            category_key=str(row.get("product_category") or ""),
            quantity=_int(row.get("quantity")),
            revenue_cents=_int(row.get("total_price_cents")),
            cost_cents=_int(row.get("total_cost_price_cents")),
            occurred_at=typing.cast(datetime.datetime, row["created_at"]),
            status=str(row.get("status") or ""),
            session_id=_uuid(row.get("session_id")),
            client_id=_uuid(row.get("client_id")),
            payment_method_key=str(row.get("payment_method") or "") or None,
            operator_key=str(row.get("sold_by") or "") or None,
        )
        for row in sale_rows
    )
    if adjustment_rows is None:
        return sales, None
    adjustments = tuple(
        ProductAdjustmentFact(
            source_id=f"adjustment:{row['id']}",
            adjustment_type=str(row.get("adjustment_type") or "adjustment"),
            amount_cents=_int(row.get("amount_cents")),
            quantity=_int(row.get("quantity")),
            occurred_at=typing.cast(datetime.datetime, row["created_at"]),
            status=str(row.get("status") or ""),
            product_id=_uuid(row.get("product_id")),
            category_key=str(row.get("product_category") or "") or None,
            client_id=_uuid(row.get("client_id")),
            operator_key=str(row.get("actor_id") or "") or None,
            reason=str(row.get("reason") or "") or None,
            source_reference=str(row.get("source_reference") or "") or None,
        )
        for row in adjustment_rows
    )
    return sales, adjustments


class PostgresAnalyticsReadRepository(AnalyticsReadRepository):
    def __init__(
        self, engine_provider: EngineProvider, period: AnalyticsFilter | None = None
    ) -> None:
        self._engine_provider = engine_provider
        self._period = period

    async def snapshot(
        self, filters: AnalyticsFilter | None = None
    ) -> tuple[tuple[ProductSaleFact, ...], tuple[ProductAdjustmentFact, ...] | None]:
        if filters is None:
            return (), None
        async with open_session(self._engine_provider) as session:
            rows = await self._rows(session, filters)
        return build_product_read_snapshot(sale_rows=rows, adjustment_rows=None)

    @staticmethod
    async def _rows(session: AsyncSession, filters: AnalyticsFilter) -> list[dict[str, object]]:
        result = await session.execute(
            sa.select(product_sales).where(
                product_sales.c.created_at >= filters.start_at,
                product_sales.c.created_at < filters.end_at,
                product_sales.c.status.in_(("completed", "confirmed")),
            )
        )
        return [dict(row) for row in result.mappings().all()]
