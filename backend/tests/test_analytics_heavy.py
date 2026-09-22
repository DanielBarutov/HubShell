import asyncio
import datetime
import hashlib
import uuid

import pytest

from gameclub_backend.modules.analytics.heavy_events import (
    AnalyticsEventType,
    AnalyticsOutboxEvent,
    event_from_payload,
)
from gameclub_backend.modules.analytics.heavy_memory import InMemoryAnalyticsHeavyRepository
from gameclub_backend.modules.analytics.projection import AnalyticsProjectionService
from gameclub_backend.modules.analytics.reporting import (
    ExportFormat,
    ReportJobService,
    ReportPermissionError,
    ReportStatus,
    render_report,
)

UTC = datetime.UTC


def event(
    *, event_id: uuid.UUID | None = None, idempotency_key: str = "event-1"
) -> AnalyticsOutboxEvent:
    return event_from_payload(
        event_id=event_id or uuid.uuid4(),
        event_type=AnalyticsEventType.FINANCIAL_FACT,
        aggregate_type="payment",
        aggregate_id="payment-1",
        occurred_at=datetime.datetime(2026, 9, 20, 10, 15, tzinfo=UTC),
        idempotency_key=idempotency_key,
        payload={
            "metric_key": "revenue_cents",
            "value_cents": 1_000,
            "quantity": 1,
            "status": "confirmed",
            "payment_method": "cash",
        },
    )


@pytest.mark.asyncio
async def test_projection_applies_duplicate_delivery_once_and_rebuild_matches() -> None:
    """Проверяет идемпотентное применение события и совпадение после перестроения."""
    repository = InMemoryAnalyticsHeavyRepository()
    service = AnalyticsProjectionService(repository)
    first = event()

    await service.publish(first)
    await service.publish(first)
    assert await service.consume_once() == 1
    assert await service.consume_once() == 0
    assert await service.read(metric_key="revenue_cents") == (
        {
            "metric_key": "revenue_cents",
            "bucket_start": "2026-09-19T21:00:00+00:00",
            "dimensions": {"payment_method": "cash"},
            "value_cents": 1000,
            "quantity": 1,
            "event_count": 1,
        },
    )

    await service.rebuild()
    assert await service.read(metric_key="revenue_cents") == (
        {
            "metric_key": "revenue_cents",
            "bucket_start": "2026-09-19T21:00:00+00:00",
            "dimensions": {"payment_method": "cash"},
            "value_cents": 1000,
            "quantity": 1,
            "event_count": 1,
        },
    )
    assert await service.reconcile("revenue_cents") is True


def test_outbox_event_rejects_unversioned_or_unconfirmed_financial_fact() -> None:
    """Проверяет версию события и исключение неподтверждённого факта."""
    with pytest.raises(ValueError, match="version"):
        AnalyticsOutboxEvent(
            id=uuid.uuid4(),
            event_type=AnalyticsEventType.FINANCIAL_FACT,
            event_version=0,
            aggregate_type="payment",
            aggregate_id="payment-1",
            occurred_at=datetime.datetime(2026, 9, 20, tzinfo=UTC),
            idempotency_key="bad",
            payload={},
            created_at=datetime.datetime(2026, 9, 20, tzinfo=UTC),
        )

    repository = InMemoryAnalyticsHeavyRepository()
    service = AnalyticsProjectionService(repository)

    async def publish_pending() -> None:
        await service.publish(
            event_from_payload(
                event_id=uuid.uuid4(),
                event_type=AnalyticsEventType.FINANCIAL_FACT,
                aggregate_type="payment",
                aggregate_id="payment-2",
                occurred_at=datetime.datetime(2026, 9, 20, tzinfo=UTC),
                idempotency_key="pending",
                payload={"metric_key": "revenue_cents", "value_cents": 500, "status": "pending"},
            )
        )
        assert await service.consume_once() == 1
        assert await service.read(metric_key="revenue_cents") == ()

    import asyncio

    asyncio.run(publish_pending())


