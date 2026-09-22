from __future__ import annotations

import datetime
import hashlib
import json
import secrets
import typing
import uuid

import sqlalchemy as sa

from gameclub_backend.infrastructure.database import EngineProvider, open_session
from gameclub_backend.modules.analytics.heavy_events import (
    AnalyticsOutboxEvent,
    bucket_start,
    projection_delta,
)
from gameclub_backend.modules.analytics.projection import AnalyticsHeavyRepository
from gameclub_backend.modules.analytics.reporting import ExportFormat, ReportJob, ReportStatus


class PostgresAnalyticsHeavyRepository(AnalyticsHeavyRepository):
    def __init__(self, engine_provider: EngineProvider, artifact_retention_days: int = 7) -> None:
        self._engine_provider = engine_provider
        self._artifact_retention_days = artifact_retention_days

    async def append_event(self, event: AnalyticsOutboxEvent) -> AnalyticsOutboxEvent:
        async with open_session(self._engine_provider) as session:
            async with session.begin():
                await session.execute(
                    sa.text(
                        """
                        INSERT INTO analytics_outbox_events
                            (id, event_type, event_version, aggregate_type, aggregate_id,
                             occurred_at, idempotency_key, payload, created_at)
                        VALUES
                            (:id, :event_type, :event_version, :aggregate_type, :aggregate_id,
                             :occurred_at, :idempotency_key, CAST(:payload AS jsonb), :created_at)
                        ON CONFLICT (idempotency_key) DO NOTHING
                        """
                    ),
                    {
                        "id": event.id,
                        "event_type": event.event_type.value,
                        "event_version": event.event_version,
                        "aggregate_type": event.aggregate_type,
                        "aggregate_id": event.aggregate_id,
                        "occurred_at": event.occurred_at,
                        "idempotency_key": event.idempotency_key,
                        "payload": json.dumps(event.payload, sort_keys=True),
                        "created_at": event.created_at,
                    },
                )
                row = (
                    (
                        await session.execute(
                            sa.text(
                                "SELECT id, event_type, event_version, aggregate_type, "
                                "aggregate_id, occurred_at, idempotency_key, payload, created_at "
                                "FROM analytics_outbox_events WHERE idempotency_key = :key"
                            ),
                            {"key": event.idempotency_key},
                        )
                    )
                    .mappings()
                    .one()
                )
        return _event_from_row(row)

    async def list_unapplied_events(self, limit: int) -> tuple[AnalyticsOutboxEvent, ...]:
        async with open_session(self._engine_provider) as session:
            rows = (
                (
                    await session.execute(
                        sa.text(
                            """
                        SELECT e.id, e.event_type, e.event_version, e.aggregate_type,
                               e.aggregate_id, e.occurred_at, e.idempotency_key,
                               e.payload, e.created_at
                        FROM analytics_outbox_events e
                        WHERE NOT EXISTS (
                            SELECT 1 FROM analytics_projection_events p WHERE p.event_id = e.id
                        )
                        ORDER BY e.occurred_at, e.id
                        LIMIT :limit
                        """
                        ),
                        {"limit": limit},
                    )
                )
                .mappings()
                .all()
            )
        return tuple(_event_from_row(row) for row in rows)

    async def list_events(self) -> tuple[AnalyticsOutboxEvent, ...]:
        async with open_session(self._engine_provider) as session:
            rows = (
                (
                    await session.execute(
                        sa.text(
                            "SELECT id, event_type, event_version, aggregate_type, aggregate_id, "
                            "occurred_at, idempotency_key, payload, created_at "
                            "FROM analytics_outbox_events ORDER BY occurred_at, id"
                        )
                    )
                )
                .mappings()
                .all()
            )
        return tuple(_event_from_row(row) for row in rows)

    async def apply_event(self, event: AnalyticsOutboxEvent) -> bool:
        delta = projection_delta(event)
        async with open_session(self._engine_provider) as session:
            async with session.begin():
                inserted = (
                    await session.execute(
                        sa.text(
                            """
                            INSERT INTO analytics_projection_events (event_id, applied_at)
                            VALUES (:event_id, :applied_at)
                            ON CONFLICT (event_id) DO NOTHING
                            RETURNING event_id
                            """
                        ),
                        {"event_id": event.id, "applied_at": datetime.datetime.now(datetime.UTC)},
                    )
                ).scalar_one_or_none()
                if inserted is None:
                    return False
                if delta is not None:
                    metric_key, value_cents, quantity, dimensions = delta
                    dimensions_key = ";".join(
                        f"{key}={dimensions[key]}" for key in sorted(dimensions)
                    )
                    await session.execute(
                        sa.text(
                            """
                            INSERT INTO analytics_projection_daily
                                (metric_key, bucket_start, dimensions_key, dimensions,
                                 value_cents, quantity, event_count, updated_at)
                            VALUES
                                (:metric_key, :bucket_start, :dimensions_key,
                                 CAST(:dimensions AS jsonb), :value_cents, :quantity, 1,
                                 :updated_at)
                            ON CONFLICT (metric_key, bucket_start, dimensions_key)
                            DO UPDATE SET
                                value_cents = analytics_projection_daily.value_cents
                                    + EXCLUDED.value_cents,
                                quantity = analytics_projection_daily.quantity + EXCLUDED.quantity,
                                event_count = analytics_projection_daily.event_count + 1,
                                updated_at = EXCLUDED.updated_at
                            """
                        ),
                        {
                            "metric_key": metric_key,
                            "bucket_start": bucket_start(event.occurred_at),
                            "dimensions_key": dimensions_key,
                            "dimensions": json.dumps(dimensions, sort_keys=True),
                            "value_cents": value_cents,
                            "quantity": quantity,
                            "updated_at": datetime.datetime.now(datetime.UTC),
                        },
                    )
                await session.execute(
                    sa.text(
                        "UPDATE analytics_outbox_events SET published_at = :published_at "
                        "WHERE id = :event_id"
                    ),
                    {"published_at": datetime.datetime.now(datetime.UTC), "event_id": event.id},
                )
        return True

    async def rebuild_projection(self) -> None:
        async with open_session(self._engine_provider) as session:
            async with session.begin():
                await session.execute(sa.text("TRUNCATE analytics_projection_events"))
                await session.execute(sa.text("TRUNCATE analytics_projection_daily"))
                rows = (
                    (
                        await session.execute(
                            sa.text(
                                "SELECT id, event_type, event_version, aggregate_type, "
                                "aggregate_id, occurred_at, idempotency_key, payload, created_at "
                                "FROM analytics_outbox_events ORDER BY occurred_at, id"
                            )
                        )
                    )
                    .mappings()
                    .all()
                )
        for row in rows:
            await self.apply_event(_event_from_row(row))

    async def read_projection(self, metric_key: str | None = None) -> tuple[dict[str, object], ...]:
        query = (
            "SELECT metric_key, bucket_start, dimensions, value_cents, quantity, event_count "
            "FROM analytics_projection_daily"
        )
        params: dict[str, object] = {}
        if metric_key is not None:
            query += " WHERE metric_key = :metric_key"
            params["metric_key"] = metric_key
        query += " ORDER BY bucket_start, metric_key, dimensions_key"
        async with open_session(self._engine_provider) as session:
            rows = (await session.execute(sa.text(query), params)).mappings().all()
        return tuple(
            {
                "metric_key": str(row["metric_key"]),
                "bucket_start": _aware(row["bucket_start"]).isoformat(),
                "dimensions": dict(row["dimensions"]),
                "value_cents": int(row["value_cents"]),
                "quantity": int(row["quantity"]),
                "event_count": int(row["event_count"]),
            }
            for row in rows
        )

    async def create_report_job(self, job: ReportJob) -> ReportJob:
        token_hash = hashlib.sha256(
            (job.artifact_token or secrets.token_urlsafe(32)).encode()
        ).hexdigest()
        async with open_session(self._engine_provider) as session:
            async with session.begin():
                await session.execute(
                    sa.text(
                        """
                        INSERT INTO analytics_report_jobs
                            (id, requested_by, report_name, export_format, idempotency_key,
                             include_pii, timeout_seconds, max_attempts, status, attempts,
                             created_at,
                             error, artifact_token_hash)
                        VALUES (:id, :requested_by, :report_name, :export_format, :idempotency_key,
                                :include_pii, :timeout_seconds, :max_attempts, :status, :attempts,
                                :created_at, :error, :artifact_token_hash)
                        ON CONFLICT (idempotency_key) DO NOTHING
                        """
                    ),
                    {
                        "id": job.id,
                        "requested_by": job.requested_by,
                        "report_name": job.report_name,
                        "export_format": job.export_format.value,
                        "idempotency_key": job.idempotency_key,
                        "include_pii": job.include_pii,
                        "timeout_seconds": job.timeout_seconds,
                        "max_attempts": job.max_attempts,
                        "status": job.status.value,
                        "attempts": job.attempts,
                        "created_at": job.created_at,
                        "error": job.error,
                        "artifact_token_hash": token_hash,
                    },
                )
                row = (
                    (
                        await session.execute(
                            sa.text(
                                "SELECT * FROM analytics_report_jobs WHERE idempotency_key = :key"
                            ),
                            {"key": job.idempotency_key},
                        )
                    )
                    .mappings()
                    .one()
                )
        return _job_from_row(
            row, artifact_token=job.artifact_token if row["id"] == job.id else None
        )

    async def get_report_job(self, job_id: uuid.UUID) -> ReportJob:
        async with open_session(self._engine_provider) as session:
            row = (
                (
                    await session.execute(
                        sa.text("SELECT * FROM analytics_report_jobs WHERE id = :id"),
                        {"id": job_id},
                    )
                )
                .mappings()
                .one()
            )
        return _job_from_row(row)

    async def update_report_job(self, job: ReportJob) -> ReportJob:
        async with open_session(self._engine_provider) as session:
            async with session.begin():
                await session.execute(
                    sa.text(
                        """
                        UPDATE analytics_report_jobs
                        SET status = :status, attempts = :attempts, started_at = :started_at,
                            completed_at = :completed_at, error = :error
                        WHERE id = :id
                        """
                    ),
                    {
                        "id": job.id,
                        "status": job.status.value,
                        "attempts": job.attempts,
                        "started_at": job.started_at,
                        "completed_at": job.completed_at,
                        "error": job.error,
                    },
                )
        return job

    async def store_artifact(self, job: ReportJob, content: bytes, content_type: str) -> ReportJob:
        now = datetime.datetime.now(datetime.UTC)
        expires_at = now + datetime.timedelta(days=self._artifact_retention_days)
        token_hash = (
            hashlib.sha256(job.artifact_token.encode()).hexdigest() if job.artifact_token else None
        )
        async with open_session(self._engine_provider) as session:
            async with session.begin():
                if token_hash is None:
                    token_hash = (
                        await session.execute(
                            sa.text(
                                "SELECT artifact_token_hash FROM analytics_report_jobs "
                                "WHERE id = :id"
                            ),
                            {"id": job.id},
                        )
                    ).scalar_one()
                await session.execute(
                    sa.text(
                        """
                        UPDATE analytics_report_jobs
                        SET status = 'succeeded', completed_at = :completed_at,
                            artifact_token_hash = :artifact_token_hash,
                            artifact_content_type = :content_type,
                            artifact_sha256 = :sha256, artifact_size = :size,
                            artifact_expires_at = :expires_at, artifact_content = :content
                        WHERE id = :id
                        """
                    ),
                    {
                        "id": job.id,
                        "completed_at": now,
                        "artifact_token_hash": token_hash,
                        "content_type": content_type,
                        "sha256": hashlib.sha256(content).hexdigest(),
                        "size": len(content),
                        "expires_at": expires_at,
                        "content": content,
                    },
                )
        return _job_with_artifact(
            job, content_type, hashlib.sha256(content).hexdigest(), len(content)
        )

    async def read_artifact(self, job: ReportJob, token: str) -> tuple[bytes, str, str, int]:
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        async with open_session(self._engine_provider) as session:
            row = (
                (
                    await session.execute(
                        sa.text(
                            "SELECT artifact_content, artifact_content_type, "
                            "artifact_sha256, artifact_size "
                            "FROM analytics_report_jobs WHERE id = :id AND status = 'succeeded' "
                            "AND artifact_token_hash = :token_hash AND artifact_expires_at > :now"
                        ),
                        {
                            "id": job.id,
                            "token_hash": token_hash,
                            "now": datetime.datetime.now(datetime.UTC),
                        },
                    )
                )
                .mappings()
                .one_or_none()
            )
        if row is None or row["artifact_content"] is None:
            raise PermissionError("Invalid or expired artifact reference")
        return (
            bytes(row["artifact_content"]),
            str(row["artifact_content_type"]),
            str(row["artifact_sha256"]),
            int(row["artifact_size"]),
        )


