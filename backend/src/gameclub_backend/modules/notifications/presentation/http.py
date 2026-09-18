import datetime
import typing
import uuid

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field

from gameclub_backend.modules.auth.domain import Principal
from gameclub_backend.modules.notifications.application.service import NotificationRuleService
from gameclub_backend.modules.notifications.domain import NotificationRule, NotificationSound
from gameclub_backend.presentation.http.auth import require_permissions

Operator = typing.Annotated[Principal, Depends(require_permissions("settings.manage"))]


class NotificationRuleRequest(BaseModel):
    threshold_minutes: int = Field(gt=0, le=24 * 60)
    enabled: bool = True
    play_sound: bool = True
    sound: NotificationSound = NotificationSound.STANDARD
    custom_sound_path: str | None = Field(default=None, max_length=512)
    show_system_notification: bool = True
    message: str = Field(min_length=1, max_length=512)


class NotificationRuleResponse(BaseModel):
    id: uuid.UUID
    threshold_minutes: int
    enabled: bool
    play_sound: bool
    sound: NotificationSound
    custom_sound_path: str | None
    show_system_notification: bool
    message: str
    created_at: datetime.datetime
    updated_at: datetime.datetime

    @classmethod
    def from_domain(cls, item: NotificationRule) -> "NotificationRuleResponse":
        return cls.model_validate(item, from_attributes=True)


def create_router(service: NotificationRuleService) -> APIRouter:
    router = APIRouter(prefix="/api/v1/notification-rules", tags=["notifications"])

    @router.get("", response_model=list[NotificationRuleResponse])
    async def list_rules(principal: Operator) -> list[NotificationRuleResponse]:
        del principal
        return [NotificationRuleResponse.from_domain(item) for item in await service.list()]

    @router.post("", response_model=NotificationRuleResponse, status_code=status.HTTP_201_CREATED)
    async def create_rule(
        body: NotificationRuleRequest,
        principal: Operator,
    ) -> NotificationRuleResponse:
        del principal
        return NotificationRuleResponse.from_domain(await service.create(**body.model_dump()))

    @router.put("/{rule_id}", response_model=NotificationRuleResponse)
    async def update_rule(
        rule_id: uuid.UUID,
        body: NotificationRuleRequest,
        principal: Operator,
    ) -> NotificationRuleResponse:
        del principal
        return NotificationRuleResponse.from_domain(
            await service.update(rule_id, **body.model_dump())
        )

    @router.delete("/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
    async def delete_rule(rule_id: uuid.UUID, principal: Operator) -> None:
        del principal
        await service.delete(rule_id)

    return router
