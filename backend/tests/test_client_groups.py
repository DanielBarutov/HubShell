import datetime

import pytest

from gameclub_backend.application.errors import ApplicationError
from gameclub_backend.modules.client_groups.application.service import ClientGroupService
from gameclub_backend.modules.client_groups.domain import ClientGroup
from gameclub_backend.modules.client_groups.infrastructure.memory import (
    InMemoryClientGroupRepository,
)
from gameclub_backend.modules.clients.application.service import ClientService
from gameclub_backend.modules.clients.infrastructure.memory import InMemoryClientRepository


class FixedClock:
    def now(self) -> datetime.datetime:
        return datetime.datetime(2026, 9, 17, 12, 0, tzinfo=datetime.UTC)


@pytest.mark.asyncio
async def test_new_portal_client_gets_current_default_group() -> None:
    """Проверяет транзакционное назначение default group только новым клиентам."""
    groups = InMemoryClientGroupRepository()
    clients = ClientService(InMemoryClientRepository(), clock=FixedClock(), groups=groups)

    created = await clients.register_portal("DefaultFox", "+7 999 111-22-33", "pass")
    assert created.client_group_id == "regular"

    vip = await ClientGroupService(groups, clock=FixedClock()).create(
        "vip", "VIP", allow_negative_balance=True, negative_balance_limit_cents=50000
    )
    await ClientGroupService(groups, clock=FixedClock()).update(
        vip.id,
        "VIP",
        allow_negative_balance=True,
        negative_balance_limit_cents=50000,
        is_default=True,
    )
    another = await clients.register_portal("VipFox", "+7 999 111-22-34", "pass")

    assert created.client_group_id == "regular"
    assert another.client_group_id == "vip"


@pytest.mark.asyncio
async def test_operator_can_assign_an_active_group_to_existing_client() -> None:
    """Проверяет, что назначение активной группы сохраняется у существующего клиента."""
    groups = InMemoryClientGroupRepository()
    group_service = ClientGroupService(groups, clock=FixedClock())
    await group_service.create(
        "vip",
        "VIP",
        allow_negative_balance=True,
        negative_balance_limit_cents=5000,
    )
    clients = ClientService(InMemoryClientRepository(), clock=FixedClock(), groups=groups)
    client = await clients.create("GroupFox")

    updated = await clients.update(client.id, "GroupFox", client_group_id="vip")

    assert updated.client_group_id == "vip"


@pytest.mark.asyncio
async def test_group_policy_allows_bounded_debt_and_blocks_next_debit() -> None:
    """Проверяет, что debit проходит до лимита долга и атомарно блокируется ниже него."""
    groups = InMemoryClientGroupRepository()
    group_service = ClientGroupService(groups, clock=FixedClock())
    await group_service.update(
        "regular",
        "Обычные клиенты",
        allow_negative_balance=True,
        negative_balance_limit_cents=500,
        is_default=True,
    )
    clients = ClientService(InMemoryClientRepository(), clock=FixedClock(), groups=groups)
    client = await clients.create("DebtFox")
    await clients.top_up(client.id, 100, 0, "seed", "operator", "seed")

    updated, _ = await clients.debit(
        client.id,
        600,
        "meter",
        "system",
        "meter-1",
        allow_negative_balance=True,
    )
    assert updated.balance_cents == -500

    with pytest.raises(ApplicationError, match="Insufficient balance"):
        await clients.debit(client.id, 1, "meter", "system", "meter-2")


@pytest.mark.asyncio
async def test_inactive_or_default_group_cannot_be_deleted() -> None:
    """Проверяет безопасное удаление: default group не удаляется, inactive остаётся явным."""
    groups = InMemoryClientGroupRepository()
    service = ClientGroupService(groups, clock=FixedClock())
    with pytest.raises(ApplicationError, match="Default client group"):
        await service.delete("regular")
    archived = await service.create("old", "Старая", active=False)
    with pytest.raises(ApplicationError, match="default"):
        await service.update(archived.id, "Старая", active=False, is_default=True)


def test_client_group_requires_limit_permission() -> None:
    """Проверяет, что лимит долга нельзя задать без разрешения на минус."""
    with pytest.raises(ValueError, match="requires negative balance permission"):
        ClientGroup("bad", "Bad", negative_balance_limit_cents=1)
