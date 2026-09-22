from __future__ import annotations

import datetime
import enum
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from zoneinfo import ZoneInfo


class AnalyticsEventType(enum.StrEnum):
    FINANCIAL_FACT = "financial_fact"
    SESSION_COMPLETED = "session_completed"
    PRODUCT_SALE_COMPLETED = "product_sale_completed"


SUPPORTED_EVENT_VERSIONS: dict[AnalyticsEventType, frozenset[int]] = {
    event_type: frozenset({1}) for event_type in AnalyticsEventType
}
MOSCOW = ZoneInfo("Europe/Moscow")


@dataclass(frozen=True, slots=True)
class AnalyticsOutboxEvent:
    id: uuid.UUID
    event_type: AnalyticsEventType
    event_version: int
    aggregate_type: str
    aggregate_id: str
    occurred_at: datetime.datetime
    idempotency_key: str
    payload: dict[str, object]
    created_at: datetime.datetime

    def __post_init__(self) -> None:
        if self.event_version not in SUPPORTED_EVENT_VERSIONS[self.event_type]:
            raise ValueError(f"Unsupported analytics event version: {self.event_version}")
        if self.occurred_at.tzinfo is None or self.created_at.tzinfo is None:
            raise ValueError("Analytics event timestamps require timezone")
        if not self.aggregate_type.strip() or not self.aggregate_id.strip():
            raise ValueError("Analytics event aggregate reference is required")
        if not self.idempotency_key.strip():
            raise ValueError("Analytics event idempotency key is required")
        object.__setattr__(self, "aggregate_type", self.aggregate_type.strip())
        object.__setattr__(self, "aggregate_id", self.aggregate_id.strip())
        object.__setattr__(self, "idempotency_key", self.idempotency_key.strip())
        object.__setattr__(self, "occurred_at", self.occurred_at.astimezone(datetime.UTC))
        object.__setattr__(self, "created_at", self.created_at.astimezone(datetime.UTC))
        object.__setattr__(self, "payload", dict(self.payload))


def event_from_payload(
    *,
    event_id: uuid.UUID,
    event_type: AnalyticsEventType,
    aggregate_type: str,
    aggregate_id: str,
    occurred_at: datetime.datetime,
    idempotency_key: str,
    payload: Mapping[str, object],
    created_at: datetime.datetime | None = None,
    event_version: int = 1,
) -> AnalyticsOutboxEvent:
    return AnalyticsOutboxEvent(
        id=event_id,
        event_type=event_type,
        event_version=event_version,
        aggregate_type=aggregate_type,
        aggregate_id=aggregate_id,
        occurred_at=occurred_at,
        idempotency_key=idempotency_key,
        payload=dict(payload),
        created_at=created_at or datetime.datetime.now(datetime.UTC),
    )


def projection_delta(
    event: AnalyticsOutboxEvent,
) -> tuple[str, int, int, dict[str, str]] | None:
    payload = event.payload
    status = str(payload.get("status", "confirmed")).lower()
    if event.event_type is AnalyticsEventType.FINANCIAL_FACT and status not in {
        "completed",
        "confirmed",
    }:
        return None

    metric_key = str(payload.get("metric_key", "")).strip()
    if not metric_key:
        metric_key = {
            AnalyticsEventType.FINANCIAL_FACT: "revenue_cents",
            AnalyticsEventType.SESSION_COMPLETED: "session_minutes",
            AnalyticsEventType.PRODUCT_SALE_COMPLETED: "product_revenue_cents",
        }[event.event_type]
    value_cents = _as_int(payload.get("value_cents", payload.get("amount_cents", 0)))
    quantity = _as_int(payload.get("quantity", 1))
    dimensions = {
        str(key): str(value)
        for key, value in payload.items()
        if key in {"payment_method", "zone", "workstation", "tariff", "category", "product"}
        and value is not None
    }
    return metric_key, value_cents, quantity, dimensions


def _as_int(value: object) -> int:
    return int(value) if isinstance(value, (int, float, str)) else 0


def bucket_start(occurred_at: datetime.datetime) -> datetime.datetime:
    local = occurred_at.astimezone(MOSCOW).replace(hour=0, minute=0, second=0, microsecond=0)
    return local.astimezone(datetime.UTC)
