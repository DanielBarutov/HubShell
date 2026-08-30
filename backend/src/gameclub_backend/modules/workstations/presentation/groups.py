import typing

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from gameclub_backend.modules.auth.domain import Principal
from gameclub_backend.modules.workstations.application.groups import WorkstationGroupService
from gameclub_backend.modules.workstations.domain import (
    LockdownDeploymentMode,
    LockdownPolicy,
    WorkstationGroup,
)
from gameclub_backend.presentation.http.auth import require_permissions

Operator = typing.Annotated[Principal, Depends(require_permissions("workstations.manage"))]


class WorkstationGroupRequest(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    theme: str = Field(default="standard", min_length=1, max_length=32)
    lockdown_policy: "LockdownPolicyRequest | None" = None


class ManagerPasswordRequest(BaseModel):
    password: str = Field(min_length=8, max_length=128)


class LockdownPolicyRequest(BaseModel):
    deployment_mode: str = Field(default="app_gate", max_length=32)
    shell_enabled: bool = True
    user_self_login_enabled: bool = True
    lock_after_session: bool = True
    restart_after_session: bool = True
    hidden_drives: list[str] = Field(default_factory=list, max_length=26)
    block_external_storage: bool = False
    disable_start_menu: bool = False
    disable_desktop_switching: bool = False
    blocked_window_rules: list[str] = Field(default_factory=list, max_length=128)
    allowed_application_ids: list[str] = Field(default_factory=list, max_length=128)
    version: int = Field(default=1, ge=1, le=1_000_000)

    def to_domain(self) -> LockdownPolicy:
        return LockdownPolicy(
            deployment_mode=LockdownDeploymentMode(self.deployment_mode.strip().lower()),
            shell_enabled=self.shell_enabled,
            user_self_login_enabled=self.user_self_login_enabled,
            lock_after_session=self.lock_after_session,
            restart_after_session=self.restart_after_session,
            hidden_drives=tuple(self.hidden_drives),
            block_external_storage=self.block_external_storage,
            disable_start_menu=self.disable_start_menu,
            disable_desktop_switching=self.disable_desktop_switching,
            blocked_window_rules=tuple(self.blocked_window_rules),
            allowed_application_ids=tuple(self.allowed_application_ids),
            version=self.version,
        )


class LockdownPolicyResponse(BaseModel):
    deployment_mode: str
    shell_enabled: bool
    user_self_login_enabled: bool
    lock_after_session: bool
    restart_after_session: bool
    hidden_drives: tuple[str, ...]
    block_external_storage: bool
    disable_start_menu: bool
    disable_desktop_switching: bool
    blocked_window_rules: tuple[str, ...]
    allowed_application_ids: tuple[str, ...]
    version: int

    @classmethod
    def from_domain(cls, policy: LockdownPolicy) -> "LockdownPolicyResponse":
        return cls(
            deployment_mode=policy.deployment_mode.value,
            shell_enabled=policy.shell_enabled,
            user_self_login_enabled=policy.user_self_login_enabled,
            lock_after_session=policy.lock_after_session,
            restart_after_session=policy.restart_after_session,
            hidden_drives=policy.hidden_drives,
            block_external_storage=policy.block_external_storage,
            disable_start_menu=policy.disable_start_menu,
            disable_desktop_switching=policy.disable_desktop_switching,
            blocked_window_rules=policy.blocked_window_rules,
            allowed_application_ids=policy.allowed_application_ids,
            version=policy.version,
        )


class WorkstationGroupResponse(BaseModel):
    id: str
    name: str
    theme: str
    updated_at: str | None
    lockdown_policy: LockdownPolicyResponse

    @classmethod
    def from_domain(cls, group: WorkstationGroup) -> "WorkstationGroupResponse":
        return cls(
            id=group.id,
            name=group.name,
            theme=group.theme,
            updated_at=group.updated_at.isoformat() if group.updated_at else None,
            lockdown_policy=LockdownPolicyResponse.from_domain(group.lockdown_policy),
        )


def create_router(service: WorkstationGroupService) -> APIRouter:
    router = APIRouter(prefix="/api/v1/workstation-groups", tags=["workstation-groups"])

    @router.get("", response_model=list[WorkstationGroupResponse])
    async def list_groups(principal: Operator) -> list[WorkstationGroupResponse]:
        del principal
        return [WorkstationGroupResponse.from_domain(item) for item in await service.list()]

    @router.put("/{group_id}", response_model=WorkstationGroupResponse)
    async def save_group(
        group_id: str,
        body: WorkstationGroupRequest,
        principal: Operator,
    ) -> WorkstationGroupResponse:
        del principal
        try:
            policy = body.lockdown_policy.to_domain() if body.lockdown_policy else None
        except ValueError as error:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=str(error),
            ) from error
        group = await service.save(group_id, body.name, body.theme, policy)
        return WorkstationGroupResponse.from_domain(group)

    @router.post("", response_model=WorkstationGroupResponse, status_code=status.HTTP_201_CREATED)
    async def create_group(
        body: WorkstationGroupRequest,
        principal: Operator,
    ) -> WorkstationGroupResponse:
        del principal
        group_id = body.name.strip().lower().replace(" ", "-")
        try:
            policy = body.lockdown_policy.to_domain() if body.lockdown_policy else None
        except ValueError as error:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=str(error),
            ) from error
        return WorkstationGroupResponse.from_domain(
            await service.save(group_id, body.name, body.theme, policy)
        )

    @router.delete("/{group_id}", status_code=status.HTTP_204_NO_CONTENT)
    async def delete_group(group_id: str, principal: Operator) -> None:
        del principal
        await service.delete(group_id)

    @router.put("/{group_id}/lockdown-policy", response_model=WorkstationGroupResponse)
    async def set_lockdown_policy(
        group_id: str,
        body: LockdownPolicyRequest,
        principal: Operator,
    ) -> WorkstationGroupResponse:
        del principal
        try:
            policy = body.to_domain()
        except ValueError as error:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=str(error),
            ) from error
        return WorkstationGroupResponse.from_domain(
            await service.set_lockdown_policy(group_id, policy)
        )

    @router.put("/{group_id}/manager-password", status_code=status.HTTP_204_NO_CONTENT)
    async def set_manager_password(
        group_id: str,
        body: ManagerPasswordRequest,
        principal: Operator,
    ) -> None:
        del principal
        await service.set_manager_password(group_id, body.password)

    return router
