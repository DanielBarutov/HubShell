import typing
import uuid

from fastapi import APIRouter, Depends, Header, Query, status
from pydantic import BaseModel, Field

from gameclub_backend.modules.auth.domain import Principal
from gameclub_backend.modules.sessions.application.service import SessionService
from gameclub_backend.modules.sessions.domain import Session, SessionStatus
from gameclub_backend.presentation.http.auth import require_permissions

Operator = typing.Annotated[Principal, Depends(require_permissions("sessions.manage"))]
QueryWorkstationId = typing.Annotated[uuid.UUID | None, Query()]
QueryActiveOnly = typing.Annotated[bool, Query()]


class StartSessionRequest(BaseModel):
    workstation_id: uuid.UUID
    client_id: uuid.UUID | None = None
    guest_id: uuid.UUID | None = None
    guest_name: str | None = Field(default=None, max_length=128)
    source: str = Field(default="operator", min_length=1, max_length=32)
    reservation_id: uuid.UUID | None = None
    tariff_id: uuid.UUID | None = None
    tariff_quantity: int = Field(default=1, ge=1, le=100)


class InterruptSessionRequest(BaseModel):
    reason: str = Field(default="Клиент завершил сессию раньше", min_length=1, max_length=256)


class SessionResponse(BaseModel):
    id: uuid.UUID
    workstation_id: uuid.UUID
    client_id: uuid.UUID | None
    guest_id: uuid.UUID | None
    guest_name: str | None
    status: SessionStatus
    started_at: str
    ended_at: str | None
    source: str
    created_by: str
    created_at: str
    reservation_id: uuid.UUID | None
    idempotency_key: str | None
    tariff_id: uuid.UUID | None
    tariff_quantity: int

    @classmethod
    def from_domain(cls, session: Session) -> "SessionResponse":
        return cls(
            id=session.id,
            workstation_id=session.workstation_id,
            client_id=session.client_id,
            guest_id=session.guest_id,
            guest_name=session.guest_name,
            status=session.status,
            started_at=session.started_at.isoformat(),
            ended_at=session.ended_at.isoformat() if session.ended_at else None,
            source=session.source,
            created_by=session.created_by,
            created_at=session.created_at.isoformat(),
            reservation_id=session.reservation_id,
            idempotency_key=session.idempotency_key,
            tariff_id=session.tariff_id,
            tariff_quantity=session.tariff_quantity,
        )


def create_router(service: SessionService) -> APIRouter:
    router = APIRouter(prefix="/api/v1/sessions", tags=["sessions"])

    @router.post("", response_model=SessionResponse, status_code=status.HTTP_201_CREATED)
    async def start_session(
        body: StartSessionRequest,
        principal: Operator,
        idempotency_key: str = Header(min_length=1, alias="Idempotency-Key"),
    ) -> SessionResponse:
        session = await service.start(
            created_by=principal.subject_id,
            idempotency_key=idempotency_key,
            **body.model_dump(),
        )
        return SessionResponse.from_domain(session)

    @router.get("", response_model=list[SessionResponse])
    async def list_sessions(
        principal: Operator,
        workstation_id: QueryWorkstationId = None,
        active_only: QueryActiveOnly = False,
    ) -> list[SessionResponse]:
        del principal
        sessions = await service.list(workstation_id, active_only)
        return [SessionResponse.from_domain(item) for item in sessions]

    @router.get("/{session_id}", response_model=SessionResponse)
    async def get_session(
        session_id: uuid.UUID,
        principal: Operator,
    ) -> SessionResponse:
        del principal
        return SessionResponse.from_domain(await service.get(session_id))

    @router.post("/{session_id}/stop", response_model=SessionResponse)
    async def stop_session(
        session_id: uuid.UUID,
        principal: Operator,
    ) -> SessionResponse:
        del principal
        return SessionResponse.from_domain(await service.stop(session_id))

    @router.post("/{session_id}/interrupt", response_model=SessionResponse)
    async def interrupt_session(
        session_id: uuid.UUID,
        body: InterruptSessionRequest,
        principal: Operator,
        idempotency_key: str = Header(min_length=1, alias="Idempotency-Key"),
    ) -> SessionResponse:
        session = await service.interrupt(
            session_id=session_id,
            interrupted_by=principal.subject_id,
            reason=body.reason,
            idempotency_key=idempotency_key,
        )
        return SessionResponse.from_domain(session)

    return router
