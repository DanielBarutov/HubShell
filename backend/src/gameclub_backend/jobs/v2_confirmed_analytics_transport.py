"""Отдельный Kafka consumer confirmed V2-фактов для аналитики."""

from __future__ import annotations

import typing

from faststream import FastStream
from faststream.kafka import KafkaBroker

from gameclub_backend.config import get_settings
from gameclub_backend.infrastructure.resources import InfrastructureResources, create_resources
from gameclub_backend.modules.eventing_v2.infrastructure.confirmed_analytics_postgres import (
    PostgresV2ConfirmedAnalyticsRepository,
)
from gameclub_backend.modules.eventing_v2.infrastructure.protobuf import event_from_protobuf_bytes

settings = get_settings()
broker = KafkaBroker(
    settings.kafka_bootstrap_servers or "localhost:9092",
    client_id="gameclub-v2-analytics",
)
app = FastStream(broker)
_resources: InfrastructureResources | None = None
_repository: PostgresV2ConfirmedAnalyticsRepository | None = None


@app.on_startup
async def prepare_confirmed_analytics() -> None:
    global _repository, _resources
    if not settings.kafka_bootstrap_servers or not settings.postgres_dsn:
        raise RuntimeError("Kafka bootstrap servers and PostgreSQL DSN are required")
    _resources = create_resources(settings)
    if _resources.engine is None:
        raise RuntimeError("Confirmed analytics consumer did not receive a PostgreSQL engine")
    _repository = PostgresV2ConfirmedAnalyticsRepository(lambda: _resources.engine)


@broker.subscriber(
    "v2.confirmed-domain-events",
    group_id="confirmed_analytics",
    auto_offset_reset="earliest",
)
async def accept_confirmed_event(message: bytes) -> None:
    if _repository is None:
        raise RuntimeError("Confirmed analytics consumer was not initialized")
    await _repository.accept(event_from_protobuf_bytes(message))


@app.on_shutdown
async def close_confirmed_analytics() -> None:
    global _repository, _resources
    if _resources is not None:
        await _resources.close()
    _repository = None
    _resources = None


if typing.TYPE_CHECKING:
    assert app is not None
