import datetime
import typing
import uuid

from fastapi import APIRouter, Depends, Header
from pydantic import BaseModel

from gameclub_backend.modules.auth.domain import Principal
from gameclub_backend.modules.sessions.application.transfer import SessionTransferService
from gameclub_backend.modules.sessions.domain import SessionTransferOffer
from gameclub_backend.modules.workstations.domain_commands import (
    WorkstationCommand,
    WorkstationCommandStatus,
)
from gameclub_backend.presentation.http.auth import require_permissions

Operator = typing.Annotated[Principal, Depends(require_permissions("sessions.manage"))]


class CreateTransferOfferRequest(BaseModel):
    session_id: uuid.UUID
    target_workstation_id: uuid.UUID


class TransferOfferResponse(BaseModel):
    id: uuid.UUID
    session_id: uuid.UUID
    client_id: uuid.UUID
    source_workstation_id: uuid.UUID
    target_workstation_id: uuid.UUID
    token: str
    status: str
    requires_package_burn: bool
    warning: str | None
    created_at: datetime.datetime
    expires_at: datetime.datetime
    confirmed_at: datetime.datetime | None

    @classmethod
    def from_domain(cls, offer: SessionTransferOffer) -> "TransferOfferResponse":
        return cls.model_validate(offer, from_attributes=True)


class ConfirmTransferResponse(BaseModel):
    offer: TransferOfferResponse
    session_id: uuid.UUID
    workstation_id: uuid.UUID
    status: str


class RestartCommandResponse(BaseModel):
    id: uuid.UUID
    workstation_id: uuid.UUID
    command_type: str
    status: WorkstationCommandStatus
    idempotency_key: str
    created_at: datetime.datetime
    expires_at: datetime.datetime
    acknowledged_at: datetime.datetime | None
    acknowledgement_message: str | None

    @classmethod
    def from_domain(cls, command: WorkstationCommand) -> "RestartCommandResponse":
        return cls.model_validate(command, from_attributes=True)


def create_router(service: SessionTransferService) -> APIRouter:
    router = APIRouter(prefix="/api/v1/session-transfers", tags=["session-transfers"])

    @router.post("/offers", response_model=TransferOfferResponse)
    async def create_offer(
        body: CreateTransferOfferRequest,
        principal: Operator,
        idempotency_key: str = Header(min_length=1, alias="Idempotency-Key"),
    ) -> TransferOfferResponse:
        del principal
        offer = await service.create_offer(
            session_id=body.session_id,
            target_workstation_id=body.target_workstation_id,
            idempotency_key=idempotency_key,
        )
        return TransferOfferResponse.from_domain(offer)

    @router.get("/offers/{offer_id}", response_model=TransferOfferResponse)
    async def get_offer(offer_id: uuid.UUID, principal: Operator) -> TransferOfferResponse:
        del principal
        return TransferOfferResponse.from_domain(await service.get(offer_id))

    @router.get(
        "/offers/{offer_id}/restart",
        response_model=RestartCommandResponse,
    )
    async def get_restart_command(
        offer_id: uuid.UUID,
        principal: Operator,
    ) -> RestartCommandResponse:
        del principal
        return RestartCommandResponse.from_domain(await service.restart_status(offer_id))

    @router.post("/offers/{offer_id}/confirm", response_model=ConfirmTransferResponse)
    async def confirm_offer(
        offer_id: uuid.UUID,
        principal: Operator,
        idempotency_key: str = Header(min_length=1, alias="Idempotency-Key"),
    ) -> ConfirmTransferResponse:
        del principal
        offer, session = await service.confirm(offer_id, idempotency_key)
        return ConfirmTransferResponse(
            offer=TransferOfferResponse.from_domain(offer),
            session_id=session.id,
            workstation_id=session.workstation_id,
            status=session.status.value,
        )

    return router
