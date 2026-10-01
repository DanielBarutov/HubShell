"""V2-процесс доставки server outbox в Kafka.

Этот процесс не принимает финансовых или сессионных решений. Он только повторяет
отправку уже зафиксированных серверных фактов и помечает их опубликованными после
подтверждения брокера.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import typing

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
from gameclub_backend.modules.eventing_v2.application.outbox import V2ServerOutboxService
from gameclub_backend.modules.eventing_v2.infrastructure.faststream import (
    FastStreamV2EventPublisher,
    V2ServerOutboxPublisher,
)
from gameclub_backend.modules.eventing_v2.infrastructure.postgres import (
    PostgresV2ServerOutboxRepository,
)

logger = logging.getLogger(__name__)
POLL_INTERVAL_SECONDS = 0.5
SERVICE_NAME = "gameclub-v2-server-outbox"


def _require_kafka_bootstrap_servers(settings: Settings) -> str:
    if not settings.kafka_bootstrap_servers:
        raise RuntimeError("GAMECLUB_KAFKA_BOOTSTRAP_SERVERS is required for V2 Kafka worker")
    return settings.kafka_bootstrap_servers


def _engine_provider(resources: InfrastructureResources):
    if resources.engine is None:
        raise RuntimeError("GAMECLUB_POSTGRES_DSN is required for V2 Kafka worker")
    return resources.engine


def create_outbox_publisher(
    resources: InfrastructureResources,
    broker: KafkaBroker,
) -> V2ServerOutboxPublisher:
    """Собрать transport-часть, не смешивая её с правилами V2-сессии."""

    engine = _engine_provider(resources)
    outbox = V2ServerOutboxService(PostgresV2ServerOutboxRepository(lambda: engine))
    return V2ServerOutboxPublisher(outbox, FastStreamV2EventPublisher(broker))


async def publish_server_outbox_until_stopped(
    publisher: V2ServerOutboxPublisher,
    stop_requested: asyncio.Event,
    *,
    poll_interval_seconds: float = POLL_INTERVAL_SECONDS,
) -> None:
    """Периодически доставлять факты; ошибка одной записи остаётся в outbox."""

    while not stop_requested.is_set():
        published = await publisher.publish_pending()
        if published:
            logger.info("v2_server_outbox_published count=%s", published)
            continue
        with contextlib.suppress(asyncio.TimeoutError):
            await asyncio.wait_for(stop_requested.wait(), timeout=poll_interval_seconds)


def _create_observability_middlewares(
    settings: Settings,
) -> tuple[tuple[object, ...], CollectorRegistry | None]:
    """Настроить технические сигналы без label с client/session/operation id."""

    if not settings.v2_observability_enabled:
        return (), None

    tracer_provider = TracerProvider(
        resource=Resource.create({"service.name": SERVICE_NAME}),
    )
    if settings.otel_exporter_otlp_endpoint:
        tracer_provider.add_span_processor(
            BatchSpanProcessor(
                OTLPSpanExporter(
                    endpoint=settings.otel_exporter_otlp_endpoint,
                    insecure=True,
                )
            )
        )
    trace.set_tracer_provider(tracer_provider)

    registry = CollectorRegistry()
    return (
        (
            KafkaTelemetryMiddleware(tracer_provider=tracer_provider),
            KafkaPrometheusMiddleware(
                registry=registry,
                app_name="gameclub_v2_outbox",
            ),
        ),
        registry,
    )


settings = get_settings()
# Значение подменяется проверкой в startup. Оно нужно лишь чтобы модуль можно было
# импортировать инструментами FastStream до загрузки окружения процесса.
_broker_middlewares, _metrics_registry = _create_observability_middlewares(settings)
broker = KafkaBroker(
    settings.kafka_bootstrap_servers or "localhost:9092",
    client_id="gameclub-v2-server-outbox",
    acks="all",
    enable_idempotence=True,
    middlewares=_broker_middlewares,
)
app = FastStream(broker)

_resources: InfrastructureResources | None = None
_stop_requested: asyncio.Event | None = None
_delivery_task: asyncio.Task[None] | None = None
_metrics_http_server: object | None = None


@app.on_startup
async def prepare_server_outbox_delivery() -> None:
    """Открыть PostgreSQL и проверить конфигурацию до подключения к Kafka."""

    global _metrics_http_server, _resources, _stop_requested

    _require_kafka_bootstrap_servers(settings)
    _resources = create_resources(settings)
    _stop_requested = asyncio.Event()
    if _metrics_registry is not None:
        _metrics_http_server, _ = start_http_server(
            settings.v2_metrics_port,
            registry=_metrics_registry,
        )


@app.after_startup
async def start_server_outbox_delivery() -> None:
    """Запустить доставку только после успешного подключения FastStream к Kafka."""

    global _delivery_task

    if _resources is None or _stop_requested is None:
        raise RuntimeError("V2 Kafka worker was not prepared before broker startup")
    publisher = create_outbox_publisher(_resources, broker)
    _delivery_task = asyncio.create_task(
        publish_server_outbox_until_stopped(publisher, _stop_requested),
        name="v2-server-outbox-delivery",
    )


@app.on_shutdown
async def stop_server_outbox_delivery() -> None:
    """Остановить цикл и закрыть соединение с PostgreSQL без потери outbox."""

    global _delivery_task, _metrics_http_server, _resources, _stop_requested

    if _stop_requested is not None:
        _stop_requested.set()
    if _delivery_task is not None:
        _delivery_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await _delivery_task
    if _resources is not None:
        await _resources.close()
    if _metrics_http_server is not None:
        _metrics_http_server.shutdown()  # type: ignore[union-attr]
        _metrics_http_server.server_close()  # type: ignore[union-attr]
    _resources = None
    _stop_requested = None
    _delivery_task = None
    _metrics_http_server = None


if typing.TYPE_CHECKING:
    # FastStream CLI discovers the module-level `app` above.
    assert app is not None
