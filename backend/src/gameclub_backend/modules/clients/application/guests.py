from __future__ import annotations

import datetime
import uuid

from gameclub_backend.application.errors import ApplicationError, ErrorCode
from gameclub_backend.modules.clients.application.ports import Clock, GuestRepository
from gameclub_backend.modules.clients.domain import Guest, Nickname, PhoneNumber, normalize_phone


class UtcClock:
    def now(self) -> datetime.datetime:
        return datetime.datetime.now(datetime.UTC)


class GuestService:
    def __init__(self, repository: GuestRepository, clock: Clock | None = None) -> None:
        self._repository = repository
        self._clock = clock or UtcClock()

    async def create(
        self,
        nickname: str,
        phone: str | None = None,
        discount_category: str | None = None,
    ) -> Guest:
        try:
            normalized_nickname = Nickname(nickname).value
            normalized_phone = PhoneNumber(phone).value if phone else None
            now = self._clock.now()
            guest = Guest(
                id=uuid.uuid4(),
                nickname=normalized_nickname,
                phone=normalized_phone,
                discount_category=discount_category,
                created_at=now,
                updated_at=now,
            )
        except ValueError as error:
            raise ApplicationError(ErrorCode.INVALID_ARGUMENT, str(error)) from error
        return await self._repository.save(guest)

    async def search(self, query: str, field: str) -> list[Guest]:
        normalized_query = query.strip().lower()
        if field not in {"nickname", "phone"}:
            raise ApplicationError(
                ErrorCode.INVALID_ARGUMENT,
                "Search field must be nickname or phone",
            )
        if field == "nickname" and len(normalized_query) < 3:
            raise ApplicationError(
                ErrorCode.INVALID_ARGUMENT,
                "Nickname search starts at 3 characters",
            )
        if field == "phone":
            normalized_query = normalize_phone(normalized_query)
            if len(normalized_query) < 4:
                raise ApplicationError(
                    ErrorCode.INVALID_ARGUMENT,
                    "Phone search starts at 4 digits",
                )
        return await self._repository.search(normalized_query, field)

    async def list_guests(self) -> list[Guest]:
        return await self._repository.list_guests()

    async def get(self, guest_id: uuid.UUID) -> Guest:
        guest = await self._repository.get(guest_id)
        if guest is None:
            raise ApplicationError(ErrorCode.NOT_FOUND, "Guest not found")
        return guest
