"""Перевод только подтверждённых серверных V2-фактов в аналитические события."""

from __future__ import annotations

import json
import uuid

from gameclub_backend.modules.analytics.heavy_events import (
    AnalyticsEventType,
    AnalyticsOutboxEvent,
    event_from_payload,
)
from gameclub_backend.modules.analytics.projection import AnalyticsProjectionService
from gameclub_backend.modules.eventing_v2.application.service import V2InboxService
from gameclub_backend.modules.eventing_v2.domain import (
    V2Event,
    V2EventType,
    V2InboxResult,
    V2InboxStatus,
)


class V2ConfirmedEventAnalyticsService:
    """Не меняет деньги или сессию; сохраняет готовые server-confirmed факты."""

    def __init__(self, projection: AnalyticsProjectionService) -> None:
        self._projection = projection

    async def ingest(self, event: V2Event) -> tuple[AnalyticsOutboxEvent, ...]:
        analytics_events = self.events_for(event)
        persisted: list[AnalyticsOutboxEvent] = []
        for item in analytics_events:
            persisted.append(await self._projection.publish(item))
        return tuple(persisted)

    @classmethod
    def events_for(cls, event: V2Event) -> tuple[AnalyticsOutboxEvent, ...]:
        if not event.producer_id.startswith("server:"):
            raise ValueError("Analytics accepts only server-confirmed V2 events")
        if event.event_type is V2EventType.BALANCE_CREDIT_APPLIED:
            return cls._deposit_events(event)
        if event.event_type is V2EventType.PER_MINUTE_DEBIT:
            return (cls._per_minute_debit_event(event),)
        return ()

    @classmethod
    def _deposit_events(cls, event: V2Event) -> tuple[AnalyticsOutboxEvent, ...]:
        payload = cls._deposit_payload(event)
        return tuple(
            event_from_payload(
                event_id=uuid.uuid5(event.event_id, f"payment-part:{index}"),
                event_type=AnalyticsEventType.FINANCIAL_FACT,
                aggregate_type="v2_deposit_credit",
                aggregate_id=str(event.operation_id),
                occurred_at=event.occurred_at,
                idempotency_key=f"v2-confirmed-deposit:{event.operation_id}:{index}",
                payload={
                    "amount_cents": amount_cents,
                    "currency": payload["currency"],
                    "metric_key": "deposit_income_cents",
                    "payment_method": method,
                    "status": "confirmed",
                },
            )
            for index, (method, amount_cents) in enumerate(payload["payment_parts"])
        )

    @classmethod
    def _per_minute_debit_event(cls, event: V2Event) -> AnalyticsOutboxEvent:
        payload = cls._per_minute_debit_payload(event)
        return event_from_payload(
            event_id=uuid.uuid5(event.event_id, "per-minute-debit"),
            event_type=AnalyticsEventType.FINANCIAL_FACT,
            aggregate_type="v2_per_minute_debit",
            aggregate_id=str(event.operation_id),
            occurred_at=event.occurred_at,
            idempotency_key=f"v2-confirmed-per-minute-debit:{event.operation_id}",
            payload={
                "amount_cents": payload["amount_cents"],
                "metric_key": "wallet_debit_cents",
                "status": "confirmed",
                "tariff": payload["tariff_id"],
            },
        )

    @staticmethod
    def _deposit_payload(event: V2Event) -> dict[str, object]:
        try:
            payload = json.loads(event.payload_json)
        except json.JSONDecodeError as error:
            raise ValueError("Confirmed deposit payload is invalid") from error
        if not isinstance(payload, dict):
            raise ValueError("Confirmed deposit payload must be an object")
        if payload.get("deposit_operation_id") != str(event.operation_id):
            raise ValueError("Confirmed deposit operation id does not match envelope")
        amount = payload.get("amount_delta_cents")
        currency = payload.get("currency")
        parts = payload.get("payment_parts")
        if not isinstance(amount, int) or isinstance(amount, bool) or amount <= 0:
            raise ValueError("Confirmed deposit amount is invalid")
        if not isinstance(currency, str) or len(currency) != 3:
            raise ValueError("Confirmed deposit currency is invalid")
        if not isinstance(parts, list) or not parts:
            raise ValueError("Confirmed deposit payment parts are required")
        normalized_parts: list[tuple[str, int]] = []
        for part in parts:
            if not isinstance(part, dict):
                raise ValueError("Confirmed deposit payment part is invalid")
            method = part.get("method")
            part_amount = part.get("amount_cents")
            if not isinstance(method, str) or not method.strip():
                raise ValueError("Confirmed deposit payment method is invalid")
            if (
                not isinstance(part_amount, int)
                or isinstance(part_amount, bool)
                or part_amount <= 0
            ):
                raise ValueError("Confirmed deposit payment amount is invalid")
            normalized_parts.append((method.strip(), part_amount))
        if sum(part[1] for part in normalized_parts) != amount:
            raise ValueError("Confirmed deposit payment parts total does not match amount")
        return {"currency": currency, "payment_parts": tuple(normalized_parts)}

    @staticmethod
    def _per_minute_debit_payload(event: V2Event) -> dict[str, object]:
        try:
            payload = json.loads(event.payload_json)
        except json.JSONDecodeError as error:
            raise ValueError("Confirmed per-minute debit payload is invalid") from error
        if not isinstance(payload, dict):
            raise ValueError("Confirmed per-minute debit payload must be an object")
        amount_cents = payload.get("amount_cents")
        tariff_id = payload.get("tariff_id")
        source_event_id = payload.get("source_event_id")
        source_event_type = payload.get("source_event_type")
        source_payload_hash = payload.get("source_payload_hash")
        if not isinstance(amount_cents, int) or isinstance(amount_cents, bool) or amount_cents <= 0:
            raise ValueError("Confirmed per-minute debit amount is invalid")
        if not isinstance(tariff_id, str) or not tariff_id.strip():
            raise ValueError("Confirmed per-minute debit tariff is invalid")
        if not isinstance(source_event_id, str) or not source_event_id.strip():
            raise ValueError("Confirmed per-minute debit source event is invalid")
        if source_event_type != V2EventType.PER_MINUTE_DEBIT.value:
            raise ValueError("Confirmed per-minute debit source type is invalid")
        if not isinstance(source_payload_hash, str) or len(source_payload_hash) != 64:
            raise ValueError("Confirmed per-minute debit source hash is invalid")
        return {"amount_cents": amount_cents, "tariff_id": tariff_id.strip()}


class V2ConfirmedAnalyticsInboxService:
    """Логический inbox analytics; повтор продолжает незавершённую доставку."""

    def __init__(
        self,
        inbox: V2InboxService,
        analytics: V2ConfirmedEventAnalyticsService,
    ) -> None:
        self._inbox = inbox
        self._analytics = analytics

    async def accept(self, event: V2Event) -> V2InboxResult:
        result = await self._inbox.accept(event)
        if result.status is V2InboxStatus.CONFLICT:
            return result
        # Повторно запускаем идемпотентную запись: это закрывает окно, когда
        # inbox закоммитился, а analytics outbox ещё не успел сохраниться.
        await self._analytics.ingest(event)
        return result
