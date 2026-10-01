"""Отдельный FastStream-процесс для приёма V2-фактов игровых ПК.

Он не рассчитывает минуты: проверку lease, snapshot, inbox, hash-chain и
создание server outbox выполняет application boundary в одной PostgreSQL
транзакции. Некорректный или конфликтный факт сначала переносится в закрытый
Kafka DLQ, и только после этого consumer подтверждает offset.
"""

from __future__ import annotations

import logging

from faststream import FastStream
from faststream.kafka import KafkaBroker
from faststream.kafka.opentelemetry import KafkaTelemetryMiddleware
from faststream.kafka.prometheus import KafkaPrometheusMiddleware
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from prometheus_client import CollectorRegistry, start_http_server

from gameclub_backend.config import Settings, get_settings
from gameclub_backend.infrastructure.resources import InfrastructureResources, create_resources
from gameclub_backend.modules.eventing_v2.application.reconciliation import (
    V2ClientFactReconciliationService,
)
from gameclub_backend.modules.eventing_v2.infrastructure.faststream import (
    FastStreamV2RejectedEventPublisher,
    V2ClientFactsConsumer,
)
from gameclub_backend.modules.eventing_v2.infrastructure.reconciliation_postgres import (
    PostgresV2ClientFactReconciliationRepository,
)
from gameclub_backend.modules.sessions.infrastructure.postgres import (
    PostgresSessionTransactionWriter,
)

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
SERVICE_NAME = "gameclub-v2-client-facts"


def _require_worker_configuration(settings: Settings) -> str:
    if not settings.kafka_bootstrap_servers:
        raise RuntimeError("GAMECLUB_KAFKA_BOOTSTRAP_SERVERS is required for V2 Kafka worker")
    if not settings.postgres_dsn:
        raise RuntimeError("GAMECLUB_POSTGRES_DSN is required for V2 Kafka worker")
    return settings.kafka_bootstrap_servers


def _create_observability_middlewares(
    settings: Settings,
) -> tuple[tuple[object, ...], CollectorRegistry | None]:
    if not settings.v2_observability_enabled:
        return (), None

    tracer_provider = TracerProvider(resource=Resource.create({"service.name": SERVICE_NAME}))
    if settings.otel_exporter_otlp_endpoint:
        tracer_provider.add_span_processor(
            BatchSpanProcessor(
                OTLPSpanExporter(endpoint=settings.otel_exporter_otlp_endpoint, insecure=True)
            )
        )
    trace.set_tracer_provider(tracer_provider)
    registry = CollectorRegistry()
    return (
        (
            KafkaTelemetryMiddleware(tracer_provider=tracer_provider),
            KafkaPrometheusMiddleware(registry=registry, app_name="gameclub_v2_client_facts"),
        ),
        registry,
    )


settings = get_settings()
_broker_middlewares, _metrics_registry = _create_observability_middlewares(settings)
broker = KafkaBroker(
    settings.kafka_bootstrap_servers or "localhost:9092",
    client_id="gameclub-v2-client-facts",
    middlewares=_broker_middlewares,
)
app = FastStream(broker)

_resources: InfrastructureResources | None = None
_consumer: V2ClientFactsConsumer | None = None
_metrics_http_server: object | None = None


@app.on_startup
async def prepare_client_facts_consumer() -> None:
    """Собрать reconciliation только перед открытием consumer group."""

    global _consumer, _metrics_http_server, _resources

    _require_worker_configuration(settings)
    _resources = create_resources(settings)
    if _resources.engine is None:
        raise RuntimeError("V2 Kafka worker did not receive a PostgreSQL engine")
    reconciliation = V2ClientFactReconciliationService(
        PostgresV2ClientFactReconciliationRepository(
            lambda: _resources.engine,
            session_writer=PostgresSessionTransactionWriter(),
        )
    )
    _consumer = V2ClientFactsConsumer(
        reconciliation,
        FastStreamV2RejectedEventPublisher(broker),
    )
    if _metrics_registry is not None:
        _metrics_http_server, _ = start_http_server(
            settings.v2_client_facts_metrics_port,
            registry=_metrics_registry,
        )


@broker.subscriber(
    "v2.client-events",
    group_id="client_session_facts",
    auto_offset_reset="earliest",
)
async def accept_client_session_fact(message: bytes) -> None:
    """Не подтверждать offset, пока transaction или перенос в DLQ не завершён."""

    if _consumer is None:
        raise RuntimeError("V2 client facts consumer was not initialized")
    result = await _consumer.accept_payload(message)
    if result is None:
        logger.warning("v2_client_fact_rejected reason=invalid_envelope")
    elif result.status.value not in {"accepted", "duplicate"}:
        logger.warning(
            "v2_client_fact_rejected status=%s reason=%s",
            result.status.value,
            result.message,
        )
    else:
        logger.info("v2_client_fact_processed status=%s", result.status.value)


@app.on_shutdown
async def close_client_facts_consumer() -> None:
    global _consumer, _metrics_http_server, _resources

    _consumer = None
    if _resources is not None:
        await _resources.close()
    if _metrics_http_server is not None:
        _metrics_http_server.shutdown()  # type: ignore[union-attr]
        _metrics_http_server.server_close()  # type: ignore[union-attr]
    _resources = None
    _metrics_http_server = None
