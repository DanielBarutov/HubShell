import json
import typing
import uuid

from fastapi import APIRouter, Depends, Header, status
from pydantic import BaseModel, Field

from gameclub_backend.modules.auth.domain import Principal
from gameclub_backend.modules.workstations.application.commands import (
    WorkstationCommandService,
)
from gameclub_backend.modules.workstations.application.service import WorkstationService
from gameclub_backend.modules.workstations.domain import Workstation, WorkstationStatus
from gameclub_backend.modules.workstations.domain_commands import (
    WorkstationCommand,
    WorkstationCommandStatus,
)
from gameclub_backend.presentation.http.auth import require_permissions

Operator = typing.Annotated[Principal, Depends(require_permissions("workstations.manage"))]


class RegisterWorkstationRequest(BaseModel):
    device_id: str = Field(min_length=1, max_length=128)
    name: str = Field(min_length=1, max_length=128)
    group_id: str | None = Field(default=None, max_length=128)
    position: int | None = Field(default=None, ge=0)
    client_version: str | None = Field(default=None, max_length=64)
    capabilities: list[str] = Field(default_factory=list)


class UpdateWorkstationRequest(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    group_id: str | None = Field(default=None, max_length=128)
    position: int | None = Field(default=None, ge=0)


class HeartbeatRequest(BaseModel):
    device_id: str = Field(min_length=1, max_length=128)
    client_version: str | None = Field(default=None, max_length=64)
    capabilities: list[str] = Field(default_factory=list)


class DisableWorkstationRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=255)


class DispatchCommandRequest(BaseModel):
    command_type: str = Field(min_length=1, max_length=64)
    payload: dict[str, typing.Any] = Field(default_factory=dict)


class WorkstationCommandResponse(BaseModel):
    id: uuid.UUID
    workstation_id: uuid.UUID
    command_type: str
    payload: dict[str, typing.Any]
    idempotency_key: str
    status: WorkstationCommandStatus
    created_at: str
    expires_at: str
    acknowledged_at: str | None
    acknowledgement_message: str | None

    @classmethod
    def from_domain(cls, command: WorkstationCommand) -> "WorkstationCommandResponse":
        return cls(
            id=command.id,
            workstation_id=command.workstation_id,
            command_type=command.command_type,
            payload=json.loads(command.payload_json),
            idempotency_key=command.idempotency_key,
            status=command.status,
            created_at=command.created_at.isoformat(),
            expires_at=command.expires_at.isoformat(),
            acknowledged_at=(
                command.acknowledged_at.isoformat() if command.acknowledged_at else None
            ),
            acknowledgement_message=command.acknowledgement_message,
        )


class WorkstationResponse(BaseModel):
    id: uuid.UUID
    device_id: str
    name: str
    group_id: str | None
    position: int | None
    status: WorkstationStatus
    last_seen_at: str | None
    client_version: str | None
    disabled_reason: str | None
    capabilities: tuple[str, ...]
    theme: str
    archived_at: str | None

    @classmethod
    def from_domain(cls, workstation: Workstation) -> "WorkstationResponse":
        return cls(
            id=workstation.id,
            device_id=workstation.device_id,
            name=workstation.name,
            group_id=workstation.group_id,
            position=workstation.position,
            status=workstation.status,
            last_seen_at=workstation.last_seen_at.isoformat() if workstation.last_seen_at else None,
            client_version=workstation.client_version,
            disabled_reason=workstation.disabled_reason,
            capabilities=workstation.capabilities,
            theme=workstation.theme,
            archived_at=workstation.archived_at.isoformat() if workstation.archived_at else None,
        )


def create_router(
    service: WorkstationService,
    command_service: WorkstationCommandService | None = None,
) -> APIRouter:
    router = APIRouter(prefix="/api/v1/workstations", tags=["workstations"])
    operator = Depends(require_permissions("workstations.manage"))

    @router.get("", response_model=list[WorkstationResponse], dependencies=[operator])
    async def list_workstations() -> list[WorkstationResponse]:
        return [WorkstationResponse.from_domain(item) for item in await service.list()]

    @router.post("", response_model=WorkstationResponse, status_code=status.HTTP_201_CREATED)
    async def register_workstation(
        body: RegisterWorkstationRequest,
        principal: Operator,
    ) -> WorkstationResponse:
        del principal
        workstation = await service.register(**body.model_dump())
        return WorkstationResponse.from_domain(workstation)

    @router.post("/heartbeat", response_model=WorkstationResponse)
    async def heartbeat(
        body: HeartbeatRequest,
        principal: Operator,
    ) -> WorkstationResponse:
        del principal
        workstation = await service.heartbeat(
            body.device_id,
            body.client_version,
            capabilities=body.capabilities,
        )
        return WorkstationResponse.from_domain(workstation)

    @router.post("/{workstation_id}/disable", response_model=WorkstationResponse)
    async def disable(
        workstation_id: uuid.UUID,
        body: DisableWorkstationRequest,
        principal: Operator,
    ) -> WorkstationResponse:
        del principal
        workstation = await service.disable(workstation_id, body.reason)
        return WorkstationResponse.from_domain(workstation)

    @router.put("/{workstation_id}", response_model=WorkstationResponse)
    async def update_workstation(
        workstation_id: uuid.UUID,
        body: UpdateWorkstationRequest,
        principal: Operator,
    ) -> WorkstationResponse:
        del principal
        return WorkstationResponse.from_domain(
            await service.update(workstation_id, **body.model_dump())
        )

    @router.post("/{workstation_id}/enable", response_model=WorkstationResponse)
    async def enable_workstation(
        workstation_id: uuid.UUID,
        principal: Operator,
    ) -> WorkstationResponse:
        del principal
        return WorkstationResponse.from_domain(await service.enable(workstation_id))

    @router.delete("/{workstation_id}", status_code=status.HTTP_204_NO_CONTENT)
    async def archive_workstation(workstation_id: uuid.UUID, principal: Operator) -> None:
        del principal
        await service.archive(workstation_id)

    if command_service is not None:

        @router.post(
            "/{workstation_id}/commands",
            response_model=WorkstationCommandResponse,
            status_code=status.HTTP_202_ACCEPTED,
        )
        async def dispatch_command(
            workstation_id: uuid.UUID,
            body: DispatchCommandRequest,
            principal: Operator,
            idempotency_key: str = Header(min_length=1, alias="Idempotency-Key"),
        ) -> WorkstationCommandResponse:
            command = await command_service.dispatch(
                workstation_id=workstation_id,
                command_type=body.command_type,
                payload_json=json.dumps(body.payload),
                idempotency_key=idempotency_key,
            )
            del principal
            return WorkstationCommandResponse.from_domain(command)

        @router.get(
            "/{workstation_id}/commands/{command_id}",
            response_model=WorkstationCommandResponse,
        )
        async def get_command(
            workstation_id: uuid.UUID,
            command_id: uuid.UUID,
            principal: Operator,
        ) -> WorkstationCommandResponse:
            del principal
            command = await command_service.get(workstation_id, command_id)
            return WorkstationCommandResponse.from_domain(command)

    return router
