import typing
import uuid

from fastapi import APIRouter, Depends, Header, Query, status
from pydantic import BaseModel, Field

from gameclub_backend.modules.auth.domain import Principal
from gameclub_backend.modules.billing.domain import MeterStatus
from gameclub_backend.modules.sessions.application.service import SessionService
from gameclub_backend.modules.sessions.domain import Session, SessionSnapshot, SessionStatus
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
    guest_payment_id: uuid.UUID | None = None
    entitlement_id: uuid.UUID | None = None


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
    guest_payment_id: uuid.UUID | None
    login_grant_minutes: int
    entitlement_id: uuid.UUID | None

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
            guest_payment_id=session.guest_payment_id,
            login_grant_minutes=session.login_grant_minutes,
            entitlement_id=session.entitlement_id,
        )


class SnapshotEntitlementResponse(BaseModel):
    id: uuid.UUID
    tariff_id: uuid.UUID
    zone_id: str | None
    duration_minutes: int
    remaining_minutes: int
    status: str
    queue_position: int
    window_start_minute: int | None
    window_end_minute: int | None
    window_timezone: str | None

    @classmethod
    def from_domain(cls, item) -> "SnapshotEntitlementResponse":
        return cls(
            id=item.id,
            tariff_id=item.tariff_id,
            zone_id=item.zone_id,
            duration_minutes=item.duration_minutes,
            remaining_minutes=item.remaining_minutes,
            status=item.status.value,
            queue_position=item.queue_position,
            window_start_minute=item.window_start_minute,
            window_end_minute=item.window_end_minute,
            window_timezone=item.window_timezone,
        )


class SnapshotMeterResponse(BaseModel):
    session_id: uuid.UUID
    billed_minutes: int
    billed_cents: int
    package_minutes: int
    active_entitlement_id: uuid.UUID | None
    status: MeterStatus
    updated_at: str

    @classmethod
    def from_domain(cls, meter) -> "SnapshotMeterResponse":
        return cls(
            session_id=meter.session_id,
            billed_minutes=meter.billed_minutes,
            billed_cents=meter.billed_cents,
            package_minutes=meter.package_minutes,
            active_entitlement_id=meter.active_entitlement_id,
            status=meter.status,
            updated_at=meter.updated_at.isoformat(),
        )


class SessionSnapshotResponse(BaseModel):
    schema_version: int
    server_time: str
    session: SessionResponse
    workstation_id: uuid.UUID
    device_id: str
    zone_id: str | None
    client_id: uuid.UUID | None
    balance_cents: int | None
    balance_bonus: int | None
    active_entitlement: SnapshotEntitlementResponse | None
    entitlements: list[SnapshotEntitlementResponse]
    meter: SnapshotMeterResponse | None
    allowed_actions: list[str]

    @classmethod
    def from_domain(cls, snapshot: SessionSnapshot) -> "SessionSnapshotResponse":
        return cls(
            schema_version=snapshot.schema_version,
            server_time=snapshot.server_time.isoformat(),
            session=SessionResponse.from_domain(snapshot.session),
            workstation_id=snapshot.workstation_id,
            device_id=snapshot.device_id,
            zone_id=snapshot.zone_id,
            client_id=snapshot.client_id,
            balance_cents=snapshot.balance_cents,
            balance_bonus=snapshot.balance_bonus,
            active_entitlement=(
                SnapshotEntitlementResponse.from_domain(snapshot.active_entitlement)
                if snapshot.active_entitlement
                else None
            ),
            entitlements=[
                SnapshotEntitlementResponse.from_domain(item) for item in snapshot.entitlements
            ],
            meter=SnapshotMeterResponse.from_domain(snapshot.meter) if snapshot.meter else None,
            allowed_actions=list(snapshot.allowed_actions),
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

    @router.get("/{session_id}/snapshot", response_model=SessionSnapshotResponse)
    async def get_session_snapshot(
        session_id: uuid.UUID,
        principal: Operator,
    ) -> SessionSnapshotResponse:
        del principal
        return SessionSnapshotResponse.from_domain(await service.snapshot(session_id))

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
