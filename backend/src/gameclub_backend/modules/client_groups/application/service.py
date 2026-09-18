from __future__ import annotations

import dataclasses
import datetime

from gameclub_backend.application.audit import AuditEvent, AuditRepository
from gameclub_backend.application.errors import ApplicationError, ErrorCode
from gameclub_backend.modules.client_groups.application.ports import ClientGroupRepository
from gameclub_backend.modules.client_groups.domain import ClientGroup


class UtcClock:
    def now(self) -> datetime.datetime:
        return datetime.datetime.now(datetime.UTC)


class ClientGroupService:
    def __init__(
        self,
        repository: ClientGroupRepository,
        clock: UtcClock | None = None,
        audit: AuditRepository | None = None,
    ) -> None:
        self._repository = repository
        self._clock = clock or UtcClock()
        self._audit = audit

    async def list(self) -> list[ClientGroup]:
        return await self._repository.list()

    async def create(
        self,
        id: str,
        name: str,
        allow_negative_balance: bool = False,
        negative_balance_limit_cents: int = 0,
        active: bool = True,
        is_default: bool = False,
        actor_id: str = "system",
    ) -> ClientGroup:
        normalized_id = id.strip().lower()
        if await self._repository.get(normalized_id) is not None:
            raise ApplicationError(ErrorCode.CONFLICT, "Client group already exists")
        if is_default and not active:
            raise ApplicationError(ErrorCode.INVALID_ARGUMENT, "Inactive group cannot be default")
        try:
            group = ClientGroup(
                id=normalized_id,
                name=name,
                allow_negative_balance=allow_negative_balance,
                negative_balance_limit_cents=negative_balance_limit_cents,
                active=active,
                is_default=is_default,
                updated_at=self._clock.now(),
            )
        except ValueError as error:
            raise ApplicationError(ErrorCode.INVALID_ARGUMENT, str(error)) from error
        result = await self._repository.save(group)
        await self._audit_change("client_group.created", result, actor_id)
        return result

    async def update(
        self,
        group_id: str,
        name: str,
        allow_negative_balance: bool = False,
        negative_balance_limit_cents: int = 0,
        active: bool = True,
        is_default: bool | None = None,
        actor_id: str = "system",
    ) -> ClientGroup:
        existing = await self._repository.get(group_id)
        if existing is None:
            raise ApplicationError(ErrorCode.NOT_FOUND, "Client group not found")
        selected_default = existing.is_default if is_default is None else is_default
        if selected_default and not active:
            raise ApplicationError(ErrorCode.INVALID_ARGUMENT, "Inactive group cannot be default")
        try:
            result = dataclasses.replace(
                existing,
                name=name,
                allow_negative_balance=allow_negative_balance,
                negative_balance_limit_cents=negative_balance_limit_cents,
                active=active,
                is_default=selected_default,
                updated_at=self._clock.now(),
            )
        except ValueError as error:
            raise ApplicationError(ErrorCode.INVALID_ARGUMENT, str(error)) from error
        result = await self._repository.save(result)
        await self._audit_change("client_group.updated", result, actor_id)
        return result

    async def delete(self, group_id: str, actor_id: str = "system") -> None:
        group = await self._repository.get(group_id)
        if group is None:
            raise ApplicationError(ErrorCode.NOT_FOUND, "Client group not found")
        if group.is_default:
            raise ApplicationError(ErrorCode.CONFLICT, "Default client group cannot be deleted")
        if await self._repository.count_clients(group.id):
            raise ApplicationError(ErrorCode.CONFLICT, "Client group is assigned to clients")
        await self._repository.delete(group.id)
        await self._audit_change("client_group.deleted", group, actor_id)

    async def _audit_change(self, action: str, group: ClientGroup, actor_id: str) -> None:
        if self._audit is None:
            return
        await self._audit.record(
            AuditEvent(
                id=__import__("uuid").uuid4(),
                actor_id=actor_id.strip() or None,
                action=action,
                resource_path=f"/api/v1/client-groups/{group.id}",
                outcome="success",
                status_code=200,
                request_id=None,
                created_at=self._clock.now(),
            )
        )
