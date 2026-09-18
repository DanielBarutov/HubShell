from __future__ import annotations

import datetime
import uuid

from gameclub_backend.modules.notifications.application.service import NotificationRuleService
from gameclub_backend.modules.sessions.domain import SessionTimeNotification


class SessionTimeNotificationLookup:
    """Adapts notification rules to the session snapshot boundary."""

    def __init__(self, service: NotificationRuleService) -> None:
        self._service = service

    async def due_events(
        self,
        session_id: uuid.UUID,
        remaining_minutes: int,
        source: str,
        now: datetime.datetime,
    ) -> list[SessionTimeNotification]:
        events = await self._service.due_events(
            session_id,
            remaining_minutes,
            source,
            now,
        )
        return [
            SessionTimeNotification(
                id=event.id,
                threshold_minutes=event.threshold_minutes,
                message=event.message,
                play_sound=event.play_sound,
                sound=event.sound.value,
                custom_sound_path=event.custom_sound_path,
                show_system_notification=event.show_system_notification,
            )
            for event in events
        ]
