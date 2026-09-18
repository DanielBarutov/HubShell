import datetime
import uuid

import pytest

from gameclub_backend.application.errors import ApplicationError
from gameclub_backend.modules.notifications.application.service import NotificationRuleService
from gameclub_backend.modules.notifications.domain import NotificationRule, NotificationSound
from gameclub_backend.modules.notifications.infrastructure.memory import (
    InMemoryNotificationRuleRepository,
)


class FixedClock:
    def now(self) -> datetime.datetime:
        return datetime.datetime(2026, 9, 17, 12, 0, tzinfo=datetime.UTC)


@pytest.mark.asyncio
async def test_notification_event_has_stable_deduplication_id() -> None:
    """Проверяет, что heartbeat не создаёт новый идентификатор одного порога."""
    service = NotificationRuleService(InMemoryNotificationRuleRepository(), clock=FixedClock())
    rule = await service.create(
        threshold_minutes=5,
        enabled=True,
        play_sound=True,
        sound=NotificationSound.STANDARD,
        custom_sound_path=None,
        show_system_notification=True,
        message="Осталось 5 минут",
    )
    session_id = uuid.uuid4()
    first = await service.due_events(session_id, 4, "package")
    second = await service.due_events(session_id, 4, "package")
    assert first[0].id == second[0].id == rule.event_id(session_id, "package", 5)


@pytest.mark.asyncio
async def test_disabled_and_future_threshold_rules_are_not_due() -> None:
    """Проверяет, что выключенное правило и ещё не достигнутый порог не отправляются."""
    repository = InMemoryNotificationRuleRepository()
    service = NotificationRuleService(repository, clock=FixedClock())
    await service.create(
        threshold_minutes=5,
        enabled=False,
        play_sound=True,
        sound=NotificationSound.STANDARD,
        custom_sound_path=None,
        show_system_notification=True,
        message="disabled",
    )
    await service.create(
        threshold_minutes=30,
        enabled=True,
        play_sound=False,
        sound=NotificationSound.STANDARD,
        custom_sound_path=None,
        show_system_notification=False,
        message="future",
    )
    assert await service.due_events(uuid.uuid4(), 31, "balance") == []


def test_custom_notification_sound_requires_supported_extension() -> None:
    """Проверяет, что пользовательский звук ограничен форматами mp3 и wav."""
    now = datetime.datetime(2026, 9, 17, 12, 0, tzinfo=datetime.UTC)
    with pytest.raises(ValueError, match="mp3 or wav"):
        NotificationRule(
            id=uuid.uuid4(),
            threshold_minutes=5,
            enabled=True,
            play_sound=True,
            sound=NotificationSound.CUSTOM,
            custom_sound_path="/tmp/voice.ogg",
            show_system_notification=False,
            message="Осталось мало времени",
            created_at=now,
            updated_at=now,
        )


@pytest.mark.asyncio
async def test_update_missing_rule_returns_not_found() -> None:
    """Проверяет, что изменение удалённого правила не считается успешным."""
    service = NotificationRuleService(InMemoryNotificationRuleRepository(), clock=FixedClock())
    with pytest.raises(ApplicationError, match="Notification rule not found"):
        await service.update(uuid.uuid4(), threshold_minutes=1)
