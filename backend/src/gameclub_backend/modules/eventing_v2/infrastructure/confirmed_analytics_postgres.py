"""Один commit для logical analytics inbox и analytics outbox."""

from __future__ import annotations

import dataclasses
import datetime
import json
import uuid

import sqlalchemy as sa

from gameclub_backend.infrastructure.database import EngineProvider, open_session
from gameclub_backend.modules.eventing_v2.application.analytics import (
    V2ConfirmedEventAnalyticsService,
)
from gameclub_backend.modules.eventing_v2.domain import (
    V2Event,
    V2EventType,
    V2InboxResult,
    V2InboxStatus,
)
from gameclub_backend.modules.eventing_v2.infrastructure.postgres import (
    V2EventInboxModel,
    V2EventingBase,
)
from gameclub_backend.modules.eventing_v2.infrastructure.reconciliation_postgres import (
    V2ConfirmedClientFactModel,
    confirmed_per_minute_debit_event,
)

CONSUMER_NAME = "confirmed_analytics"
PER_MINUTE_DEBIT_BACKFILL = "v2_confirmed_per_minute_debits_v1"


@dataclasses.dataclass(frozen=True)
class V2ConfirmedAnalyticsBackfillResult:
    """Результат одной ограниченной порции immutable V2-фактов."""

    accepted_count: int
    duplicate_count: int
    skipped_count: int
    completed: bool


class V2AnalyticsBackfillRunModel(V2EventingBase):
    __tablename__ = "v2_analytics_backfill_runs"

    name: sa.orm.Mapped[str] = sa.orm.mapped_column(sa.String(128), primary_key=True)
    status: sa.orm.Mapped[str] = sa.orm.mapped_column(sa.String(32), nullable=False)
    cutoff_confirmed_at: sa.orm.Mapped[datetime.datetime | None] = sa.orm.mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )
    cutoff_event_id: sa.orm.Mapped[uuid.UUID | None] = sa.orm.mapped_column(
        sa.dialects.postgresql.UUID(as_uuid=True), nullable=True
    )
    cursor_confirmed_at: sa.orm.Mapped[datetime.datetime | None] = sa.orm.mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )
    cursor_event_id: sa.orm.Mapped[uuid.UUID | None] = sa.orm.mapped_column(
        sa.dialects.postgresql.UUID(as_uuid=True), nullable=True
    )
    created_at: sa.orm.Mapped[datetime.datetime] = sa.orm.mapped_column(sa.DateTime(timezone=True))
    updated_at: sa.orm.Mapped[datetime.datetime] = sa.orm.mapped_column(sa.DateTime(timezone=True))


class V2AnalyticsBackfillSkipModel(V2EventingBase):
    __tablename__ = "v2_analytics_backfill_skips"

    backfill_name: sa.orm.Mapped[str] = sa.orm.mapped_column(sa.String(128), primary_key=True)
    source_event_id: sa.orm.Mapped[uuid.UUID] = sa.orm.mapped_column(
        sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True
    )
    reason: sa.orm.Mapped[str] = sa.orm.mapped_column(sa.String(128), nullable=False)
    recorded_at: sa.orm.Mapped[datetime.datetime] = sa.orm.mapped_column(sa.DateTime(timezone=True))


