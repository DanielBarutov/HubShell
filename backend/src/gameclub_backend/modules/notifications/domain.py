from __future__ import annotations

import dataclasses
import datetime
import enum
import hashlib
import uuid


class NotificationSound(enum.StrEnum):
    STANDARD = "standard"
    CUSTOM = "custom"


@dataclasses.dataclass(frozen=True)
class NotificationRule:
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

    def __post_init__(self) -> None:
        if self.threshold_minutes <= 0:
            raise ValueError("Notification threshold must be positive")
        try:
            sound = NotificationSound(self.sound)
        except ValueError as error:
            raise ValueError("Invalid notification sound") from error
        if sound is NotificationSound.CUSTOM:
            if not self.custom_sound_path or not self.custom_sound_path.lower().endswith(
                (".mp3", ".wav")
            ):
                raise ValueError("Custom notification sound must be mp3 or wav")
            if len(self.custom_sound_path) > 512:
                raise ValueError("Custom notification sound path is too long")
        if not self.message.strip() or len(self.message) > 512:
            raise ValueError("Notification message must contain from 1 to 512 characters")
        if self.created_at.tzinfo is None or self.updated_at.tzinfo is None:
            raise ValueError("Notification timestamps must include timezone")
        object.__setattr__(self, "sound", sound)
        object.__setattr__(self, "message", self.message.strip())

    def event_id(self, session_id: uuid.UUID, source: str, remaining_minutes: int) -> str:
        raw = f"{self.id}:{session_id}:{source}:{remaining_minutes}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()


@dataclasses.dataclass(frozen=True)
class TimeNotificationEvent:
    id: str
    rule_id: uuid.UUID
    session_id: uuid.UUID
    threshold_minutes: int
    message: str
    play_sound: bool
    sound: NotificationSound
    custom_sound_path: str | None
    show_system_notification: bool
    created_at: datetime.datetime