@pytest.mark.asyncio
async def test_report_jobs_require_export_and_pii_permissions_and_protect_artifact() -> None:
    """Проверяет права экспорта, защиту PII и ссылку на артефакт."""
    repository = InMemoryAnalyticsHeavyRepository()
    service = ReportJobService(repository)

    with pytest.raises(ReportPermissionError):
        await service.create_job(
            requested_by="operator",
            permissions={"analytics.read"},
            report_name="daily",
            export_format=ExportFormat.CSV,
            idempotency_key="report-1",
            include_pii=False,
        )

    with pytest.raises(ReportPermissionError):
        await service.create_job(
            requested_by="operator",
            permissions={"analytics.read", "analytics.export"},
            report_name="daily",
            export_format=ExportFormat.CSV,
            idempotency_key="report-2",
            include_pii=True,
        )

    job = await service.create_job(
        requested_by="operator",
        permissions={"analytics.read", "analytics.export"},
        report_name="daily",
        export_format=ExportFormat.CSV,
        idempotency_key="report-3",
        include_pii=False,
    )
    same = await service.create_job(
        requested_by="operator",
        permissions={"analytics.read", "analytics.export"},
        report_name="daily",
        export_format=ExportFormat.CSV,
        idempotency_key="report-3",
        include_pii=False,
    )
    assert same.id == job.id
    assert job.status is ReportStatus.PENDING

    await service.complete_job(job.id, b"metric,value\nrevenue_cents,1000\n", "text/csv")
    artifact = await service.read_artifact(job.id, job.artifact_token or "", {"analytics.read"})
    assert artifact.content == b"metric,value\nrevenue_cents,1000\n"
    assert artifact.sha256 == hashlib.sha256(artifact.content).hexdigest()

    with pytest.raises(ReportPermissionError):
        await service.read_artifact(job.id, "wrong-token", {"analytics.read"})


@pytest.mark.asyncio
async def test_report_job_retry_timeout_and_not_available_exports() -> None:
    """Проверяет повторы отчёта, тайм-аут и недоступные форматы."""
    repository = InMemoryAnalyticsHeavyRepository()
    service = ReportJobService(repository)
    job = await service.create_job(
        requested_by="operator",
        permissions={"analytics.read", "analytics.export"},
        report_name="daily",
        export_format=ExportFormat.CSV,
        idempotency_key="retry-report",
        include_pii=False,
        timeout_seconds=1,
        max_attempts=2,
    )

    async def failing_renderer() -> tuple[bytes, str]:
        raise RuntimeError("temporary")

    assert await service.run(job.id, failing_renderer) is ReportStatus.PENDING
    assert (await service.get(job.id)).attempts == 1
    assert await service.run(job.id, failing_renderer) is ReportStatus.FAILED
    assert (await service.get(job.id)).attempts == 2

    timeout_job = await service.create_job(
        requested_by="operator",
        permissions={"analytics.read", "analytics.export"},
        report_name="slow",
        export_format=ExportFormat.CSV,
        idempotency_key="timeout-report",
        include_pii=False,
        timeout_seconds=1,
        max_attempts=1,
    )

    async def slow_renderer() -> tuple[bytes, str]:
        await asyncio.sleep(1.1)
        return b"", "text/csv"

    assert await service.run(timeout_job.id, slow_renderer) is ReportStatus.FAILED

    xlsx, xlsx_type = render_report(ExportFormat.XLSX, [{"a": 1}])
    assert xlsx.startswith(b"PK")
    assert xlsx_type.startswith("application/vnd.openxmlformats")
    pdf, pdf_type = render_report(ExportFormat.PDF, [{"a": 1}])
    assert pdf.startswith(b"%PDF-1.4")
    assert pdf_type == "application/pdf"

    available = await service.create_job(
        requested_by="operator",
        permissions={"analytics.read", "analytics.export"},
        report_name="daily",
        export_format=ExportFormat.XLSX,
        idempotency_key="xlsx-available",
        include_pii=False,
    )
    assert available.status is ReportStatus.PENDING
