from __future__ import annotations

import datetime
import hashlib
import secrets
import uuid
from dataclasses import replace

from gameclub_backend.modules.analytics.heavy_events import (
    AnalyticsOutboxEvent,
    bucket_start,
    projection_delta,
)
from gameclub_backend.modules.analytics.reporting import ReportJob, ReportStatus


class InMemoryAnalyticsHeavyRepository:
    def __init__(self) -> None:
        self._events: dict[uuid.UUID, AnalyticsOutboxEvent] = {}
        self._event_ids_by_key: dict[str, uuid.UUID] = {}
        self._applied: set[uuid.UUID] = set()
        self._rows: dict[tuple[str, str, str], dict[str, object]] = {}
        self._jobs: dict[uuid.UUID, ReportJob] = {}
        self._job_ids_by_key: dict[str, uuid.UUID] = {}
        self._artifact_bytes: dict[uuid.UUID, bytes] = {}
        self._artifact_tokens: dict[uuid.UUID, str] = {}

    async def append_event(self, event: AnalyticsOutboxEvent) -> AnalyticsOutboxEvent:
        existing_id = self._event_ids_by_key.get(event.idempotency_key)
        if existing_id is not None:
            return self._events[existing_id]
        self._events[event.id] = event
        self._event_ids_by_key[event.idempotency_key] = event.id
        return event

    async def list_unapplied_events(self, limit: int) -> tuple[AnalyticsOutboxEvent, ...]:
        events = [event for event in self._events.values() if event.id not in self._applied]
        return tuple(sorted(events, key=lambda item: (item.occurred_at, str(item.id)))[:limit])

    async def list_events(self) -> tuple[AnalyticsOutboxEvent, ...]:
        return tuple(
            sorted(self._events.values(), key=lambda item: (item.occurred_at, str(item.id)))
        )

    async def apply_event(self, event: AnalyticsOutboxEvent) -> bool:
        if event.id in self._applied:
            return False
        delta = projection_delta(event)
        if delta is not None:
            metric_key, value_cents, quantity, dimensions = delta
            bucket = bucket_start(event.occurred_at).isoformat()
            dimensions_key = ";".join(f"{key}={dimensions[key]}" for key in sorted(dimensions))
            key = (metric_key, bucket, dimensions_key)
            row = self._rows.setdefault(
                key,
                {
                    "metric_key": metric_key,
                    "bucket_start": bucket,
                    "dimensions": dimensions,
                    "value_cents": 0,
                    "quantity": 0,
                    "event_count": 0,
                },
            )
            row["value_cents"] = _as_int(row["value_cents"]) + value_cents
            row["quantity"] = _as_int(row["quantity"]) + quantity
            row["event_count"] = _as_int(row["event_count"]) + 1
        self._applied.add(event.id)
        return True

    async def rebuild_projection(self) -> None:
        self._applied.clear()
        self._rows.clear()
        for event in sorted(
            self._events.values(), key=lambda item: (item.occurred_at, str(item.id))
        ):
            await self.apply_event(event)

    async def read_projection(self, metric_key: str | None = None) -> tuple[dict[str, object], ...]:
        rows = tuple(self._rows.values())
        if metric_key is not None:
            rows = tuple(row for row in rows if row["metric_key"] == metric_key)
        return tuple(
            dict(row)
            for row in sorted(
                rows, key=lambda item: (str(item["bucket_start"]), str(item["metric_key"]))
            )
        )

    async def create_report_job(self, job: ReportJob) -> ReportJob:
        existing_id = self._job_ids_by_key.get(job.idempotency_key)
        if existing_id is not None:
            return self._jobs[existing_id]
        self._jobs[job.id] = job
        self._job_ids_by_key[job.idempotency_key] = job.id
        return job

    async def get_report_job(self, job_id: uuid.UUID) -> ReportJob:
        return self._jobs[job_id]

    async def update_report_job(self, job: ReportJob) -> ReportJob:
        self._jobs[job.id] = job
        return job

    async def store_artifact(self, job: ReportJob, content: bytes, content_type: str) -> ReportJob:
        token = job.artifact_token or secrets.token_urlsafe(32)
        updated = replace(
            job,
            status=ReportStatus.SUCCEEDED,
            artifact_token=token,
            artifact_content_type=content_type,
            artifact_sha256=hashlib.sha256(content).hexdigest(),
            artifact_size=len(content),
            completed_at=datetime.datetime.now(datetime.UTC),
        )
        self._artifact_bytes[job.id] = content
        self._artifact_tokens[job.id] = hashlib.sha256(token.encode()).hexdigest()
        return await self.update_report_job(updated)

    async def read_artifact(self, job: ReportJob, token: str) -> tuple[bytes, str, str, int]:
        expected = self._artifact_tokens.get(job.id)
        if expected is None or not secrets.compare_digest(
            expected, hashlib.sha256(token.encode()).hexdigest()
        ):
            raise PermissionError("Invalid artifact reference")
        return (
            self._artifact_bytes[job.id],
            job.artifact_content_type or "application/octet-stream",
            job.artifact_sha256 or "",
            job.artifact_size or 0,
        )


def _as_int(value: object) -> int:
    return int(value) if isinstance(value, (int, float, str)) else 0
