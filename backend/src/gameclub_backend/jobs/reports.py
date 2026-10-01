from __future__ import annotations

import logging
import uuid

import dramatiq

from gameclub_backend.config import get_settings
from gameclub_backend.infrastructure.resources import create_resources
from gameclub_backend.jobs.broker import broker as shared_broker
from gameclub_backend.modules.analytics.heavy_postgres import PostgresAnalyticsHeavyRepository
from gameclub_backend.modules.analytics.projection import AnalyticsProjectionService
from gameclub_backend.modules.analytics.reporting import ReportJobService, render_report
from gameclub_backend.modules.eventing_v2.infrastructure.confirmed_analytics_postgres import (
    PostgresV2ConfirmedAnalyticsRepository,
)

dramatiq.set_broker(shared_broker)

logger = logging.getLogger(__name__)


@dramatiq.actor(queue_name="analytics-reports", max_retries=0, time_limit=300_000)  # type: ignore[arg-type]
async def generate_analytics_report(job_id: str) -> None:
    """Render one durable analytics job from the analytics projection."""
    settings = get_settings()
    if not settings.postgres_dsn:
        raise RuntimeError("GAMECLUB_POSTGRES_DSN is required for analytics report workers")
    resources = create_resources(settings)
    try:
        repository = PostgresAnalyticsHeavyRepository(lambda: resources.engine)
        projection = AnalyticsProjectionService(repository)
        service = ReportJobService(repository)
        job = await service.get(uuid.UUID(job_id))
        await projection.consume_once()
        rows = await repository.read_projection()

        async def renderer() -> tuple[bytes, str]:
            return render_report(job.export_format, rows)

        await service.run(job.id, renderer)
    finally:
        await resources.close()


@dramatiq.actor(queue_name="analytics-projection", max_retries=3, time_limit=120_000)  # type: ignore[arg-type]
async def project_analytics_events() -> None:
    """Apply pending versioned outbox events to the analytics projection."""
    settings = get_settings()
    if not settings.postgres_dsn:
        raise RuntimeError("GAMECLUB_POSTGRES_DSN is required for analytics projection workers")
    resources = create_resources(settings)
    try:
        repository = PostgresAnalyticsHeavyRepository(lambda: resources.engine)
        applied = await AnalyticsProjectionService(repository).consume_once()
        logger.info("analytics_projection_completed applied_count=%s", applied)
    finally:
        await resources.close()


@dramatiq.actor(queue_name="analytics-projection", max_retries=3, time_limit=120_000)  # type: ignore[arg-type]
async def backfill_v2_confirmed_per_minute_debits() -> None:
    """Восстановить analytics outbox из уже принятых V2 immutable debit facts."""
    settings = get_settings()
    if not settings.postgres_dsn:
        raise RuntimeError("GAMECLUB_POSTGRES_DSN is required for V2 analytics backfill")
    resources = create_resources(settings)
    try:
        if resources.engine is None:
            raise RuntimeError("PostgreSQL engine is required for V2 analytics backfill")
        result = await PostgresV2ConfirmedAnalyticsRepository(
            lambda: resources.engine
        ).backfill_per_minute_debits()
        logger.info(
            "v2_confirmed_per_minute_debit_backfill_completed accepted_count=%s duplicate_count=%s",
            result.accepted_count,
            result.duplicate_count,
        )
    finally:
        await resources.close()
