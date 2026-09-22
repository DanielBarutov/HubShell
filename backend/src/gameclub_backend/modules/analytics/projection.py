from __future__ import annotations

import typing
import uuid

from gameclub_backend.modules.analytics.heavy_events import AnalyticsOutboxEvent, projection_delta


class AnalyticsHeavyRepository(typing.Protocol):
    async def append_event(self, event: AnalyticsOutboxEvent) -> AnalyticsOutboxEvent: ...

    async def list_unapplied_events(self, limit: int) -> tuple[AnalyticsOutboxEvent, ...]: ...

    async def list_events(self) -> tuple[AnalyticsOutboxEvent, ...]: ...

    async def apply_event(self, event: AnalyticsOutboxEvent) -> bool: ...

    async def rebuild_projection(self) -> None: ...

    async def read_projection(
        self, metric_key: str | None = None
    ) -> tuple[dict[str, object], ...]: ...


class AnalyticsProjectionService:
    def __init__(self, repository: AnalyticsHeavyRepository) -> None:
        self._repository = repository

    async def publish(self, event: AnalyticsOutboxEvent) -> AnalyticsOutboxEvent:
        return await self._repository.append_event(event)

    async def consume_once(self, limit: int = 100) -> int:
        if limit <= 0:
            raise ValueError("Projection batch limit must be positive")
        applied = 0
        for event in await self._repository.list_unapplied_events(limit):
            if await self._repository.apply_event(event):
                applied += 1
        return applied

    async def rebuild(self) -> None:
        await self._repository.rebuild_projection()

    async def read(self, metric_key: str | None = None) -> tuple[dict[str, object], ...]:
        return await self._repository.read_projection(metric_key)

    async def read_total(self, metric_key: str) -> int:
        rows = await self.read(metric_key)
        return sum(_as_int(row["value_cents"]) for row in rows)

    async def read_count(self, metric_key: str) -> int:
        rows = await self.read(metric_key)
        return sum(_as_int(row["event_count"]) for row in rows)

    async def event_count(self) -> int:
        rows = await self.read()
        return sum(_as_int(row["event_count"]) for row in rows)

    async def reconcile(self, metric_key: str | None = None) -> bool:
        before = await self.read(metric_key)
        await self.rebuild()
        if before != await self.read(metric_key):
            return False
        direct_totals: dict[str, int] = {}
        for event in await self._repository.list_events():
            delta = projection_delta(event)
            if delta is not None:
                direct_totals[delta[0]] = direct_totals.get(delta[0], 0) + delta[1]
        keys = {metric_key} if metric_key is not None else set(direct_totals)
        for key in keys:
            if direct_totals.get(key, 0) != await self.read_total(key):
                return False
        return True

    async def publish_fact(
        self,
        *,
        event_type: str,
        aggregate_type: str,
        aggregate_id: str,
        occurred_at: typing.Any,
        idempotency_key: str,
        payload: dict[str, object],
    ) -> AnalyticsOutboxEvent:
        from gameclub_backend.modules.analytics.heavy_events import (
            AnalyticsEventType,
            event_from_payload,
        )

        return await self.publish(
            event_from_payload(
                event_id=uuid.uuid4(),
                event_type=AnalyticsEventType(event_type),
                aggregate_type=aggregate_type,
                aggregate_id=aggregate_id,
                occurred_at=occurred_at,
                idempotency_key=idempotency_key,
                payload=payload,
            )
        )


def _as_int(value: object) -> int:
    return int(value) if isinstance(value, (int, float, str)) else 0
