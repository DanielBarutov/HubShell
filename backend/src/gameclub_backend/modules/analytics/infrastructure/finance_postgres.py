from __future__ import annotations

import datetime
import typing
import uuid

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.ext.asyncio import AsyncSession

from gameclub_backend.infrastructure.database import EngineProvider, open_session
from gameclub_backend.modules.analytics.application.ports import FinanceAnalyticsRepository
from gameclub_backend.modules.analytics.finance import (
    CONFIRMED_STATUSES,
    FinanceFactsSnapshot,
    FinanceFactType,
    FinanceFilters,
    FinancialFact,
    WalletFact,
    WalletFactType,
    is_confirmed_status,
)

balance_operations = sa.table(
    "balance_operations",
    sa.column("id", UUID(as_uuid=True)),
    sa.column("client_id", UUID(as_uuid=True)),
    sa.column("amount_cents", sa.BigInteger()),
    sa.column("operation_type", sa.String()),
    sa.column("created_at", sa.DateTime(timezone=True)),
    sa.column("actor_id", sa.String()),
    sa.column("idempotency_key", sa.String()),
    sa.column("payment_parts", sa.JSON()),
)
product_sales = sa.table(
    "product_sales",
    sa.column("id", UUID(as_uuid=True)),
    sa.column("client_id", UUID(as_uuid=True)),
    sa.column("total_price_cents", sa.BigInteger()),
    sa.column("payment_method", sa.String()),
    sa.column("status", sa.String()),
    sa.column("created_at", sa.DateTime(timezone=True)),
    sa.column("sold_by", sa.String()),
    sa.column("payment_parts", sa.JSON()),
)
guest_session_payments = sa.table(
    "guest_session_payments",
    sa.column("id", UUID(as_uuid=True)),
    sa.column("guest_id", UUID(as_uuid=True)),
    sa.column("total_price_cents", sa.BigInteger()),
    sa.column("status", sa.String()),
    sa.column("created_at", sa.DateTime(timezone=True)),
    sa.column("created_by", sa.String()),
    sa.column("payment_parts", sa.JSON()),
)
client_entitlements = sa.table(
    "client_entitlements",
    sa.column("id", UUID(as_uuid=True)),
    sa.column("client_id", UUID(as_uuid=True)),
    sa.column("price_cents", sa.BigInteger()),
    sa.column("settlement_status", sa.String()),
    sa.column("purchased_at", sa.DateTime(timezone=True)),
    sa.column("payment_parts", sa.JSON()),
)


def _as_uuid(value: object) -> uuid.UUID | None:
    return value if isinstance(value, uuid.UUID) else None


def _as_parts(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list):
        return []
    return [part for part in value if isinstance(part, dict)]


def _part_amount(part: dict[str, object]) -> int:
    value = part.get("amount_cents", 0)
    return int(value) if isinstance(value, (int, float)) else 0


def _as_int(value: object) -> int:
    return int(value) if isinstance(value, (int, float)) else 0


def _part_method(part: dict[str, object]) -> str | None:
    value = part.get("method")
    return str(value) if value is not None else None


def _part_reference(part: dict[str, object]) -> str | None:
    value = part.get("reference")
    return str(value) if value is not None else None


def _wallet_facts_from_balance_row(row: dict[str, object]) -> list[WalletFact]:
    source_id = str(row["id"])
    operation_type = str(row.get("operation_type") or "")
    fact_type = {
        "top_up": WalletFactType.TOP_UP,
        "debit": WalletFactType.DEBIT,
    }.get(operation_type)
    if fact_type is None:
        return []
    occurred_at = typing.cast(datetime.datetime, row["created_at"])
    parts = _as_parts(row.get("payment_parts"))
    if fact_type is WalletFactType.DEBIT or not parts:
        return [
            WalletFact(
                source_id=f"balance_operation:{source_id}",
                fact_type=fact_type,
                amount_cents=abs(_as_int(row["amount_cents"])),
                occurred_at=occurred_at,
                status="completed",
                source_reference=str(row.get("idempotency_key") or source_id),
                operator_key=str(row.get("actor_id") or "") or None,
                client_id=_as_uuid(row.get("client_id")),
                operation_type=operation_type,
            )
        ]
    facts: list[WalletFact] = []
    for index, part in enumerate(parts):
        amount_cents = _part_amount(part)
        if amount_cents <= 0:
            continue
        facts.append(
            WalletFact(
                source_id=f"balance_operation:{source_id}:{index}",
                fact_type=fact_type,
                amount_cents=amount_cents,
                occurred_at=occurred_at,
                status="completed",
                source_reference=f"{row.get('idempotency_key') or source_id}:{index}",
                payment_method_key=_part_method(part),
                operation_type=operation_type,
                operator_key=str(row.get("actor_id") or "") or None,
                client_id=_as_uuid(row.get("client_id")),
            )
        )
    return facts


def _payment_facts_from_parts(
    *,
    source_type: str,
    source_id: str,
    occurred_at: datetime.datetime,
    status: str,
    parts: list[dict[str, object]],
    client_id: uuid.UUID | None = None,
    operator_key: str | None = None,
    guest_id: uuid.UUID | None = None,
) -> list[FinancialFact]:
    if not is_confirmed_status(status):
        return []
    facts: list[FinancialFact] = []
    for index, part in enumerate(parts):
        amount_cents = _part_amount(part)
        method_key = _part_method(part)
        if amount_cents <= 0 or method_key in {None, "balance"}:
            continue
        facts.append(
            FinancialFact(
                source_id=f"{source_type}:{source_id}:{index}",
                fact_type=FinanceFactType.PAYMENT,
                amount_cents=amount_cents,
                occurred_at=occurred_at,
                status=status,
                source_reference=(_part_reference(part) or f"{source_type}:{source_id}:{index}"),
                payment_method_key=method_key,
                operation_type="payment",
                operator_key=operator_key,
                client_id=client_id,
            )
        )
    return facts


