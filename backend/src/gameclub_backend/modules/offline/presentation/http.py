from __future__ import annotations

import datetime
import typing
import uuid
from typing import Any

from fastapi import APIRouter, Depends
from fastapi import HTTPException as FastAPIHTTPException
from pydantic import BaseModel, Field

from gameclub_backend.modules.auth.domain import Principal, SubjectType
from gameclub_backend.modules.offline.application.service import OfflineReplayService
from gameclub_backend.modules.offline.domain import (
    OfflineBatch,
    OfflineOperation,
    OfflineOperationKind,
    OfflineOperationResult,
    OfflineOperationStatus,
)
from gameclub_backend.modules.sessions.presentation.http import SessionSnapshotResponse
from gameclub_backend.presentation.http.auth import get_current_principal

DevicePrincipal = typing.Annotated[Principal, Depends(get_current_principal)]


class OfflineOperationRequest(BaseModel):
    id: uuid.UUID
    sequence: int = Field(ge=1)
    kind: OfflineOperationKind
    payload: dict[str, Any] = Field(default_factory=dict)
    snapshot_version: int = Field(ge=1)
    idempotency_key: str = Field(min_length=1, max_length=128)
    checksum: str = Field(min_length=64, max_length=64)
    created_at: datetime.datetime


class OfflineBatchRequest(BaseModel):
    protocol_version: int = Field(default=1, ge=1)
    device_id: str = Field(min_length=1, max_length=128)
    session_id: uuid.UUID
    operations: list[OfflineOperationRequest] = Field(min_length=1, max_length=100)


class OfflineOperationResultResponse(BaseModel):
    operation_id: uuid.UUID
    sequence: int
    status: OfflineOperationStatus
    message: str
    applied_at: str | None

    @classmethod
    def from_domain(cls, result: OfflineOperationResult) -> OfflineOperationResultResponse:
        return cls(
            operation_id=result.operation_id,
            sequence=result.sequence,
            status=result.status,
            message=result.message,
            applied_at=result.applied_at.isoformat() if result.applied_at else None,
        )


class OfflineBatchResponse(BaseModel):
    protocol_version: int
    session_id: uuid.UUID
    results: list[OfflineOperationResultResponse]
    snapshot: SessionSnapshotResponse | None


def create_router(service: OfflineReplayService) -> APIRouter:
    router = APIRouter(prefix="/api/v1/offline", tags=["offline"])

    @router.post("/replay", response_model=OfflineBatchResponse)
    async def replay_batch(
        body: OfflineBatchRequest,
        principal: DevicePrincipal,
    ) -> OfflineBatchResponse:
        if principal.subject_type is not SubjectType.DEVICE or not principal.can(
            "workstations.connect"
        ):
            raise FastAPIHTTPException(status_code=403, detail="Device identity is required")
        try:
            operations = tuple(
                OfflineOperation.create(
                    operation_id=item.id,
                    session_id=body.session_id,
                    device_id=body.device_id,
                    sequence=item.sequence,
                    kind=item.kind,
                    payload=item.payload,
                    snapshot_version=item.snapshot_version,
                    idempotency_key=item.idempotency_key,
                    created_at=item.created_at,
                )
                for item in body.operations
            )
            batch = OfflineBatch(
                protocol_version=body.protocol_version,
                device_id=body.device_id,
                session_id=body.session_id,
                operations=operations,
            )
            result = await service.replay(batch, actor_device_id=principal.subject_id)
        except ValueError as error:
            raise FastAPIHTTPException(status_code=400, detail=str(error)) from error
        return OfflineBatchResponse(
            protocol_version=result.protocol_version,
            session_id=result.session_id,
            results=[OfflineOperationResultResponse.from_domain(item) for item in result.results],
            snapshot=(
                SessionSnapshotResponse.from_domain(result.snapshot)
                if result.snapshot is not None
                else None
            ),
        )

    return router
