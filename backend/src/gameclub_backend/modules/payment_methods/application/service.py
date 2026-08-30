from __future__ import annotations

import dataclasses
import datetime
import re
import uuid

from gameclub_backend.application.errors import ApplicationError, ErrorCode
from gameclub_backend.modules.payment_methods.application.ports import PaymentMethodRepository
from gameclub_backend.modules.payment_methods.domain import PaymentMethod


class UtcClock:
    def now(self) -> datetime.datetime:
        return datetime.datetime.now(datetime.UTC)


class PaymentMethodService:
    def __init__(
        self,
        repository: PaymentMethodRepository,
        clock: UtcClock | None = None,
    ) -> None:
        self._repository = repository
        self._clock = clock or UtcClock()

    async def list(self) -> list[PaymentMethod]:
        return await self._repository.list()

    async def create(
        self,
        key: str,
        name: str,
        active: bool = True,
        sort_order: int = 0,
    ) -> PaymentMethod:
        normalized_key, normalized_name = self._validate_values(key, name, sort_order)
        if await self._repository.get_by_key(normalized_key) is not None:
            raise ApplicationError(ErrorCode.CONFLICT, "Payment method key already exists")
        now = self._clock.now()
        return await self._repository.save(
            PaymentMethod(
                id=uuid.uuid4(),
                key=normalized_key,
                name=normalized_name,
                active=active,
                sort_order=sort_order,
                created_at=now,
                updated_at=now,
            )
        )

    async def update(
        self,
        method_id: uuid.UUID,
        key: str,
        name: str,
        active: bool = True,
        sort_order: int = 0,
    ) -> PaymentMethod:
        normalized_key, normalized_name = self._validate_values(key, name, sort_order)
        existing = await self._repository.get(method_id)
        if existing is None:
            raise ApplicationError(ErrorCode.NOT_FOUND, "Payment method not found")
        duplicate = await self._repository.get_by_key(normalized_key)
        if duplicate is not None and duplicate.id != method_id:
            raise ApplicationError(ErrorCode.CONFLICT, "Payment method key already exists")
        return await self._repository.save(
            dataclasses.replace(
                existing,
                key=normalized_key,
                name=normalized_name,
                active=active,
                sort_order=sort_order,
                updated_at=self._clock.now(),
            )
        )

    async def delete(self, method_id: uuid.UUID) -> None:
        if await self._repository.get(method_id) is None:
            raise ApplicationError(ErrorCode.NOT_FOUND, "Payment method not found")
        await self._repository.delete(method_id)

    @staticmethod
    def _validate_values(key: str, name: str, sort_order: int) -> tuple[str, str]:
        normalized_key = key.strip().lower()
        normalized_name = name.strip()
        if not re.fullmatch(r"^[a-z0-9][a-z0-9_-]{0,63}$", normalized_key):
            raise ApplicationError(
                ErrorCode.INVALID_ARGUMENT,
                "Payment method key must use lowercase latin letters, numbers, _ or -",
            )
        if not normalized_name or len(normalized_name) > 128:
            raise ApplicationError(
                ErrorCode.INVALID_ARGUMENT,
                "Payment method name must contain from 1 to 128 characters",
            )
        if isinstance(sort_order, bool) or not isinstance(sort_order, int) or sort_order < 0:
            raise ApplicationError(
                ErrorCode.INVALID_ARGUMENT,
                "Payment method sort order is invalid",
            )
        return normalized_key, normalized_name