def _aware(value: object) -> datetime.datetime:
    if not isinstance(value, datetime.datetime):
        raise TypeError("Expected datetime")
    return value if value.tzinfo is not None else value.replace(tzinfo=datetime.UTC)


def _event_from_row(row: object) -> AnalyticsOutboxEvent:
    mapping = typing.cast(typing.Mapping[str, typing.Any], row)
    from gameclub_backend.modules.analytics.heavy_events import AnalyticsEventType

    return AnalyticsOutboxEvent(
        id=mapping["id"],
        event_type=AnalyticsEventType(str(mapping["event_type"])),
        event_version=int(mapping["event_version"]),
        aggregate_type=str(mapping["aggregate_type"]),
        aggregate_id=str(mapping["aggregate_id"]),
        occurred_at=_aware(mapping["occurred_at"]),
        idempotency_key=str(mapping["idempotency_key"]),
        payload=dict(mapping["payload"]),
        created_at=_aware(mapping["created_at"]),
    )


def _job_from_row(row: object, artifact_token: str | None = None) -> ReportJob:
    import typing

    mapping = typing.cast(typing.Mapping[str, typing.Any], row)
    return ReportJob(
        id=mapping["id"],
        requested_by=str(mapping["requested_by"]),
        report_name=str(mapping["report_name"]),
        export_format=ExportFormat(str(mapping["export_format"])),
        idempotency_key=str(mapping["idempotency_key"]),
        include_pii=bool(mapping["include_pii"]),
        timeout_seconds=int(mapping["timeout_seconds"]),
        max_attempts=int(mapping["max_attempts"]),
        status=ReportStatus(str(mapping["status"])),
        attempts=int(mapping["attempts"]),
        created_at=_aware(mapping["created_at"]),
        started_at=_aware(mapping["started_at"]) if mapping["started_at"] else None,
        completed_at=_aware(mapping["completed_at"]) if mapping["completed_at"] else None,
        error=str(mapping["error"]) if mapping["error"] else None,
        artifact_token=artifact_token,
        artifact_content_type=str(mapping["artifact_content_type"])
        if mapping["artifact_content_type"]
        else None,
        artifact_sha256=str(mapping["artifact_sha256"]) if mapping["artifact_sha256"] else None,
        artifact_size=int(mapping["artifact_size"])
        if mapping["artifact_size"] is not None
        else None,
    )


def _job_with_artifact(job: ReportJob, content_type: str, sha256: str, size: int) -> ReportJob:
    from dataclasses import replace

    return replace(
        job,
        status=ReportStatus.SUCCEEDED,
        artifact_content_type=content_type,
        artifact_sha256=sha256,
        artifact_size=size,
        completed_at=datetime.datetime.now(datetime.UTC),
    )
