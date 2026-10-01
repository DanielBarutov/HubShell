"""Серверное пополнение V2: деньги и сообщение клиенту фиксируются вместе."""

from __future__ import annotations

import dataclasses
import datetime
import hashlib
import json
import typing
import uuid

from gameclub_backend.modules.payment_methods.domain import PaymentPart


@dataclasses.dataclass(frozen=True)
class V2DepositCreditCommand:
    """Неизменяемый запрос оператора на пополнение автономного клиента.

    ``payment_operation_id`` приходит от серверной payment-boundary. Он не
    создаётся Windows-клиентом и одновременно служит ключом идемпотентности.
    """

    payment_operation_id: uuid.UUID
    client_id: uuid.UUID
    session_id: uuid.UUID
    device_id: str
    amount_delta_cents: int
    currency: str
    reason: str
    actor_id: str
    payment_parts: tuple[PaymentPart, ...]
    cash_shift_id: uuid.UUID | None = None

    def __post_init__(self) -> None:
        if (
            isinstance(self.amount_delta_cents, bool)
            or not isinstance(self.amount_delta_cents, int)
            or self.amount_delta_cents <= 0
        ):
            raise ValueError("Deposit amount must be a positive integer")
        currency = self.currency.strip().upper()
        if len(currency) != 3 or not currency.isalpha():
            raise ValueError("Deposit currency must be a three-letter code")
        reason = self.reason.strip()
        actor_id = self.actor_id.strip()
        device_id = self.device_id.strip()
        if not reason or not actor_id or not device_id:
            raise ValueError("Deposit reason, actor and device are required")
        parts = tuple(self.payment_parts)
        if not parts:
            raise ValueError("Deposit payment parts are required")
        if sum(part.amount_cents for part in parts) != self.amount_delta_cents:
            raise ValueError("Deposit payment parts total must match the amount")
        if any(part.method not in {"cash", "transfer"} for part in parts):
            raise ValueError("Deposit payment supports cash or transfer")
        if any(part.method == "cash" for part in parts) and self.cash_shift_id is None:
            raise ValueError("Cash deposit requires a cash shift")
        object.__setattr__(self, "currency", currency)
        object.__setattr__(self, "reason", reason)
        object.__setattr__(self, "actor_id", actor_id)
        object.__setattr__(self, "device_id", device_id)
        object.__setattr__(self, "payment_parts", parts)

    @property
    def request_hash(self) -> str:
        """Hash the full semantic request; raw payment references stay out of events."""

        payload = {
            "payment_operation_id": str(self.payment_operation_id),
            "client_id": str(self.client_id),
            "session_id": str(self.session_id),
            "device_id": self.device_id,
            "amount_delta_cents": self.amount_delta_cents,
            "currency": self.currency,
            "reason": self.reason,
            "actor_id": self.actor_id,
            "payment_parts": [part.as_dict() for part in self.payment_parts],
            "cash_shift_id": str(self.cash_shift_id) if self.cash_shift_id else None,
        }
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@dataclasses.dataclass(frozen=True)
class V2DepositCreditResult:
    """Результат без абсолютного баланса для доставки на offline ПК."""

    payment_operation_id: uuid.UUID
    balance_operation_id: uuid.UUID
    client_delivery_event_id: uuid.UUID
    confirmed_domain_event_id: uuid.UUID
    amount_delta_cents: int
    currency: str
    accepted_at: datetime.datetime
    is_duplicate: bool = False


class V2DepositCreditRepository(typing.Protocol):
    async def apply(
        self,
        command: V2DepositCreditCommand,
        accepted_at: datetime.datetime,
    ) -> V2DepositCreditResult:
        """Atomically write ledger, audit, cash movement and both outbox facts."""


class Clock(typing.Protocol):
    def now(self) -> datetime.datetime:
        """Return an aware UTC timestamp."""


class UtcClock:
    def now(self) -> datetime.datetime:
        return datetime.datetime.now(datetime.UTC)


class V2DepositCreditService:
    """Application boundary for an operator-confirmed server deposit."""

    def __init__(
        self,
        repository: V2DepositCreditRepository,
        clock: Clock | None = None,
    ) -> None:
        self._repository = repository
        self._clock = clock or UtcClock()

    async def apply(self, command: V2DepositCreditCommand) -> V2DepositCreditResult:
        return await self._repository.apply(command, self._clock.now())