class PostgresV2ConfirmedAnalyticsRepository:
    """Аналитика не меняет деньги; Kafka offset ждёт одного durable commit."""

    def __init__(self, engine_provider: EngineProvider) -> None:
        self._engine_provider = engine_provider

    async def accept(self, event: V2Event) -> V2InboxResult:
        async with open_session(self._engine_provider) as session:
            async with session.begin():
                return await self._accept_in_transaction(session, event)

    async def _accept_in_transaction(self, session, event: V2Event) -> V2InboxResult:
        analytics_events = V2ConfirmedEventAnalyticsService.events_for(event)
        existing = await session.scalar(
            sa.select(V2EventInboxModel).where(
                V2EventInboxModel.consumer_name == CONSUMER_NAME,
                V2EventInboxModel.producer_id == event.producer_id,
                V2EventInboxModel.operation_id == event.operation_id,
            )
        )
        if existing is not None:
            stored = existing.to_domain()
            if stored.payload_hash != event.payload_hash or stored.event_type != event.event_type:
                return V2InboxResult(
                    V2InboxStatus.CONFLICT,
                    stored.event_id,
                    event.operation_id,
                    "operation_id уже принадлежит другому confirmed событию",
                )
            return V2InboxResult(
                V2InboxStatus.DUPLICATE,
                stored.event_id,
                event.operation_id,
                "Confirmed V2-событие уже учтено аналитикой",
            )

        session.add(V2EventInboxModel(**V2EventInboxModel.values_from_domain(CONSUMER_NAME, event)))
        for item in analytics_events:
            await session.execute(
                sa.text(
                    """
                    INSERT INTO analytics_outbox_events
                      (id, event_type, event_version, aggregate_type, aggregate_id,
                       occurred_at, idempotency_key, payload, created_at)
                    VALUES (
                      :id, :event_type, :event_version, :aggregate_type,
                      :aggregate_id, :occurred_at, :idempotency_key,
                      CAST(:payload AS jsonb), :created_at
                    )
                    ON CONFLICT (idempotency_key) DO NOTHING
                    """
                ),
                {
                    "id": item.id,
                    "event_type": item.event_type.value,
                    "event_version": item.event_version,
                    "aggregate_type": item.aggregate_type,
                    "aggregate_id": item.aggregate_id,
                    "occurred_at": item.occurred_at,
                    "idempotency_key": item.idempotency_key,
                    "payload": json.dumps(item.payload, sort_keys=True),
                    "created_at": item.created_at,
                },
            )
        return V2InboxResult(
            V2InboxStatus.ACCEPTED,
            event.event_id,
            event.operation_id,
            "Confirmed V2-событие передано в analytics outbox",
        )

    async def backfill_per_minute_debits(
        self,
        limit: int = 100,
    ) -> V2ConfirmedAnalyticsBackfillResult:
        """Дописать аналитику только для server-confirmed immutable source facts.

        Сырые Kafka client events сюда не попадают. Legacy факты без актуального
        `amount_cents` не выбираются: их семантика не угадывается и остаётся
        предметом отдельной ручной миграции.
        """
        if limit <= 0:
            raise ValueError("V2 analytics backfill limit must be positive")

        async with open_session(self._engine_provider) as session:
            async with session.begin():
                now = datetime.datetime.now(datetime.UTC)
                await session.execute(
                    sa.dialects.postgresql.insert(V2AnalyticsBackfillRunModel)
                    .values(
                        name=PER_MINUTE_DEBIT_BACKFILL,
                        status="pending",
                        created_at=now,
                        updated_at=now,
                    )
                    .on_conflict_do_nothing()
                )
                run = await session.scalar(
                    sa.select(V2AnalyticsBackfillRunModel)
                    .where(V2AnalyticsBackfillRunModel.name == PER_MINUTE_DEBIT_BACKFILL)
                    .with_for_update()
                )
                if run is None:
                    raise RuntimeError("V2 analytics backfill run was not created")
                if run.status == "completed":
                    return V2ConfirmedAnalyticsBackfillResult(0, 0, 0, True)
                if run.cutoff_confirmed_at is None or run.cutoff_event_id is None:
                    last = await session.scalar(
                        sa.select(V2ConfirmedClientFactModel)
                        .where(
                            V2ConfirmedClientFactModel.event_type
                            == V2EventType.PER_MINUTE_DEBIT.value
                        )
                        .order_by(
                            V2ConfirmedClientFactModel.confirmed_at.desc(),
                            V2ConfirmedClientFactModel.event_id.desc(),
                        )
                        .limit(1)
                    )
                    if last is None:
                        run.status = "completed"
                        run.updated_at = now
                        return V2ConfirmedAnalyticsBackfillResult(0, 0, 0, True)
                    run.cutoff_confirmed_at = last.confirmed_at
                    run.cutoff_event_id = last.event_id

                conditions = [
                    V2ConfirmedClientFactModel.event_type == V2EventType.PER_MINUTE_DEBIT.value,
                    sa.or_(
                        V2ConfirmedClientFactModel.confirmed_at < run.cutoff_confirmed_at,
                        sa.and_(
                            V2ConfirmedClientFactModel.confirmed_at == run.cutoff_confirmed_at,
                            V2ConfirmedClientFactModel.event_id <= run.cutoff_event_id,
                        ),
                    ),
                ]
                if run.cursor_confirmed_at is not None and run.cursor_event_id is not None:
                    conditions.append(
                        sa.or_(
                            V2ConfirmedClientFactModel.confirmed_at > run.cursor_confirmed_at,
                            sa.and_(
                                V2ConfirmedClientFactModel.confirmed_at == run.cursor_confirmed_at,
                                V2ConfirmedClientFactModel.event_id > run.cursor_event_id,
                            ),
                        )
                    )
                source_facts = tuple(
                    await session.scalars(
                        sa.select(V2ConfirmedClientFactModel)
                        .where(*conditions)
                        .order_by(
                            V2ConfirmedClientFactModel.confirmed_at,
                            V2ConfirmedClientFactModel.event_id,
                        )
                        .limit(limit)
                    )
                )
                accepted_count = duplicate_count = skipped_count = 0
                for source_fact in source_facts:
                    try:
                        event = confirmed_per_minute_debit_event(
                            source_fact.to_domain(), source_fact.confirmed_at
                        )
                    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
                        session.add(
                            V2AnalyticsBackfillSkipModel(
                                backfill_name=PER_MINUTE_DEBIT_BACKFILL,
                                source_event_id=source_fact.event_id,
                                reason="legacy_or_invalid_per_minute_payload",
                                recorded_at=now,
                            )
                        )
                        skipped_count += 1
                    else:
                        result = await self._accept_in_transaction(session, event)
                        if result.status is V2InboxStatus.ACCEPTED:
                            accepted_count += 1
                        elif result.status is V2InboxStatus.DUPLICATE:
                            duplicate_count += 1
                        else:
                            session.add(
                                V2AnalyticsBackfillSkipModel(
                                    backfill_name=PER_MINUTE_DEBIT_BACKFILL,
                                    source_event_id=source_fact.event_id,
                                    reason="analytics_operation_conflict",
                                    recorded_at=now,
                                )
                            )
                            skipped_count += 1
                    run.cursor_confirmed_at = source_fact.confirmed_at
                    run.cursor_event_id = source_fact.event_id
                run.updated_at = now
                if len(source_facts) < limit:
                    run.status = "completed"
                else:
                    run.status = "running"
                return V2ConfirmedAnalyticsBackfillResult(
                    accepted_count,
                    duplicate_count,
                    skipped_count,
                    run.status == "completed",
                )
