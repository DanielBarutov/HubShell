"""Выдача бонусного бюджета только на подтверждённой границе локальной цепочки."""

import dataclasses
import datetime
import typing
import uuid

from gameclub_backend.application.errors import ApplicationError, ErrorCode
from gameclub_backend.modules.auth.domain import Principal, SubjectType
from gameclub_backend.modules.clients.application.bonus import (
    BonusCommand,
    BonusEarningsPort,
    BonusGameQuote,
)
from gameclub_backend.modules.clients.bonus import BonusOperationKind


@dataclasses.dataclass(frozen=True)
class BonusBudgetRequest:
    client_id: uuid.UUID
    session_id: uuid.UUID
    device_id: str
    snapshot_id: uuid.UUID
    snapshot_version: int
    last_sequence: int
    last_payload_hash: str | None
    idempotency_key: str

    def __post_init__(self) -> None:
        for value in (self.client_id, self.session_id, self.snapshot_id):
            if not isinstance(value, uuid.UUID):
                raise ValueError("Bonus budget identifiers must be UUIDs")
        for value, minimum in ((self.snapshot_version, 1), (self.last_sequence, 0)):
            if (
                isinstance(value, bool)
                or not isinstance(value, int)
                or not minimum <= value <= 2_147_483_647
            ):
                raise ValueError("Invalid bonus budget checkpoint")
        if (
            not isinstance(self.device_id, str)
            or not self.device_id.strip()
            or len(self.device_id) > 128
        ):
            raise ValueError("Invalid device identity")
        if (
            not isinstance(self.idempotency_key, str)
            or not self.idempotency_key.strip()
            or len(self.idempotency_key) > 128
        ):
            raise ValueError("Invalid bonus budget idempotency key")
        object.__setattr__(self, "idempotency_key", self.idempotency_key.strip())
        value = self.last_payload_hash
        if self.last_sequence == 0:
            if value is not None:
                raise ValueError("An empty chain cannot have a hash")
        elif (
            not isinstance(value, str)
            or len(value) != 64
            or any(c not in "0123456789abcdef" for c in value)
        ):
            raise ValueError("Invalid bonus budget checkpoint hash")


@dataclasses.dataclass(frozen=True)
class BonusBudgetGrant:
    id: uuid.UUID
    request: BonusBudgetRequest
    version: int
    budget_cents: int
    payment_limit_bps: int
    issued_at: datetime.datetime


@dataclasses.dataclass(frozen=True)
class BonusBudgetContext:
    next_version: int
    existing: BonusBudgetGrant | None = None
    minute_price_cents: int = 0
    is_cancelled: bool = False


class BonusBudgetRepository(typing.Protocol):
    async def prepare_cancellation(
        self, request: BonusBudgetRequest, now: datetime.datetime
    ) -> BonusBudgetContext:
        """Validate the current confirmed checkpoint before cancelling this target key."""

    async def cancel(
        self, request: BonusBudgetRequest, context: BonusBudgetContext, now: datetime.datetime
    ) -> None:
        """Persist revocation even if the original enable has not arrived yet."""

    async def prepare(
        self, request: BonusBudgetRequest, now: datetime.datetime
    ) -> BonusBudgetContext:
        """Lock this session, validate lease/checkpoint, and find an immutable retry."""

    async def save(self, grant: BonusBudgetGrant) -> None:
        """Replace the current grant inside the application's transaction."""


class BonusBudgetService:
    def __init__(
        self,
        repository: BonusBudgetRepository,
        bonuses: BonusEarningsPort,
        transaction: typing.Callable[[], typing.AsyncContextManager[object]],
    ) -> None:
        self._repository = repository
        self._bonuses = bonuses
        self._transaction = transaction

    @staticmethod
    def _authorize(request: BonusBudgetRequest, principal: Principal) -> None:
        if (
            principal.subject_type is not SubjectType.CLIENT
            or principal.subject_id != str(request.client_id)
            or principal.device_id != request.device_id
            or principal.password_reset_required
            or not principal.can("client.portal")
        ):
            raise ApplicationError(ErrorCode.PERMISSION_DENIED, "Bonus budget is not authorized")

    async def quote(self, request: BonusBudgetRequest, principal: Principal) -> BonusGameQuote:
        self._authorize(request, principal)
        async with self._transaction():
            context = await self._repository.prepare(request, datetime.datetime.now(datetime.UTC))
            return await self._bonuses.quote_bonus_game(
                request.client_id,
                context.minute_price_cents,
                True,
                request.session_id,
                include_session_reserved=True,
            )

    async def cancel(self, request: BonusBudgetRequest, principal: Principal) -> None:
        self._authorize(request, principal)
        now = datetime.datetime.now(datetime.UTC)
        async with self._transaction():
            context = await self._repository.prepare_cancellation(request, now)
            if context.is_cancelled:
                return
            if context.existing is not None:
                cancel_id = uuid.uuid5(request.session_id, request.idempotency_key)
                await self._bonuses.apply_bonus_operation(
                    BonusCommand(
                        request.client_id,
                        BonusOperationKind.RELEASE,
                        0,
                        f"client:{request.client_id}",
                        "Отмена запроса бонусной оплаты",
                        f"v2-bonus-cancel:{cancel_id}",
                        request.session_id,
                    )
                )
            await self._repository.cancel(request, context, now)

    async def issue(self, request: BonusBudgetRequest, principal: Principal) -> BonusBudgetGrant:
        self._authorize(request, principal)
        now = datetime.datetime.now(datetime.UTC)
        async with self._transaction():
            context = await self._repository.prepare(request, now)
            if context.existing is not None:
                return context.existing
            current = await self._bonuses.get_bonus_policy()
            policy = await self._bonuses.get_bonus_policy(request.client_id, request.session_id)
            if not current.enabled or not policy.enabled or not policy.payment_limit_bps:
                raise ApplicationError(ErrorCode.CONFLICT, "Bonus payment is disabled")
            reserved = await self._bonuses.apply_bonus_operation(
                BonusCommand(
                    request.client_id,
                    BonusOperationKind.RESERVE,
                    0,
                    f"client:{request.client_id}",
                    "Резерв бонусов для поминутной игры",
                    f"v2-bonus:{uuid.uuid5(request.session_id, request.idempotency_key)}",
                    request.session_id,
                )
            )
            if reserved.session_reserved_after_cents <= 0:
                raise ApplicationError(ErrorCode.CONFLICT, "No bonuses available for the session")
            grant = BonusBudgetGrant(
                uuid.uuid4(),
                request,
                context.next_version,
                reserved.session_reserved_after_cents,
                policy.payment_limit_bps,
                now,
            )
            await self._repository.save(grant)
            return grant
