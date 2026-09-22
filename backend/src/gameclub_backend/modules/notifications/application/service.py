from __future__ import annotations

import builtins
import datetime
import typing
import uuid

from gameclub_backend.application.errors import ApplicationError, ErrorCode
from gameclub_backend.modules.notifications.application.ports import (
    Clock,
    NotificationRuleRepository,
)
from gameclub_backend.modules.notifications.domain import (
    NotificationRule,
    NotificationSound,
    TimeNotificationEvent,
)


class UtcClock:
    def now(self) -> datetime.datetime:
        return datetime.datetime.now(datetime.UTC)


class NotificationRuleUpdate(typing.TypedDict, total=False):
    threshold_minutes: int
    enabled: bool
    play_sound: bool
    sound: NotificationSound
    custom_sound_path: str | None
    show_system_notification: bool
    message: str


class NotificationRuleService:
    def __init__(
        self,
        repository: NotificationRuleRepository,
        clock: Clock | None = None,
    ) -> None:
        self._repository = repository
        self._clock = clock or UtcClock()

    async def list(self) -> list[NotificationRule]:
        return await self._repository.list()

    async def create(
        self,
        *,
        threshold_minutes: int,
        enabled: bool,
        play_sound: bool,
        sound: NotificationSound,
        custom_sound_path: str | None,
        show_system_notification: bool,
        message: str,
    ) -> NotificationRule:
        now = self._clock.now()
        try:
            rule = NotificationRule(
                id=uuid.uuid4(),
                threshold_minutes=threshold_minutes,
                enabled=enabled,
                play_sound=play_sound,
                sound=sound,
                custom_sound_path=custom_sound_path,
                show_system_notification=show_system_notification,
                message=message,
                created_at=now,
                updated_at=now,
            )
        except (TypeError, ValueError) as error:
            raise ApplicationError(ErrorCode.INVALID_ARGUMENT, str(error)) from error
        return await self._repository.save(rule)

    async def update(
        self,
        rule_id: uuid.UUID,
        **values: typing.Unpack[NotificationRuleUpdate],
    ) -> NotificationRule:
        existing = await self._repository.get(rule_id)
        if existing is None:
            raise ApplicationError(ErrorCode.NOT_FOUND, "Notification rule not found")
        try:
            updated = NotificationRule(
                id=existing.id,
                threshold_minutes=values.get("threshold_minutes", existing.threshold_minutes),
                enabled=values.get("enabled", existing.enabled),
                play_sound=values.get("play_sound", existing.play_sound),
                sound=values.get("sound", existing.sound),
                custom_sound_path=values.get("custom_sound_path", existing.custom_sound_path),
                show_system_notification=values.get(
                    "show_system_notification", existing.show_system_notification
                ),
                message=values.get("message", existing.message),
                created_at=existing.created_at,
                updated_at=self._clock.now(),
            )
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
    ) -> builtins.list[TimeNotificationEvent]:
        moment = now or self._clock.now()
        events: builtins.list[TimeNotificationEvent] = []
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