def _product_sale_facts(row: dict[str, object]) -> list[FinancialFact]:
    source_id = str(row["id"])
    parts = _as_parts(row.get("payment_parts"))
    if parts:
        return _payment_facts_from_parts(
            source_type="product_sale",
            source_id=source_id,
            occurred_at=typing.cast(datetime.datetime, row["created_at"]),
            status=str(row.get("status") or ""),
            parts=parts,
            client_id=_as_uuid(row.get("client_id")),
            operator_key=str(row.get("sold_by") or "") or None,
        )
    method_key = str(row.get("payment_method") or "")
    if not is_confirmed_status(str(row.get("status") or "")) or method_key == "balance":
        return []
    return [
        FinancialFact(
            source_id=f"product_sale:{source_id}",
            fact_type=FinanceFactType.PAYMENT,
            amount_cents=_as_int(row["total_price_cents"]),
            occurred_at=typing.cast(datetime.datetime, row["created_at"]),
            status=str(row["status"]),
            source_reference=f"product_sale:{source_id}",
            payment_method_key=method_key,
            operation_type="payment",
            operator_key=str(row.get("sold_by") or "") or None,
            client_id=_as_uuid(row.get("client_id")),
        )
    ]


def _entitlement_facts(row: dict[str, object]) -> list[FinancialFact]:
    settlement_status = str(row.get("settlement_status") or "")
    normalized_status = "confirmed" if settlement_status == "settled" else settlement_status
    return _payment_facts_from_parts(
        source_type="entitlement",
        source_id=str(row["id"]),
        occurred_at=typing.cast(datetime.datetime, row["purchased_at"]),
        status=normalized_status,
        parts=_as_parts(row.get("payment_parts")),
        client_id=_as_uuid(row.get("client_id")),
    )


def _guest_payment_facts(row: dict[str, object]) -> list[FinancialFact]:
    return _payment_facts_from_parts(
        source_type="guest_session_payment",
        source_id=str(row["id"]),
        occurred_at=typing.cast(datetime.datetime, row["created_at"]),
        status=str(row.get("status") or ""),
        parts=_as_parts(row.get("payment_parts")),
        guest_id=_as_uuid(row.get("guest_id")),
        operator_key=str(row.get("created_by") or "") or None,
    )


def build_finance_snapshot(
    *,
    balance_rows: typing.Iterable[dict[str, object]],
    sale_rows: typing.Iterable[dict[str, object]],
    guest_payment_rows: typing.Iterable[dict[str, object]],
    entitlement_rows: typing.Iterable[dict[str, object]],
) -> FinanceFactsSnapshot:
    wallet_facts = [fact for row in balance_rows for fact in _wallet_facts_from_balance_row(row)]
    financial_facts = [fact for row in sale_rows for fact in _product_sale_facts(row)]
    financial_facts.extend(fact for row in guest_payment_rows for fact in _guest_payment_facts(row))
    financial_facts.extend(fact for row in entitlement_rows for fact in _entitlement_facts(row))
    return FinanceFactsSnapshot(
        financial_facts=tuple(financial_facts),
        wallet_facts=tuple(wallet_facts),
        refunds_available=False,
        history_available=False,
    )


class PostgresFinanceAnalyticsRepository(FinanceAnalyticsRepository):
    def __init__(self, engine_provider: EngineProvider) -> None:
        self._engine_provider = engine_provider

    async def snapshot(self, filters: FinanceFilters | None = None) -> FinanceFactsSnapshot:
        if filters is None:
            raise ValueError("Finance snapshot requires a period")
        async with open_session(self._engine_provider) as session:
            balance_rows = await self._rows(
                session,
                balance_operations,
                balance_operations.c.created_at,
                filters,
            )
            sale_rows = await self._rows(
                session,
                product_sales,
                product_sales.c.created_at,
                filters,
                product_sales.c.status.in_(CONFIRMED_STATUSES),
            )
            guest_rows = await self._rows(
                session,
                guest_session_payments,
                guest_session_payments.c.created_at,
                filters,
                guest_session_payments.c.status.in_(CONFIRMED_STATUSES),
            )
            entitlement_rows = await self._rows(
                session,
                client_entitlements,
                client_entitlements.c.purchased_at,
                filters,
                client_entitlements.c.settlement_status.in_(("completed", "confirmed", "settled")),
            )
        return build_finance_snapshot(
            balance_rows=balance_rows,
            sale_rows=sale_rows,
            guest_payment_rows=guest_rows,
            entitlement_rows=entitlement_rows,
        )

    @staticmethod
    async def _rows(
        session: AsyncSession,
        table: sa.TableClause,
        timestamp_column: sa.ColumnClause,
        filters: FinanceFilters,
        *conditions: sa.ColumnElement[bool],
    ) -> list[dict[str, object]]:
        result = await session.execute(
            sa.select(table).where(
                timestamp_column >= filters.start_at,
                timestamp_column < filters.end_at,
                *conditions,
            )
        )
        return [dict(row) for row in result.mappings().all()]
