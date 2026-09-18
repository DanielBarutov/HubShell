import uuid

from gameclub_backend.modules.notifications.domain import NotificationRule


class InMemoryNotificationRuleRepository:
    def __init__(self) -> None:
        self._items: dict[uuid.UUID, NotificationRule] = {}

    async def list(self) -> list[NotificationRule]:
        return sorted(self._items.values(), key=lambda item: item.threshold_minutes)

    async def get(self, rule_id: uuid.UUID) -> NotificationRule | None:
        return self._items.get(rule_id)

    async def save(self, rule: NotificationRule) -> NotificationRule:
        self._items[rule.id] = rule
        return rule

    async def delete(self, rule_id: uuid.UUID) -> None:
        self._items.pop(rule_id, None)
