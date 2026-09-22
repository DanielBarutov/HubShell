import datetime
import typing
import uuid

from gameclub_backend.modules.notifications.domain import NotificationRule


class NotificationRuleRepository(typing.Protocol):
    async def list(self) -> list[NotificationRule]:
        """Return rules ordered by threshold."""

    async def get(self, rule_id: uuid.UUID) -> NotificationRule | None:
        """Return one rule."""

    async def save(self, rule: NotificationRule) -> NotificationRule:
        """Persist a rule."""

    async def delete(self, rule_id: uuid.UUID) -> None:
        """Delete a rule."""


class Clock(typing.Protocol):
    def now(self) -> datetime.datetime:
        """Return an aware UTC datetime."""
        ...
