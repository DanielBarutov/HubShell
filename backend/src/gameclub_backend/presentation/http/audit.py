import datetime
import typing
import uuid

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from gameclub_backend.application.audit import AuditEvent, AuditRepository
from gameclub_backend.modules.auth.domain import Principal
from gameclub_backend.presentation.http.auth import require_permissions

Operator = typing.Annotated[Principal, Depends(require_permissions("audit.read"))]


class AuditEventResponse(BaseModel):
    id: uuid.UUID
    actor_id: str | None
    action: str
    resource_path: str
    outcome: str
    status_code: int
    request_id: str | None
    created_at: datetime.datetime

    @classmethod
    def from_domain(cls, event: AuditEvent) -> "AuditEventResponse":
        return cls(
            id=event.id,
            actor_id=event.actor_id,
            action=event.action,
            resource_path=event.resource_path,
            outcome=event.outcome,
            status_code=event.status_code,
            request_id=event.request_id,
            created_at=event.created_at,
        )


def create_router(audit_repository: AuditRepository) -> APIRouter:
    router = APIRouter(prefix="/api/v1/audit", tags=["audit"])

    @router.get("/events", response_model=list[AuditEventResponse])
    async def list_events(
        principal: Operator,
        limit: int = Query(default=20, ge=1, le=100),
    ) -> list[AuditEventResponse]:
        del principal
        events = await audit_repository.list_recent(limit)
        return [AuditEventResponse.from_domain(event) for event in events]

    return router
