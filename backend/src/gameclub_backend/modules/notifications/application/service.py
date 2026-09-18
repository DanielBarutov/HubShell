from __future__ import annotations

import dataclasses
import datetime
import uuid

from gameclub_backend.application.errors import ApplicationError, ErrorCode
from gameclub_backend.modules.notifications.application.ports import NotificationRuleRepository
from gameclub_backend.modules.notifications.domain import (
    NotificationRule,
    TimeNotificationEvent,
)


class UtcClock:
    def now(self) -> datetime.datetime:
        return datetime.datetime.now(datetime.UTC)


class NotificationRuleService:
    def __init__(
        self,
        repository: NotificationRuleRepository,
        clock: UtcClock | None = None,
    ) -> None:
        self._repository = repository
        self._clock = clock or UtcClock()

    async def list(self) -> list[NotificationRule]:
        return await self._repository.list()

    async def create(self, **values: object) -> NotificationRule:
        now = self._clock.now()
        try:
            rule = NotificationRule(id=uuid.uuid4(), created_at=now, updated_at=now, **values)
        except (TypeError, ValueError) as error:
            raise ApplicationError(ErrorCode.INVALID_ARGUMENT, str(error)) from error
        return await self._repository.save(rule)

    async def update(self, rule_id: uuid.UUID, **values: object) -> NotificationRule:
        existing = await self._repository.get(rule_id)
        if existing is None:
            raise ApplicationError(ErrorCode.NOT_FOUND, "Notification rule not found")
        try:
            updated = dataclasses.replace(existing, **values, updated_at=self._clock.now())
        except (TypeError, ValueError) as error:
            raise ApplicationError(ErrorCode.INVALID_ARGUMENT, str(error)) from error
        return await self._repository.save(updated)

    async def delete(self, rule_id: uuid.UUID) -> None:
        if await self._repository.get(rule_id) is None:
            raise ApplicationError(ErrorCode.NOT_FOUND, "Notification rule not found")
        await self._repository.delete(rule_id)

    async def due_events(
        self,
        session_id: uuid.UUID,
        remaining_minutes: int,
        source: str,
        now: datetime.datetime | None = None,
    ) -> list[TimeNotificationEvent]:
        moment = now or self._clock.now()
        events: list[TimeNotificationEvent] = []
        for rule in await self._repository.list():
            if not rule.enabled or remaining_minutes > rule.threshold_minutes:
                continue
            events.append(
                TimeNotificationEvent(
                    id=rule.event_id(session_id, source, rule.threshold_minutes),
                    rule_id=rule.id,
                    session_id=session_id,
                    threshold_minutes=rule.threshold_minutes,
                    message=rule.message,
                    play_sound=rule.play_sound,
                    sound=rule.sound,
                    custom_sound_path=rule.custom_sound_path,
                    show_system_notification=rule.show_system_notification,
                    created_at=moment,
                )
            )
        return events
