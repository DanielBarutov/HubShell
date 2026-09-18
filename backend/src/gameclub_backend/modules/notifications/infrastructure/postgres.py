from __future__ import annotations

import datetime
import uuid

from sqlalchemy import Boolean, DateTime, Integer, String, select
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from gameclub_backend.infrastructure.database import EngineProvider, open_session
from gameclub_backend.modules.notifications.domain import NotificationRule, NotificationSound


class NotificationBase(DeclarativeBase):
    pass


class NotificationRuleModel(NotificationBase):
    __tablename__ = "notification_rules"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    threshold_minutes: Mapped[int] = mapped_column(Integer())
    enabled: Mapped[bool] = mapped_column(Boolean(), default=True)
    play_sound: Mapped[bool] = mapped_column(Boolean(), default=True)
    sound: Mapped[str] = mapped_column(String(16))
    custom_sound_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    show_system_notification: Mapped[bool] = mapped_column(Boolean(), default=True)
    message: Mapped[str] = mapped_column(String(512))
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True))

    def to_domain(self) -> NotificationRule:
        return NotificationRule(
            id=self.id,
            threshold_minutes=self.threshold_minutes,
            enabled=self.enabled,
            play_sound=self.play_sound,
            sound=NotificationSound(self.sound),
            custom_sound_path=self.custom_sound_path,
            show_system_notification=self.show_system_notification,
            message=self.message,
            created_at=self.created_at,
            updated_at=self.updated_at,
        )

    @classmethod
    def from_domain(cls, item: NotificationRule) -> NotificationRuleModel:
        return cls(
            id=item.id,
            threshold_minutes=item.threshold_minutes,
            enabled=item.enabled,
            play_sound=item.play_sound,
            sound=item.sound.value,
            custom_sound_path=item.custom_sound_path,
            show_system_notification=item.show_system_notification,
            message=item.message,
            created_at=item.created_at,
            updated_at=item.updated_at,
        )


class PostgresNotificationRuleRepository:
    def __init__(self, engine_provider: EngineProvider) -> None:
        self._engine_provider = engine_provider

    async def list(self) -> list[NotificationRule]:
        async with open_session(self._engine_provider) as session:
            result = await session.scalars(
                select(NotificationRuleModel).order_by(NotificationRuleModel.threshold_minutes)
            )
            return [item.to_domain() for item in result]

    async def get(self, rule_id: uuid.UUID) -> NotificationRule | None:
        async with open_session(self._engine_provider) as session:
            item = await session.get(NotificationRuleModel, rule_id)
            return item.to_domain() if item else None

    async def save(self, item: NotificationRule) -> NotificationRule:
        async with open_session(self._engine_provider) as session:
            model = await session.get(NotificationRuleModel, item.id)
            if model is None:
                session.add(NotificationRuleModel.from_domain(item))
            else:
                for key, value in NotificationRuleModel.from_domain(item).__dict__.items():
                    if not key.startswith("_"):
                        setattr(model, key, value)
            await session.commit()
            return item

    async def delete(self, rule_id: uuid.UUID) -> None:
        async with open_session(self._engine_provider) as session:
            model = await session.get(NotificationRuleModel, rule_id)
            if model is not None:
                await session.delete(model)
                await session.commit()
