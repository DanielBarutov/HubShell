from __future__ import annotations

import datetime
import logging
import typing

from faststream.kafka import KafkaBroker

from gameclub_backend.modules.eventing_v2.application.outbox import V2ServerOutboxService
from gameclub_backend.modules.eventing_v2.application.reconciliation import (
    V2ClientFactResult,
    V2ClientFactStatus,
)
from gameclub_backend.modules.eventing_v2.domain import (
    V2Event,
    V2InboxResult,
    V2InboxStatus,
    V2OutgoingServerEvent,
)
from gameclub_backend.modules.eventing_v2.infrastructure.protobuf import (
    event_from_protobuf_bytes,
    event_to_protobuf,
)

logger = logging.getLogger(__name__)


class V2EventPublisher(typing.Protocol):
    """Отправка одного неизменяемого V2-факта в Kafka."""

    async def publish(self, event: V2OutgoingServerEvent) -> None:
        """Дождаться подтверждения Kafka или выбросить ошибку."""


class FastStreamV2EventPublisher:
    """Адаптер FastStream: транспорт не принимает бизнес-решений."""

    def __init__(self, broker: KafkaBroker) -> None:
        self._broker = broker

    async def publish(self, event: V2OutgoingServerEvent) -> None:
        envelope = event.event
        await self._broker.publish(
            event_to_protobuf(envelope).SerializeToString(),
            topic=event.topic,
            key=event.partition_key.encode("utf-8"),
            correlation_id=str(envelope.operation_id),
            headers={
                "event_id": str(envelope.event_id),
                "event_type": envelope.event_type.value,
                "schema_version": str(envelope.schema_version),
                "traceparent": envelope.traceparent or "",
            },
        )


class V2ServerOutboxPublisher:
    """Повторно отправить из постоянной очереди только подтверждённые факты."""

    def __init__(
        self,
        outbox: V2ServerOutboxService,
        publisher: V2EventPublisher,
    ) -> None:
        self._outbox = outbox
        self._publisher = publisher

    async def publish_pending(self, limit: int = 100) -> int:
        """Записать результат Kafka в outbox; не терять запись при ошибке транспорта."""
        published = 0
        for event in await self._outbox.pending(limit):
            try:
                await self._publisher.publish(event)
            except Exception as error:
                await self._outbox.record_publish_failure(event, str(error))
            else:
                await self._outbox.mark_published(event, datetime.datetime.now(datetime.UTC))
                published += 1
        return published


class V2ClientFactsHandler(typing.Protocol):
    """Бизнес-обработчик факта клиентской сессии после проверки конверта."""

    async def accept(self, event: V2Event) -> V2ClientFactResult:
        """Зафиксировать inbox и бизнес-результат одной транзакцией."""


class V2RejectedEventPublisher(typing.Protocol):
    """Записать не принятый факт в закрытый DLQ до Kafka offset commit."""

    async def publish_rejected(self, payload: bytes, reason_code: str) -> None:
        """Подтвердить перенос исходного Kafka payload в V2 failed-events."""


class FastStreamV2RejectedEventPublisher:
    """Переносит исходный bytes в DLQ, не логируя или не меняя их содержимое."""

    def __init__(self, broker: KafkaBroker, *, consumer_name: str = "client_session_facts") -> None:
        self._broker = broker
        self._consumer_name = consumer_name

    async def publish_rejected(self, payload: bytes, reason_code: str) -> None:
        await self._broker.publish(
            payload,
            topic="v2.failed-events",
            headers={
                "consumer_name": self._consumer_name,
                "reason_code": reason_code,
            },
        )


class V2ClientFactsConsumer:
    """Kafka boundary: offset подтверждается только после commit или DLQ."""

    def __init__(
        self,
        handler: V2ClientFactsHandler,
        rejected_events: V2RejectedEventPublisher,
    ) -> None:
        self._handler = handler
        self._rejected_events = rejected_events

    async def accept_payload(self, payload: bytes) -> V2ClientFactResult | None:
        try:
            event = event_from_protobuf_bytes(payload)
        except ValueError as error:
            await self._rejected_events.publish_rejected(payload, "invalid_envelope")
            logger.warning("v2_client_fact_invalid_envelope reason=%s", str(error))
            return None

        result = await self._handler.accept(event)
        if result.status in {V2ClientFactStatus.ACCEPTED, V2ClientFactStatus.DUPLICATE}:
            return result

        await self._rejected_events.publish_rejected(
            payload,
            f"reconciliation_{result.status.value}",
        )
        logger.warning(
            "v2_client_fact_reconciliation_rejected status=%s reason=%s",
            result.status.value,
            result.message,
        )
        return result


class V2ConfirmedAnalyticsHandler(typing.Protocol):
    """Приём только server-confirmed факта в независимый analytics inbox."""

    async def accept(self, event: V2Event) -> V2InboxResult:
        """Сохранить analytics inbox и outbox одной PostgreSQL-транзакцией."""


class V2ConfirmedAnalyticsConsumer:
    """Подтверждает offset лишь после analytics commit либо безопасного DLQ."""

    def __init__(
        self,
        handler: V2ConfirmedAnalyticsHandler,
        rejected_events: V2RejectedEventPublisher,
    ) -> None:
        self._handler = handler
        self._rejected_events = rejected_events

    async def accept_payload(self, payload: bytes) -> V2InboxResult | None:
        try:
            event = event_from_protobuf_bytes(payload)
            result = await self._handler.accept(event)
        except ValueError:
            await self._rejected_events.publish_rejected(payload, "invalid_confirmed_event")
            return None

        if result.status in {V2InboxStatus.ACCEPTED, V2InboxStatus.DUPLICATE}:
            return result

        await self._rejected_events.publish_rejected(
            payload,
            f"confirmed_analytics_{result.status.value}",
        )
        return result


def register_client_session_facts_consumer(
    broker: KafkaBroker,
    consumer: V2ClientFactsConsumer,
) -> None:
    """Подключить FastStream-группу без переноса правил сессии в transport."""

    @broker.subscriber(
        "v2.client-events",
        group_id="client_session_facts",
        auto_offset_reset="earliest",
    )
    async def accept_client_session_fact(message: bytes) -> None:
        await consumer.accept_payload(message)


def register_confirmed_analytics_consumer(
    broker: KafkaBroker,
    consumer: V2ConfirmedAnalyticsConsumer,
) -> None:
    """Подключить analytics group без доступа к write-path денег или сессии."""

    @broker.subscriber(
        "v2.confirmed-domain-events",
        group_id="confirmed_analytics",
        auto_offset_reset="earliest",
    )
    async def accept_confirmed_domain_event(message: bytes) -> None:
        await consumer.accept_payload(message)
