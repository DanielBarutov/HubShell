import datetime
import typing
import uuid

from fastapi import APIRouter, Depends, Header, Query, status
from pydantic import BaseModel, Field

from gameclub_backend.modules.auth.domain import Principal
from gameclub_backend.modules.reservations.application.service import ReservationService
from gameclub_backend.modules.reservations.domain import (
    EntryDecision,
    Reservation,
    ReservationAvailability,
    ReservationStatus,
)
from gameclub_backend.presentation.http.auth import require_permissions

Operator = typing.Annotated[Principal, Depends(require_permissions("reservations.manage"))]
QueryDatetime = typing.Annotated[datetime.datetime, Query()]
QueryEntryAt = typing.Annotated[datetime.datetime | None, Query()]


class CreateReservationRequest(BaseModel):
    workstation_ids: list[uuid.UUID] = Field(min_length=1)
    start_at: datetime.datetime
    end_at: datetime.datetime
    client_id: uuid.UUID | None = None
    guest_id: uuid.UUID | None = None
    guest_name: str | None = Field(default=None, max_length=128)
    notes: str | None = Field(default=None, max_length=500)
    tariff_id: uuid.UUID | None = None


class UpdateReservationRequest(BaseModel):
    workstation_ids: list[uuid.UUID] = Field(min_length=1)
    start_at: datetime.datetime
    end_at: datetime.datetime
    client_id: uuid.UUID | None = None
    guest_id: uuid.UUID | None = None
    guest_name: str | None = Field(default=None, max_length=128)
    notes: str | None = Field(default=None, max_length=500)
    tariff_id: uuid.UUID | None = None


class CheckAvailabilityRequest(BaseModel):
    workstation_ids: list[uuid.UUID] = Field(min_length=1)
    start_at: datetime.datetime
    end_at: datetime.datetime


class CheckAvailabilityResponse(BaseModel):
    available: bool
    conflicting_reservation_ids: tuple[uuid.UUID, ...]
    reason: str | None

    @classmethod
    def from_domain(cls, availability: ReservationAvailability) -> "CheckAvailabilityResponse":
        return cls.model_validate(availability, from_attributes=True)


class EntryDecisionResponse(BaseModel):
    allowed: bool
    reason: str
    reservation_id: uuid.UUID | None
    assigned_client_id: uuid.UUID | None
    starts_at: datetime.datetime | None
    ends_at: datetime.datetime | None

    @classmethod
    def from_domain(cls, decision: EntryDecision) -> "EntryDecisionResponse":
        return cls.model_validate(decision, from_attributes=True)


class ReservationResponse(BaseModel):
    id: uuid.UUID
    workstation_ids: tuple[uuid.UUID, ...]
    client_id: uuid.UUID | None
    guest_id: uuid.UUID | None
    guest_name: str | None
    start_at: datetime.datetime
    end_at: datetime.datetime
    status: ReservationStatus
    notes: str | None
    tariff_id: uuid.UUID | None
    created_by: str
    created_at: datetime.datetime
    cancelled_at: datetime.datetime | None
    idempotency_key: str | None

    @classmethod
    def from_domain(cls, reservation: Reservation) -> "ReservationResponse":
        return cls.model_validate(reservation, from_attributes=True)


def create_router(service: ReservationService) -> APIRouter:
    router = APIRouter(prefix="/api/v1/reservations", tags=["reservations"])

    @router.get("", response_model=list[ReservationResponse])
    async def list_reservations(
        principal: Operator,
        start_at: QueryDatetime,
        end_at: QueryDatetime,
    ) -> list[ReservationResponse]:
        del principal
        reservations = await service.list(start_at, end_at)
        return [ReservationResponse.from_domain(item) for item in reservations]

    @router.post("", response_model=ReservationResponse, status_code=status.HTTP_201_CREATED)
    async def create_reservation(
        body: CreateReservationRequest,
        principal: Operator,
        idempotency_key: str = Header(min_length=1, alias="Idempotency-Key"),
    ) -> ReservationResponse:
        reservation = await service.create(
            created_by=principal.subject_id,
            idempotency_key=idempotency_key,
            **body.model_dump(),
        )
        return ReservationResponse.from_domain(reservation)

    @router.post("/check-availability", response_model=CheckAvailabilityResponse)
    async def check_availability(
        body: CheckAvailabilityRequest,
        principal: Operator,
    ) -> CheckAvailabilityResponse:
        del principal
        availability = await service.check_availability(**body.model_dump())
        return CheckAvailabilityResponse.from_domain(availability)

    @router.get("/entry-decision", response_model=EntryDecisionResponse)
    async def check_entry(
        workstation_id: uuid.UUID,
        principal: Operator,
        client_id: uuid.UUID | None = None,
        guest_id: uuid.UUID | None = None,
        at: QueryEntryAt = None,
    ) -> EntryDecisionResponse:
        del principal
        decision = await service.check_entry(
            workstation_id=workstation_id,
            client_id=client_id,
            guest_id=guest_id,
            now=at,
        )
        return EntryDecisionResponse.from_domain(decision)

    @router.post("/{reservation_id}/cancel", response_model=ReservationResponse)
    async def cancel_reservation(
        reservation_id: uuid.UUID,
        principal: Operator,
    ) -> ReservationResponse:
        del principal
        return ReservationResponse.from_domain(await service.cancel(reservation_id))

    @router.get("/{reservation_id}", response_model=ReservationResponse)
    async def get_reservation(
        reservation_id: uuid.UUID,
        principal: Operator,
    ) -> ReservationResponse:
        del principal
        return ReservationResponse.from_domain(await service.get(reservation_id))

    @router.patch("/{reservation_id}", response_model=ReservationResponse)
    async def update_reservation(
        reservation_id: uuid.UUID,
        body: UpdateReservationRequest,
        principal: Operator,
    ) -> ReservationResponse:
        del principal
        return ReservationResponse.from_domain(
            await service.update(reservation_id, **body.model_dump())
        )

    @router.post("/{reservation_id}/activate", response_model=ReservationResponse)
    async def activate_reservation(
        reservation_id: uuid.UUID,
        principal: Operator,
    ) -> ReservationResponse:
        del principal
        return ReservationResponse.from_domain(await service.activate(reservation_id))

    @router.post("/{reservation_id}/complete", response_model=ReservationResponse)
    async def complete_reservation(
        reservation_id: uuid.UUID,
        principal: Operator,
    ) -> ReservationResponse:
        del principal
        return ReservationResponse.from_domain(await service.complete(reservation_id))

    @router.post("/{reservation_id}/no-show", response_model=ReservationResponse)
    async def mark_no_show_reservation(
        reservation_id: uuid.UUID,
        principal: Operator,
    ) -> ReservationResponse:
        del principal
        return ReservationResponse.from_domain(await service.mark_no_show(reservation_id))

    return router
