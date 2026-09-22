import datetime
import os
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from gameclub_backend.modules.analytics.heavy_events import AnalyticsEventType, event_from_payload
from gameclub_backend.modules.analytics.heavy_postgres import PostgresAnalyticsHeavyRepository
from gameclub_backend.modules.analytics.projection import AnalyticsProjectionService
from gameclub_backend.modules.analytics.reporting import ExportFormat, ReportJobService

UTC = datetime.UTC


@pytest.mark.integration
@pytest.mark.postgres
async def test_postgres_outbox_projection_rebuild_and_report_artifact() -> None:
    """Проверяет outbox, проекцию, перестроение и защищённый артефакт в PostgreSQL."""
    dsn = os.getenv("GAMECLUB_TEST_POSTGRES_DSN")
    if not dsn:
        pytest.skip("Set GAMECLUB_TEST_POSTGRES_DSN to run analytics heavy PostgreSQL checks")
    engine = create_async_engine(dsn, pool_pre_ping=True)
    event_id = uuid.uuid4()
    event_key = f"heavy-test-{event_id}"
    job_key = f"heavy-report-{event_id}"
    try:
        repository = PostgresAnalyticsHeavyRepository(lambda: engine)
        projection = AnalyticsProjectionService(repository)
        analytics_event = event_from_payload(
            event_id=event_id,
            event_type=AnalyticsEventType.FINANCIAL_FACT,
            aggregate_type="payment",
            aggregate_id=str(event_id),
            occurred_at=datetime.datetime(2026, 9, 20, 10, tzinfo=UTC),
            idempotency_key=event_key,
            payload={
                "metric_key": "revenue_cents",
                "value_cents": 1234,
                "quantity": 1,
                "status": "confirmed",
                "payment_method": "cash",
            },
        )
        first = await projection.publish(analytics_event)
        second = await projection.publish(analytics_event)
        assert first.id == second.id == event_id
        assert await projection.consume_once() == 1
        assert await projection.read_total("revenue_cents") >= 1234
        before = await projection.read("revenue_cents")
        await projection.rebuild()
        assert await projection.read("revenue_cents") == before

        jobs = ReportJobService(repository)
        job = await jobs.create_job(
            requested_by="integration-test",
            permissions={"analytics.read", "analytics.export"},
            report_name="projection",
            export_format=ExportFormat.CSV,
            idempotency_key=job_key,
            include_pii=False,
        )
        await jobs.complete_job(job.id, b"metric,value\nrevenue_cents,1234\n", "text/csv")
        artifact = await jobs.read_artifact(job.id, job.artifact_token or "", {"analytics.read"})
        assert artifact.sha256
        assert artifact.content.startswith(b"metric,value")
    finally:
        async with engine.begin() as connection:
            await connection.execute(
                text("TRUNCATE analytics_projection_events, analytics_projection_daily")
            )
            await connection.execute(
                text("DELETE FROM analytics_report_jobs WHERE idempotency_key = :key"),
                {"key": job_key},
            )
            await connection.execute(
                text("DELETE FROM analytics_outbox_events WHERE idempotency_key = :key"),
                {"key": event_key},
            )
        await engine.dispose()
