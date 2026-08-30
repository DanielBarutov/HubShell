from __future__ import annotations

import datetime
import uuid

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

from gameclub_backend.infrastructure.database import EngineProvider, open_session
from gameclub_backend.modules.analytics.domain import (
    AnalyticsBreakdown,
    AnalyticsBucket,
    AnalyticsOverview,
    AnalyticsPayment,
    ClientAnalytics,
    TopClient,
    TopProduct,
)

clients = sa.table(
    "clients",
    sa.column("id", UUID(as_uuid=True)),
    sa.column("nickname", sa.String()),
    sa.column("phone", sa.String()),
    sa.column("created_at", sa.DateTime(timezone=True)),
    sa.column("blocked_at", sa.DateTime(timezone=True)),
)
sessions = sa.table(
    "gaming_sessions",
    sa.column("id", UUID(as_uuid=True)),
    sa.column("workstation_id", UUID(as_uuid=True)),
    sa.column("client_id", UUID(as_uuid=True)),
    sa.column("status", sa.String()),
    sa.column("started_at", sa.DateTime(timezone=True)),
    sa.column("ended_at", sa.DateTime(timezone=True)),
    sa.column("tariff_id", UUID(as_uuid=True)),
)
workstations = sa.table(
    "workstations",
    sa.column("id", UUID(as_uuid=True)),
    sa.column("name", sa.String()),
    sa.column("group_id", sa.String()),
    sa.column("archived_at", sa.DateTime(timezone=True)),
)
workstation_groups = sa.table(
    "workstation_groups",
    sa.column("id", sa.String()),
    sa.column("name", sa.String()),
)
tariffs = sa.table(
    "tariffs",
    sa.column("id", UUID(as_uuid=True)),
    sa.column("name", sa.String()),
)
charges = sa.table(
    "session_charges",
    sa.column("session_id", UUID(as_uuid=True)),
    sa.column("client_id", UUID(as_uuid=True)),
    sa.column("tariff_id", UUID(as_uuid=True)),
    sa.column("amount_cents", sa.BigInteger()),
    sa.column("duration_minutes", sa.Integer()),
    sa.column("discount_amount_cents", sa.BigInteger()),
    sa.column("created_at", sa.DateTime(timezone=True)),
)
sales = sa.table(
    "product_sales",
    sa.column("id", UUID(as_uuid=True)),
    sa.column("product_id", UUID(as_uuid=True)),
    sa.column("product_name", sa.String()),
    sa.column("product_category", sa.String()),
    sa.column("client_id", UUID(as_uuid=True)),
    sa.column("quantity", sa.Integer()),
    sa.column("unit_cost_price_cents", sa.BigInteger()),
    sa.column("total_price_cents", sa.BigInteger()),
    sa.column("payment_method", sa.String()),
    sa.column("status", sa.String()),
    sa.column("created_at", sa.DateTime(timezone=True)),
)


def _period_filter(column: sa.ColumnClause, start_at: datetime.datetime, end_at: datetime.datetime):
    return sa.and_(column >= start_at, column < end_at)


def _int(value: object) -> int:
    return int(value or 0)


def _minutes(value: object) -> int:
    return int(float(value or 0))


def _share_bps(value: int, total: int) -> int:
    if not total:
        return 0
    return round(value * 10_000 / total)


def _new_bucket() -> dict[str, int]:
    return {
        "session_revenue_cents": 0,
        "product_revenue_cents": 0,
        "session_count": 0,
        "product_sale_count": 0,
        "product_units": 0,
        "played_minutes": 0,
        "guest_session_count": 0,
    }


def _bucket(
    key: str,
    label: str,
    values: dict[str, int],
) -> AnalyticsBucket:
    session_revenue = values["session_revenue_cents"]
    product_revenue = values["product_revenue_cents"]
    return AnalyticsBucket(
        key=key,
        label=label,
        session_revenue_cents=session_revenue,
        product_revenue_cents=product_revenue,
        total_revenue_cents=session_revenue + product_revenue,
        session_count=values["session_count"],
        product_sale_count=values["product_sale_count"],
        product_units=values["product_units"],
        played_minutes=values["played_minutes"],
        guest_session_count=values["guest_session_count"],
    )


