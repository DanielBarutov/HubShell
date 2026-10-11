import json
import typing
import uuid

from fastapi import APIRouter, Depends, Header, status
from pydantic import BaseModel, Field

from gameclub_backend.application.errors import ApplicationError, ErrorCode
from gameclub_backend.modules.auth.domain import Principal
from gameclub_backend.modules.workstations.application.commands import (
    DEVICE_COMMAND_TYPES,
    WorkstationCommandService,
)
from gameclub_backend.modules.workstations.domain_commands import WorkstationCommand
from gameclub_backend.presentation.http.auth import require_permissions

Operator = typing.Annotated[Principal, Depends(require_permissions("workstations.manage"))]


class DeviceCommandRequest(BaseModel):
    command_type: str = Field(min_length=1, max_length=64)
    payload: dict[str, typing.Any] = Field(default_factory=dict)


class DeviceCommandResponse(BaseModel):
    id: uuid.UUID
    workstation_id: uuid.UUID
    command_type: str
    status: str
    expires_at: str

    @classmethod
    def from_domain(cls, command: WorkstationCommand) -> "DeviceCommandResponse":
        return cls(
            id=command.id,
            workstation_id=command.workstation_id,
            command_type=command.command_type,
            status=command.status.value,
            expires_at=command.expires_at.isoformat(),
        )


def create_router(command_service: WorkstationCommandService) -> APIRouter:
    router = APIRouter(prefix="/api/workstations", tags=["workstations"])

    @router.post(
        "/{workstation_id}/device-commands",
        response_model=DeviceCommandResponse,
        status_code=status.HTTP_202_ACCEPTED,
    )
    async def dispatch_device_command(
        workstation_id: uuid.UUID,
        body: DeviceCommandRequest,
        principal: Operator,
        idempotency_key: str = Header(min_length=1, alias="Idempotency-Key"),
    ) -> DeviceCommandResponse:
        del principal
        if body.command_type not in DEVICE_COMMAND_TYPES:
            raise ApplicationError(
                ErrorCode.INVALID_ARGUMENT,
                "Unsupported device command",
            )
        command = await command_service.dispatch(
            workstation_id=workstation_id,
            command_type=body.command_type,
            payload_json=json.dumps(body.payload),
            idempotency_key=idempotency_key,
        )
        return DeviceCommandResponse.from_domain(command)

    return router
