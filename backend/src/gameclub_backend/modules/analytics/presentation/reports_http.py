from __future__ import annotations

import typing
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import Response
from pydantic import BaseModel, Field

from gameclub_backend.modules.analytics.reporting import (
    ExportFormat,
    ReportJob,
    ReportJobService,
    ReportPermissionError,
    ReportStatus,
)
from gameclub_backend.modules.auth.domain import Principal
from gameclub_backend.presentation.http.auth import require_permissions

Reader = typing.Annotated[Principal, Depends(require_permissions("analytics.read"))]
Exporter = typing.Annotated[
    Principal,
    Depends(require_permissions("analytics.read", "analytics.export")),
]


class ReportCreateRequest(BaseModel):
    report_name: str = Field(min_length=1, max_length=128)
    export_format: ExportFormat
    idempotency_key: str = Field(min_length=1, max_length=255)
    include_pii: bool = False
    timeout_seconds: int = Field(default=300, ge=1, le=3600)
    max_attempts: int = Field(default=3, ge=1, le=10)


class ReportJobResponse(BaseModel):
    id: uuid.UUID
    report_name: str
    export_format: ExportFormat
    status: ReportStatus
    attempts: int
    max_attempts: int
    created_at: str
    started_at: str | None
    completed_at: str | None
    error: str | None
    artifact_size: int | None
    artifact_sha256: str | None
    download_url: str | None = None

    @classmethod
    def from_domain(cls, job: ReportJob, *, download_url: str | None = None) -> ReportJobResponse:
        return cls(
            id=job.id,
            report_name=job.report_name,
            export_format=job.export_format,
            status=job.status,
            attempts=job.attempts,
            max_attempts=job.max_attempts,
            created_at=job.created_at.isoformat(),
            started_at=job.started_at.isoformat() if job.started_at else None,
            completed_at=job.completed_at.isoformat() if job.completed_at else None,
            error=job.error,
            artifact_size=job.artifact_size,
            artifact_sha256=job.artifact_sha256,
            download_url=download_url,
        )


def create_reports_router(
    service: ReportJobService,
    enqueue: typing.Callable[[str], typing.Any],
) -> APIRouter:
    router = APIRouter(prefix="/api/v2/analytics/reports", tags=["analytics-reports"])

    @router.post("", response_model=ReportJobResponse, status_code=status.HTTP_202_ACCEPTED)
    async def create_report(
        principal: Exporter,
        payload: ReportCreateRequest,
    ) -> ReportJobResponse:
        try:
            job = await service.create_job(
                requested_by=principal.subject_id,
                permissions=principal.permissions,
                report_name=payload.report_name,
                export_format=payload.export_format,
                idempotency_key=payload.idempotency_key,
                include_pii=payload.include_pii,
                timeout_seconds=payload.timeout_seconds,
                max_attempts=payload.max_attempts,
            )
        except ReportPermissionError as error:
            raise HTTPException(status_code=403, detail=str(error)) from error
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

        if job.status is ReportStatus.PENDING:
            enqueue(str(job.id))
        download_url = None
        if job.artifact_token:
            download_url = f"/api/v2/analytics/reports/{job.id}/artifact?token={job.artifact_token}"
        return ReportJobResponse.from_domain(job, download_url=download_url)

    @router.get("/{job_id}", response_model=ReportJobResponse)
    async def get_report(principal: Reader, job_id: uuid.UUID) -> ReportJobResponse:
        del principal
        try:
            job = await service.get(job_id)
        except KeyError as error:
            raise HTTPException(status_code=404, detail="Report job not found") from error
        return ReportJobResponse.from_domain(job)

    @router.get("/{job_id}/artifact")
    async def download_report(
        principal: Reader,
        job_id: uuid.UUID,
        token: str = Query(min_length=1),
    ) -> Response:
        try:
            artifact = await service.read_artifact(job_id, token, principal.permissions)
        except (KeyError, ReportPermissionError) as error:
            raise HTTPException(status_code=404, detail="Artifact not found") from error
        return Response(
            content=artifact.content,
            media_type=artifact.content_type,
            headers={
                "Content-Length": str(artifact.size),
                "ETag": artifact.sha256,
            },
        )

    return router