def _breakdown(
    key: str,
    label: str,
    session_revenue_cents: int,
    product_revenue_cents: int,
    product_cost_cents: int,
    session_count: int,
    product_sale_count: int,
    product_units: int,
    played_minutes: int,
    total_revenue_cents: int,
    discount_cents: int = 0,
) -> AnalyticsBreakdown:
    revenue = session_revenue_cents + product_revenue_cents
    return AnalyticsBreakdown(
        key=key,
        label=label,
        session_revenue_cents=session_revenue_cents,
        product_revenue_cents=product_revenue_cents,
        revenue_cents=revenue,
        product_cost_cents=product_cost_cents,
        gross_profit_cents=revenue - product_cost_cents,
        session_count=session_count,
        product_sale_count=product_sale_count,
        product_units=product_units,
        played_minutes=played_minutes,
        share_bps=_share_bps(revenue, total_revenue_cents),
        discount_cents=discount_cents,
    )


class PostgresAnalyticsRepository:
    def __init__(self, engine_provider: EngineProvider) -> None:
        self._engine_provider = engine_provider

    async def overview(
        self,
        start_at: datetime.datetime,
        end_at: datetime.datetime,
        limit: int,
    ) -> AnalyticsOverview:
        async with open_session(self._engine_provider) as session:
            session_financials = (
                await session.execute(
                    sa.select(
                        sa.func.coalesce(sa.func.sum(charges.c.amount_cents), 0),
                        sa.func.coalesce(sa.func.sum(charges.c.discount_amount_cents), 0),
                    ).where(_period_filter(charges.c.created_at, start_at, end_at))
                )
            ).one()
            product_stats = (
                await session.execute(
                    sa.select(
                        sa.func.coalesce(sa.func.sum(sales.c.total_price_cents), 0),
                        sa.func.coalesce(
                            sa.func.sum(sales.c.unit_cost_price_cents * sales.c.quantity), 0
                        ),
                        sa.func.count(sales.c.id),
                        sa.func.coalesce(sa.func.sum(sales.c.quantity), 0),
                    ).where(
                        sales.c.status == "completed",
                        _period_filter(sales.c.created_at, start_at, end_at),
                    )
                )
            ).one()
            session_stats = (
                await session.execute(
                    sa.select(
                        sa.func.count(sessions.c.id),
                        sa.func.coalesce(
                            sa.func.sum(
                                sa.func.extract(
                                    "epoch", sessions.c.ended_at - sessions.c.started_at
                                )
                                / 60
                            ),
                            0,
                        ),
                        sa.func.count().filter(sessions.c.client_id.is_(None)),
                    ).where(
                        sessions.c.status == "completed",
                        sessions.c.ended_at.is_not(None),
                        _period_filter(sessions.c.started_at, start_at, end_at),
                    )
                )
            ).one()
            (client_count,) = (
                await session.execute(
                    sa.select(sa.func.count(clients.c.id)).where(clients.c.blocked_at.is_(None))
                )
            ).one()
            active_client_ids = sa.union(
                sa.select(sessions.c.client_id.label("client_id")).where(
                    sessions.c.client_id.is_not(None),
                    sessions.c.status == "completed",
                    _period_filter(sessions.c.started_at, start_at, end_at),
                ),
                sa.select(sales.c.client_id.label("client_id")).where(
                    sales.c.client_id.is_not(None),
                    sales.c.status == "completed",
                    _period_filter(sales.c.created_at, start_at, end_at),
                ),
            ).subquery()
            (active_client_count,) = (
                await session.execute(sa.select(sa.func.count()).select_from(active_client_ids))
            ).one()
            (new_client_count,) = (
                await session.execute(
                    sa.select(sa.func.count(clients.c.id)).where(
                        clients.c.blocked_at.is_(None),
                        _period_filter(clients.c.created_at, start_at, end_at),
                    )
                )
            ).one()
            (returning_client_count,) = (
                await session.execute(
                    sa.select(sa.func.count())
                    .select_from(
                        active_client_ids.join(
                            clients, clients.c.id == active_client_ids.c.client_id
                        )
                    )
                    .where(clients.c.created_at < start_at)
                )
            ).one()
            (workstation_count,) = (
                await session.execute(
                    sa.select(sa.func.count(workstations.c.id)).where(
                        workstations.c.archived_at.is_(None)
                    )
                )
            ).one()
            daily_activity = await self._activity_buckets(session, start_at, end_at, limit=None)
            hourly_activity = await self._hourly_activity(session, start_at, end_at)
            total_revenue = _int(session_financials[0]) + _int(product_stats[0])
            played_minutes = _minutes(session_stats[1])
            period_minutes = max((end_at - start_at).total_seconds() / 60, 1)
            capacity_minutes = max(_int(workstation_count), 1) * period_minutes
            occupancy_percent = round(min(100, played_minutes / capacity_minutes * 100), 2)
            zones = await self._zone_breakdown(session, start_at, end_at, total_revenue)
            workstation_breakdown = await self._workstation_breakdown(
                session, start_at, end_at, total_revenue
            )
            tariff_breakdown = await self._tariff_breakdown(
                session, start_at, end_at, total_revenue
            )
            payment_methods = await self._payment_breakdown(
                session, start_at, end_at, total_revenue
            )
            product_categories = await self._product_category_breakdown(
                session, start_at, end_at, total_revenue
            )
            peak_usage_hour = (
                max(hourly_activity, key=lambda item: item.played_minutes, default=None)
                if any(item.played_minutes for item in hourly_activity)
                else None
            )
            return AnalyticsOverview(
                start_at=start_at,
                end_at=end_at,
                session_revenue_cents=_int(session_financials[0]),
                product_revenue_cents=_int(product_stats[0]),
                total_revenue_cents=total_revenue,
                session_count=_int(session_stats[0]),
                product_sale_count=_int(product_stats[2]),
                product_units=_int(product_stats[3]),
                played_minutes=played_minutes,
                guest_session_count=_int(session_stats[2]),
                client_count=_int(client_count),
                top_products=tuple(await self._top_products(session, start_at, end_at, limit)),
                top_clients=tuple(await self._top_clients(session, start_at, end_at, limit)),
                product_cost_cents=_int(product_stats[1]),
                gross_profit_cents=total_revenue - _int(product_stats[1]),
                discount_cents=_int(session_financials[1]),
                active_client_count=_int(active_client_count),
                new_client_count=_int(new_client_count),
                returning_client_count=_int(returning_client_count),
                unique_visitor_count=_int(active_client_count) + _int(session_stats[2]),
                workstation_count=_int(workstation_count),
                occupancy_percent=occupancy_percent,
                peak_usage_hour=peak_usage_hour.label if peak_usage_hour else None,
                daily_activity=tuple(daily_activity),
                hourly_activity=tuple(hourly_activity),
                zones=tuple(zones),
                workstations=tuple(workstation_breakdown),
                tariffs=tuple(tariff_breakdown),
                payment_methods=tuple(payment_methods),
                product_categories=tuple(product_categories),
            )

    async def _activity_buckets(
        self,
        session: sa.ext.asyncio.AsyncSession,
        start_at: datetime.datetime,
        end_at: datetime.datetime,
        limit: int | None,
        client_id: uuid.UUID | None = None,
    ) -> list[AnalyticsBucket]:
        values: dict[str, dict[str, int]] = {}

        def bucket_values(key: str) -> dict[str, int]:
            if key not in values:
                values[key] = _new_bucket()
            return values[key]

        session_filters = [
            sessions.c.status == "completed",
            sessions.c.ended_at.is_not(None),
            _period_filter(sessions.c.started_at, start_at, end_at),
        ]
        if client_id is not None:
            session_filters.append(sessions.c.client_id == client_id)
        day_bucket = sa.func.date_trunc("day", sessions.c.started_at)
        result = await session.execute(
            sa.select(
                day_bucket,
                sa.func.count(sessions.c.id),
                sa.func.coalesce(
                    sa.func.sum(
                        sa.func.extract("epoch", sessions.c.ended_at - sessions.c.started_at) / 60
                    ),
                    0,
                ),
                sa.func.count().filter(sessions.c.client_id.is_(None)),
            )
            .where(*session_filters)
            .group_by(day_bucket)
        )
        for row in result:
            item = bucket_values(row[0].date().isoformat())
            item["session_count"] = _int(row[1])
            item["played_minutes"] = _minutes(row[2])
            item["guest_session_count"] = _int(row[3])

        charge_filters = [_period_filter(charges.c.created_at, start_at, end_at)]
        if client_id is not None:
            charge_filters.append(charges.c.client_id == client_id)
        charge_day_bucket = sa.func.date_trunc("day", charges.c.created_at)
        result = await session.execute(
            sa.select(
                charge_day_bucket,
                sa.func.coalesce(sa.func.sum(charges.c.amount_cents), 0),
            )
            .where(*charge_filters)
            .group_by(charge_day_bucket)
        )
        for row in result:
            bucket_values(row[0].date().isoformat())["session_revenue_cents"] = _int(row[1])

        sale_filters = [
            sales.c.status == "completed",
            _period_filter(sales.c.created_at, start_at, end_at),
        ]
        if client_id is not None:
            sale_filters.append(sales.c.client_id == client_id)
        sale_day_bucket = sa.func.date_trunc("day", sales.c.created_at)
        result = await session.execute(
            sa.select(
                sale_day_bucket,
                sa.func.coalesce(sa.func.sum(sales.c.total_price_cents), 0),
                sa.func.count(sales.c.id),
                sa.func.coalesce(sa.func.sum(sales.c.quantity), 0),
            )
            .where(*sale_filters)
            .group_by(sale_day_bucket)
        )
        for row in result:
            item = bucket_values(row[0].date().isoformat())
            item["product_revenue_cents"] = _int(row[1])
            item["product_sale_count"] = _int(row[2])
            item["product_units"] = _int(row[3])

        result: list[AnalyticsBucket] = []
        cursor = start_at.replace(hour=0, minute=0, second=0, microsecond=0)
        last_day = (end_at - datetime.timedelta(microseconds=1)).date()
        while cursor.date() <= last_day:
            key = cursor.date().isoformat()
            result.append(_bucket(key, cursor.strftime("%d.%m"), bucket_values(key)))
            cursor += datetime.timedelta(days=1)
        return result[:limit] if limit is not None else result

    async def _hourly_activity(
        self,
        session: sa.ext.asyncio.AsyncSession,
        start_at: datetime.datetime,
        end_at: datetime.datetime,
        client_id: uuid.UUID | None = None,
    ) -> list[AnalyticsBucket]:
        values = {str(hour): _new_bucket() for hour in range(24)}
        session_filters = [
            sessions.c.status == "completed",
            sessions.c.ended_at.is_not(None),
            _period_filter(sessions.c.started_at, start_at, end_at),
        ]
        if client_id is not None:
            session_filters.append(sessions.c.client_id == client_id)
        session_hour_bucket = sa.func.extract("hour", sessions.c.started_at)
        result = await session.execute(
            sa.select(
                session_hour_bucket,
                sa.func.count(sessions.c.id),
                sa.func.coalesce(
                    sa.func.sum(
                        sa.func.extract("epoch", sessions.c.ended_at - sessions.c.started_at) / 60
                    ),
                    0,
                ),
                sa.func.count().filter(sessions.c.client_id.is_(None)),
            )
            .where(*session_filters)
            .group_by(session_hour_bucket)
        )
        for row in result:
            item = values[str(int(row[0]))]
            item["session_count"] = _int(row[1])
            item["played_minutes"] = _minutes(row[2])
            item["guest_session_count"] = _int(row[3])

        charge_filters = [_period_filter(charges.c.created_at, start_at, end_at)]
        if client_id is not None:
            charge_filters.append(charges.c.client_id == client_id)
        charge_hour_bucket = sa.func.extract("hour", charges.c.created_at)
        result = await session.execute(
            sa.select(
                charge_hour_bucket,
                sa.func.coalesce(sa.func.sum(charges.c.amount_cents), 0),
            )
            .where(*charge_filters)
            .group_by(charge_hour_bucket)
        )
        for row in result:
            values[str(int(row[0]))]["session_revenue_cents"] = _int(row[1])

        sale_filters = [
            sales.c.status == "completed",
            _period_filter(sales.c.created_at, start_at, end_at),
        ]
        if client_id is not None:
            sale_filters.append(sales.c.client_id == client_id)
        sale_hour_bucket = sa.func.extract("hour", sales.c.created_at)
        result = await session.execute(
            sa.select(
                sale_hour_bucket,
                sa.func.coalesce(sa.func.sum(sales.c.total_price_cents), 0),
                sa.func.count(sales.c.id),
                sa.func.coalesce(sa.func.sum(sales.c.quantity), 0),
            )
            .where(*sale_filters)
            .group_by(sale_hour_bucket)
        )
        for row in result:
            item = values[str(int(row[0]))]
            item["product_revenue_cents"] = _int(row[1])
            item["product_sale_count"] = _int(row[2])
            item["product_units"] = _int(row[3])
        return [_bucket(str(hour), f"{hour:02d}:00", values[str(hour)]) for hour in range(24)]

    async def _workstation_breakdown(
        self,
        session: sa.ext.asyncio.AsyncSession,
        start_at: datetime.datetime,
        end_at: datetime.datetime,
        total_revenue_cents: int,
    ) -> list[AnalyticsBreakdown]:
        duration = sa.func.extract("epoch", sessions.c.ended_at - sessions.c.started_at) / 60
        result = await session.execute(
            sa.select(
                workstations.c.id,
                workstations.c.name,
                sa.func.count(sessions.c.id),
                sa.func.coalesce(sa.func.sum(duration), 0),
                sa.func.coalesce(sa.func.sum(charges.c.amount_cents), 0),
                sa.func.coalesce(sa.func.sum(charges.c.discount_amount_cents), 0),
            )
            .select_from(
                sessions.join(
                    workstations, sessions.c.workstation_id == workstations.c.id
                ).outerjoin(charges, charges.c.session_id == sessions.c.id)
            )
            .where(
                sessions.c.status == "completed",
                sessions.c.ended_at.is_not(None),
                _period_filter(sessions.c.started_at, start_at, end_at),
            )
            .group_by(workstations.c.id, workstations.c.name)
            .order_by(sa.func.sum(duration).desc())
        )
        return [
            _breakdown(
                str(row[0]),
                row[1],
                _int(row[4]),
                0,
                0,
                _int(row[2]),
                0,
                0,
                _minutes(row[3]),
                total_revenue_cents,
                _int(row[5]),
            )
            for row in result
        ]

    async def _zone_breakdown(
        self,
        session: sa.ext.asyncio.AsyncSession,
        start_at: datetime.datetime,
        end_at: datetime.datetime,
        total_revenue_cents: int,
    ) -> list[AnalyticsBreakdown]:
        duration = sa.func.extract("epoch", sessions.c.ended_at - sessions.c.started_at) / 60
        zone_key = sa.func.coalesce(workstations.c.group_id, "unassigned")
        zone_name = sa.func.coalesce(workstation_groups.c.name, "Без зоны")
        result = await session.execute(
            sa.select(
                zone_key,
                zone_name,
                sa.func.count(sessions.c.id),
                sa.func.coalesce(sa.func.sum(duration), 0),
                sa.func.coalesce(sa.func.sum(charges.c.amount_cents), 0),
                sa.func.coalesce(sa.func.sum(charges.c.discount_amount_cents), 0),
            )
            .select_from(
                sessions.join(workstations, sessions.c.workstation_id == workstations.c.id)
                .outerjoin(workstation_groups, workstations.c.group_id == workstation_groups.c.id)
                .outerjoin(charges, charges.c.session_id == sessions.c.id)
            )
            .where(
                sessions.c.status == "completed",
                sessions.c.ended_at.is_not(None),
                _period_filter(sessions.c.started_at, start_at, end_at),
            )
            .group_by(zone_key, zone_name)
            .order_by(sa.func.sum(duration).desc())
        )
        return [
            _breakdown(
                row[0],
                row[1],
                _int(row[4]),
                0,
                0,
                _int(row[2]),
                0,
                0,
                _minutes(row[3]),
                total_revenue_cents,
                _int(row[5]),
            )
            for row in result
        ]

    async def _tariff_breakdown(
        self,
        session: sa.ext.asyncio.AsyncSession,
        start_at: datetime.datetime,
        end_at: datetime.datetime,
        total_revenue_cents: int,
    ) -> list[AnalyticsBreakdown]:
        tariff_key = sa.func.coalesce(sa.cast(tariffs.c.id, sa.String()), "unassigned")
        tariff_name = sa.func.coalesce(tariffs.c.name, "Без тарифа")
        result = await session.execute(
            sa.select(
                tariff_key,
                tariff_name,
                sa.func.count(charges.c.session_id),
                sa.func.coalesce(sa.func.sum(charges.c.duration_minutes), 0),
                sa.func.coalesce(sa.func.sum(charges.c.amount_cents), 0),
                sa.func.coalesce(sa.func.sum(charges.c.discount_amount_cents), 0),
            )
            .select_from(charges.outerjoin(tariffs, charges.c.tariff_id == tariffs.c.id))
            .where(_period_filter(charges.c.created_at, start_at, end_at))
            .group_by(tariff_key, tariff_name)
            .order_by(sa.func.sum(charges.c.amount_cents).desc())
        )
        return [
            _breakdown(
                row[0],
                row[1],
                _int(row[4]),
                0,
                0,
                _int(row[2]),
                0,
                0,
                _int(row[3]),
                total_revenue_cents,
                _int(row[5]),
            )
            for row in result
        ]

    async def _payment_breakdown(
        self,
        session: sa.ext.asyncio.AsyncSession,
        start_at: datetime.datetime,
        end_at: datetime.datetime,
        total_revenue_cents: int,
        client_id: uuid.UUID | None = None,
    ) -> list[AnalyticsPayment]:
        payments: dict[str, tuple[int, int]] = {}
        charge_filters = [_period_filter(charges.c.created_at, start_at, end_at)]
        if client_id is not None:
            charge_filters.append(charges.c.client_id == client_id)
        (balance_revenue, balance_count) = (
            await session.execute(
                sa.select(
                    sa.func.coalesce(sa.func.sum(charges.c.amount_cents), 0),
                    sa.func.count(charges.c.session_id),
                ).where(*charge_filters)
            )
        ).one()
        if _int(balance_count):
            payments["balance"] = (_int(balance_revenue), _int(balance_count))

        sale_filters = [
            sales.c.status == "completed",
            _period_filter(sales.c.created_at, start_at, end_at),
        ]
        if client_id is not None:
            sale_filters.append(sales.c.client_id == client_id)
        result = await session.execute(
            sa.select(
                sales.c.payment_method,
                sa.func.coalesce(sa.func.sum(sales.c.total_price_cents), 0),
                sa.func.count(sales.c.id),
            )
            .where(*sale_filters)
            .group_by(sales.c.payment_method)
        )
        for row in result:
            payments[row[0]] = (_int(row[1]), _int(row[2]))

        labels = {"balance": "С баланса", "cash": "Наличные"}
        return [
            AnalyticsPayment(
                key=key,
                label=labels.get(key, key),
                revenue_cents=revenue,
                operation_count=count,
                share_bps=_share_bps(revenue, total_revenue_cents),
            )
            for key, (revenue, count) in sorted(
                payments.items(), key=lambda item: item[1][0], reverse=True
            )
        ]

    async def _product_category_breakdown(
        self,
        session: sa.ext.asyncio.AsyncSession,
        start_at: datetime.datetime,
        end_at: datetime.datetime,
        total_revenue_cents: int,
    ) -> list[AnalyticsBreakdown]:
        result = await session.execute(
            sa.select(
                sales.c.product_category,
                sa.func.sum(sales.c.total_price_cents),
                sa.func.sum(sales.c.unit_cost_price_cents * sales.c.quantity),
                sa.func.count(sales.c.id),
                sa.func.sum(sales.c.quantity),
            )
            .where(
                sales.c.status == "completed",
                _period_filter(sales.c.created_at, start_at, end_at),
            )
            .group_by(sales.c.product_category)
            .order_by(sa.func.sum(sales.c.total_price_cents).desc())
        )
        return [
            _breakdown(
                str(row[0]),
                str(row[0]),
                0,
                _int(row[1]),
                _int(row[2]),
                0,
                _int(row[3]),
                _int(row[4]),
                0,
                total_revenue_cents,
            )
            for row in result
        ]

    async def _top_products(
        self,
        session: sa.ext.asyncio.AsyncSession,
        start_at: datetime.datetime,
        end_at: datetime.datetime,
        limit: int,
    ) -> list[TopProduct]:
        result = await session.execute(
            sa.select(
                sales.c.product_id,
                sales.c.product_name,
                sa.func.sum(sales.c.quantity),
                sa.func.sum(sales.c.total_price_cents),
                sa.func.sum(
                    sales.c.total_price_cents - sales.c.unit_cost_price_cents * sales.c.quantity
                ),
            )
            .where(
                sales.c.status == "completed",
                _period_filter(sales.c.created_at, start_at, end_at),
            )
            .group_by(sales.c.product_id, sales.c.product_name)
            .order_by(sa.func.sum(sales.c.total_price_cents).desc())
            .limit(limit)
        )
        return [
            TopProduct(
                product_id=row[0],
                product_name=row[1],
                units=int(row[2] or 0),
                revenue_cents=int(row[3] or 0),
                gross_profit_cents=int(row[4] or 0),
            )
            for row in result
        ]

    async def _top_clients(
        self,
        session: sa.ext.asyncio.AsyncSession,
        start_at: datetime.datetime,
        end_at: datetime.datetime,
        limit: int,
    ) -> list[TopClient]:
        session_totals = (
            sa.select(
                sessions.c.client_id.label("client_id"),
                sa.func.count(sessions.c.id).label("session_count"),
                sa.func.coalesce(
                    sa.func.sum(
                        sa.func.extract("epoch", sessions.c.ended_at - sessions.c.started_at) / 60
                    ),
                    0,
                ).label("played_minutes"),
            )
            .where(
                sessions.c.status == "completed",
                sessions.c.client_id.is_not(None),
                sessions.c.ended_at.is_not(None),
                _period_filter(sessions.c.started_at, start_at, end_at),
            )
            .group_by(sessions.c.client_id)
            .subquery()
        )
        charge_totals = (
            sa.select(
                charges.c.client_id.label("client_id"),
                sa.func.coalesce(sa.func.sum(charges.c.amount_cents), 0).label("session_spend"),
            )
            .where(_period_filter(charges.c.created_at, start_at, end_at))
            .group_by(charges.c.client_id)
            .subquery()
        )
        product_totals = (
            sa.select(
                sales.c.client_id.label("client_id"),
                sa.func.coalesce(sa.func.sum(sales.c.total_price_cents), 0).label("product_spend"),
                sa.func.coalesce(sa.func.sum(sales.c.quantity), 0).label("product_units"),
            )
            .where(
                sales.c.status == "completed",
                sales.c.client_id.is_not(None),
                _period_filter(sales.c.created_at, start_at, end_at),
            )
            .group_by(sales.c.client_id)
            .subquery()
        )
        result = await session.execute(
            sa.select(
                clients.c.id,
                clients.c.nickname,
                sa.func.coalesce(session_totals.c.session_count, 0),
                sa.func.coalesce(session_totals.c.played_minutes, 0),
                sa.func.coalesce(charge_totals.c.session_spend, 0),
                sa.func.coalesce(product_totals.c.product_spend, 0),
                sa.func.coalesce(product_totals.c.product_units, 0),
            )
            .select_from(
                clients.outerjoin(session_totals, clients.c.id == session_totals.c.client_id)
                .outerjoin(charge_totals, clients.c.id == charge_totals.c.client_id)
                .outerjoin(product_totals, clients.c.id == product_totals.c.client_id)
            )
            .where(
                clients.c.blocked_at.is_(None),
                sa.or_(
                    session_totals.c.client_id.is_not(None),
                    charge_totals.c.client_id.is_not(None),
                    product_totals.c.client_id.is_not(None),
                ),
            )
            .order_by(
                (
                    sa.func.coalesce(charge_totals.c.session_spend, 0)
                    + sa.func.coalesce(product_totals.c.product_spend, 0)
                ).desc()
            )
            .limit(limit)
        )
        return [
            TopClient(
                client_id=row[0],
                nickname=row[1],
                session_count=_int(row[2]),
                played_minutes=_minutes(row[3]),
                session_spend_cents=_int(row[4]),
                product_spend_cents=_int(row[5]),
                product_units=_int(row[6]),
            )
            for row in result
        ]

    async def client(
        self,
        client_id: uuid.UUID,
        start_at: datetime.datetime,
        end_at: datetime.datetime,
        limit: int,
    ) -> ClientAnalytics | None:
        async with open_session(self._engine_provider) as session:
            client_row = (
                await session.execute(
                    sa.select(clients.c.id, clients.c.nickname, clients.c.phone).where(
                        clients.c.id == client_id
                    )
                )
            ).one_or_none()
            if client_row is None:
                return None
            session_stats = (
                await session.execute(
                    sa.select(
                        sa.func.count(sessions.c.id),
                        sa.func.coalesce(
                            sa.func.sum(
                                sa.func.extract(
                                    "epoch", sessions.c.ended_at - sessions.c.started_at
                                )
                                / 60
                            ),
                            0,
                        ),
                        sa.func.min(sessions.c.started_at),
                        sa.func.max(sessions.c.started_at),
                    ).where(
                        sessions.c.client_id == client_id,
                        sessions.c.status == "completed",
                        sessions.c.ended_at.is_not(None),
                        _period_filter(sessions.c.started_at, start_at, end_at),
                    )
                )
            ).one()
            (session_spend,) = (
                await session.execute(
                    sa.select(sa.func.coalesce(sa.func.sum(charges.c.amount_cents), 0)).where(
                        charges.c.client_id == client_id,
                        _period_filter(charges.c.created_at, start_at, end_at),
                    )
                )
            ).one()
            product_stats = (
                await session.execute(
                    sa.select(
                        sa.func.coalesce(sa.func.sum(sales.c.total_price_cents), 0),
                        sa.func.coalesce(
                            sa.func.sum(sales.c.unit_cost_price_cents * sales.c.quantity), 0
                        ),
                        sa.func.coalesce(sa.func.sum(sales.c.quantity), 0),
                        sa.func.max(sales.c.created_at),
                    ).where(
                        sales.c.client_id == client_id,
                        sales.c.status == "completed",
                        _period_filter(sales.c.created_at, start_at, end_at),
                    )
                )
            ).one()
            favorite_products = await self._top_products_for_client(
                session, client_id, start_at, end_at, limit
            )
            return ClientAnalytics(
                client_id=client_row[0],
                nickname=client_row[1],
                phone=client_row[2],
                start_at=start_at,
                end_at=end_at,
                played_minutes=int(float(session_stats[1] or 0)),
                session_count=int(session_stats[0] or 0),
                session_spend_cents=int(session_spend or 0),
                product_spend_cents=int(product_stats[0] or 0),
                product_units=int(product_stats[2] or 0),
                first_session_at=session_stats[2],
                last_session_at=session_stats[3],
                last_purchase_at=product_stats[3],
                favorite_products=tuple(favorite_products),
                product_cost_cents=_int(product_stats[1]),
                daily_activity=tuple(
                    await self._activity_buckets(
                        session, start_at, end_at, limit=None, client_id=client_id
                    )
                ),
                payment_methods=tuple(
                    await self._payment_breakdown(
                        session,
                        start_at,
                        end_at,
                        _int(session_spend) + _int(product_stats[0]),
                        client_id,
                    )
                ),
            )

    async def _top_products_for_client(
        self,
        session: sa.ext.asyncio.AsyncSession,
        client_id: uuid.UUID,
        start_at: datetime.datetime,
        end_at: datetime.datetime,
        limit: int,
    ) -> list[TopProduct]:
        result = await session.execute(
            sa.select(
                sales.c.product_id,
                sales.c.product_name,
                sa.func.sum(sales.c.quantity),
                sa.func.sum(sales.c.total_price_cents),
                sa.func.sum(
                    sales.c.total_price_cents - sales.c.unit_cost_price_cents * sales.c.quantity
                ),
            )
            .where(
                sales.c.client_id == client_id,
                sales.c.status == "completed",
                _period_filter(sales.c.created_at, start_at, end_at),
            )
            .group_by(sales.c.product_id, sales.c.product_name)
            .order_by(sa.func.sum(sales.c.quantity).desc())
            .limit(limit)
        )
        return [
            TopProduct(
                product_id=row[0],
                product_name=row[1],
                units=int(row[2] or 0),
                revenue_cents=int(row[3] or 0),
                gross_profit_cents=int(row[4] or 0),
            )
            for row in result
        ]
