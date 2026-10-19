from __future__ import annotations

import asyncio
import contextlib
import dataclasses
import datetime
import uuid
from collections.abc import Callable, Mapping, Sequence

from gameclub_backend.application.errors import ApplicationError, ErrorCode
from gameclub_backend.modules.auth.domain import Principal, SubjectType
from gameclub_backend.modules.catalog.domain import BillingMode, TariffAudience
from gameclub_backend.modules.clients.application.bonus import (
    BonusCommand,
    BonusEarningCommand,
    BonusEarningsPort,
    BonusGameQuote,
    StaleBonusQuoteError,
)
from gameclub_backend.modules.clients.bonus import BonusOperationKind, BonusPolicy, BonusSource
from gameclub_backend.modules.entitlements.application.ports import (
    ActiveSessionLookup,
    CashEntitlementSettlement,
    ClientEntitlementDebit,
    Clock,
    EntitlementRepository,
    TariffLookup,
    WorkstationLookup,
)
from gameclub_backend.modules.entitlements.domain import (
    Entitlement,
    EntitlementSettlementStatus,
    EntitlementStatus,
)
from gameclub_backend.modules.payment_methods.domain import (
    PaymentPart,
    normalize_payment_parts,
    validate_mixed_cash_transfer,
)


class UtcClock:
    def now(self) -> datetime.datetime:
        return datetime.datetime.now(datetime.UTC)


@dataclasses.dataclass(frozen=True)
class EntitlementConsumption:
    consumed_minutes: int
    active_entitlement_id: uuid.UUID | None
    active_remaining_minutes: int
    exhausted_entitlement_ids: tuple[uuid.UUID, ...] = ()


class EntitlementService:
    def __init__(
        self,
        repository: EntitlementRepository,
        tariffs: TariffLookup,
        clients: ClientEntitlementDebit,
        clock: Clock | None = None,
        active_sessions: ActiveSessionLookup | None = None,
        workstations: WorkstationLookup | None = None,
        cash: CashEntitlementSettlement | None = None,
        bonuses: BonusEarningsPort | None = None,
        transaction: Callable[[], contextlib.AbstractAsyncContextManager] | None = None,
    ) -> None:
        self._repository = repository
        self._tariffs = tariffs
        self._clients = clients
        self._clock = clock or UtcClock()
        self._active_sessions = active_sessions
        self._workstations = workstations
        self._cash = cash
        self._bonuses = bonuses
        self._transaction = transaction or contextlib.nullcontext
        self._reconciliation_lock = asyncio.Lock()

    async def list_for_client(self, client_id: uuid.UUID) -> list[Entitlement]:
        return await self._repository.list_for_client(client_id)

    async def get(self, entitlement_id: uuid.UUID) -> Entitlement:
        entitlement = await self._repository.get(entitlement_id)
        if entitlement is None:
            raise ApplicationError(ErrorCode.NOT_FOUND, "Entitlement not found")
        return entitlement

    async def get_active_for_client(self, client_id: uuid.UUID) -> Entitlement | None:
        return await self._repository.get_active_for_client(client_id)

    async def list_recoverable_settlements(
        self,
        limit: int = 100,
        now: datetime.datetime | None = None,
    ) -> list[Entitlement]:
        return await self._repository.list_recoverable_settlements(limit=limit, now=now)

    async def burn_active_for_client(
        self,
        client_id: uuid.UUID,
        reason: str,
    ) -> Entitlement | None:
        active = await self._repository.get_active_for_client(client_id)
        if active is None:
            return None
        return await self.burn(active.id, client_id, reason)

    async def quote_purchase(
        self, client_id: uuid.UUID, tariff_id: uuid.UUID, use_bonus: bool = False
    ) -> BonusGameQuote:
        if self._bonuses is None:
            raise ApplicationError(
                ErrorCode.DEPENDENCY_UNAVAILABLE, "Bonus payment is not configured"
            )
        tariff = await self._tariffs.get_tariff(tariff_id)
        if (
            tariff is None
            or not tariff.active
            or tariff.billing_mode is not BillingMode.BLOCK
            or not tariff.is_visible_to(self._clock.now(), TariffAudience.REGISTERED)
        ):
            raise ApplicationError(ErrorCode.CONFLICT, "Package is not available for this client")
        active = (
            await self._active_sessions.get_active_for_client(client_id)
            if self._active_sessions
            else None
        )
        session_id = active.id if active else None
        price = await self._purchase_price(client_id, tariff)
        return await self._bonuses.quote_bonus_game(client_id, price, use_bonus, session_id)

    async def _purchase_price(self, client_id: uuid.UUID, tariff) -> int:
        if self._bonuses is None:
            return tariff.price_cents
        client = await self._clients.get(client_id)
        quote = await self._tariffs.quote_for_tariff(
            tariff.id,
            tariff.group_id,
            self._clock.now(),
            discount_category=client.discount_category,
            audience=TariffAudience.REGISTERED,
        )
        return quote.price_cents

    async def purchase(
        self,
        client_id: uuid.UUID,
        tariff_id: uuid.UUID,
        actor_id: str,
        idempotency_key: str,
        payment_parts: Sequence[PaymentPart | Mapping[str, object]] | None = None,
        cash_shift_id: uuid.UUID | None = None,
        use_bonus: bool = False,
        expected_price_cents: int | None = None,
        expected_bonus_cents: int | None = None,
        expected_money_cents: int | None = None,
        expected_earned_bonus_cents: int | None = None,
        principal: Principal | None = None,
    ) -> Entitlement:
        if not isinstance(use_bonus, bool):
            raise ApplicationError(ErrorCode.INVALID_ARGUMENT, "Bonus choice must be a boolean")
        if use_bonus:
            operator = (
                principal is not None
                and principal.subject_type is SubjectType.OPERATOR
                and principal.can("clients.manage")
                and actor_id == principal.subject_id
            )
            member = (
                principal is not None
                and principal.subject_type is SubjectType.CLIENT
                and principal.subject_id == str(client_id)
                and actor_id == f"client:{client_id}"
            )
            if not operator and not member:
                raise ApplicationError(
                    ErrorCode.PERMISSION_DENIED, "Bonus purchase is not authorized for this client"
                )
        expected = (
            expected_price_cents,
            expected_bonus_cents,
            expected_money_cents,
            expected_earned_bonus_cents,
        )
        if use_bonus and (self._bonuses is None or any(value is None for value in expected)):
            raise ApplicationError(
                ErrorCode.INVALID_ARGUMENT, "Confirm the server payment quote first"
            )
        if any(
            value is not None
            and (isinstance(value, bool) or not isinstance(value, int) or value < 0)
            for value in expected
        ):
            raise ApplicationError(ErrorCode.INVALID_ARGUMENT, "Invalid confirmed payment quote")
        if use_bonus and (payment_parts or cash_shift_id is not None):
            raise ApplicationError(
                ErrorCode.INVALID_ARGUMENT,
                "Bonus payment uses the deposit for its monetary remainder",
            )
        async with self._transaction() if use_bonus else contextlib.nullcontext():
            purchased = await self._purchase(
                client_id,
                tariff_id,
                actor_id,
                idempotency_key,
                payment_parts,
                cash_shift_id,
                use_bonus,
                expected,
            )
            if purchased.settlement_status is EntitlementSettlementStatus.PENDING:
                return await self.retry_pending_settlement(purchased.id)
            return purchased

    async def _purchase(
        self,
        client_id: uuid.UUID,
        tariff_id: uuid.UUID,
        actor_id: str,
        idempotency_key: str,
        payment_parts: Sequence[PaymentPart | Mapping[str, object]] | None,
        cash_shift_id: uuid.UUID | None,
        use_bonus: bool,
        expected: tuple[int | None, int | None, int | None, int | None],
    ) -> Entitlement:
        key = idempotency_key.strip()
        actor = actor_id.strip()
        if not key or len(key) > 128:
            raise ApplicationError(ErrorCode.INVALID_ARGUMENT, "Idempotency key is required")
        if not actor:
            raise ApplicationError(ErrorCode.INVALID_ARGUMENT, "Purchase author is required")
        existing = await self._repository.get_by_idempotency_key(key)
        if existing is not None:
            return self._replay_purchase(
                existing,
                client_id,
                tariff_id,
                actor,
                payment_parts,
                cash_shift_id,
                use_bonus,
                expected,
            )
        tariff = await self._tariffs.get_tariff(tariff_id)
        if tariff is None:
            raise ApplicationError(ErrorCode.NOT_FOUND, "Tariff not found")
        if not tariff.active:
            raise ApplicationError(ErrorCode.CONFLICT, "Tariff is inactive")
        now = self._clock.now()
        if not tariff.is_visible_to(now, TariffAudience.REGISTERED):
            raise ApplicationError(
                ErrorCode.CONFLICT,
                "Tariff is not available for registered clients at this time",
            )
        active = (
            await self._active_sessions.get_active_for_client(client_id)
            if self._active_sessions
            else None
        )
        bonus_session_id = active.id if active is not None else None
        policy = (
            await self._bonuses.get_bonus_policy(client_id, bonus_session_id)
            if self._bonuses is not None
            else BonusPolicy(enabled=False)
        )
        if self._bonuses is not None and tariff.billing_mode is not BillingMode.BLOCK:
            raise ApplicationError(ErrorCode.CONFLICT, "A package tariff is required")
        price = await self._purchase_price(client_id, tariff)
        bonus_amount = 0
        earning_rate = policy.rate(BonusSource.GAME)
        bonus_limit = policy.payment_limit_bps if policy.enabled else 0
        if use_bonus:
            quote = await self._bonuses.quote_bonus_game(client_id, price, True, bonus_session_id)
            repeated = await self._repository.get_by_idempotency_key(key)
            if repeated is not None:
                return self._replay_purchase(
                    repeated,
                    client_id,
                    tariff_id,
                    actor,
                    payment_parts,
                    cash_shift_id,
                    use_bonus,
                    expected,
                )
            actual = (
                quote.price_cents,
                quote.bonus_cents,
                quote.money_cents,
                quote.earned_bonus_cents,
            )
            if actual != expected:
                raise StaleBonusQuoteError()
            if not quote.can_pay:
                raise ApplicationError(ErrorCode.CONFLICT, "Insufficient balance")
            bonus_amount = quote.bonus_cents
            earning_rate = quote.earning_rate_bps
            bonus_limit = quote.payment_limit_bps
        elif any(value is not None for value in expected):
            actual = (price, 0, price, price * earning_rate // 10000)
            if any(value is not None and value != actual[i] for i, value in enumerate(expected)):
                raise ApplicationError(ErrorCode.CONFLICT, "Confirmed payment quote has changed")
        try:
            parts = normalize_payment_parts(payment_parts, price - bonus_amount)
            validate_mixed_cash_transfer(parts)
            if not parts and price > bonus_amount:
                parts = (PaymentPart("balance", price - bonus_amount),)
            if any(part.method == "cash" for part in parts) and self._cash is None:
                raise ValueError("Cash settlement is not configured")
            queued = await self._repository.list_for_client(client_id)
            position = max((item.queue_position for item in queued), default=0) + 1
            entitlement = Entitlement(
                id=uuid.uuid4(),
                purchase_reason=f"Покупка тарифа «{tariff.name}»",
                purchase_actor_id=actor,
                bonus_requested=use_bonus,
                bonus_amount_cents=bonus_amount,
                bonus_rate_bps=earning_rate,
                bonus_session_id=bonus_session_id,
                bonus_limit_bps=bonus_limit,
                client_id=client_id,
                tariff_id=tariff.id,
                zone_id=tariff.group_id,
                duration_minutes=tariff.duration_minutes,
                remaining_minutes=tariff.duration_minutes,
                price_cents=price,
                queue_position=position,
                status=EntitlementStatus.QUEUED,
                idempotency_key=key,
                purchased_at=now,
                time_restricted=tariff.time_restricted,
                sale_window_start_minute=tariff.sale_window_start_minute,
                sale_window_end_minute=tariff.sale_window_end_minute,
                usage_window_start_minute=tariff.usage_window_start_minute,
                usage_window_end_minute=tariff.usage_window_end_minute,
                window_timezone=tariff.window_timezone,
                audience=tariff.audience,
                payment_parts=parts,
                cash_shift_id=cash_shift_id,
                settlement_status=EntitlementSettlementStatus.PENDING,
            )
        except ValueError as error:
            raise ApplicationError(ErrorCode.INVALID_ARGUMENT, str(error)) from error
        try:
            created = await self._repository.create(entitlement)
        except ValueError as error:
            raise ApplicationError(ErrorCode.CONFLICT, str(error)) from error
        if created.settlement_status is not EntitlementSettlementStatus.SETTLED:
            return await self._settle_pending(created, actor)
        return await self._activate_after_settlement(created, now)

    @staticmethod
    def _replay_purchase(
        existing: Entitlement,
        client_id: uuid.UUID,
        tariff_id: uuid.UUID,
        actor: str,
        payment_parts: Sequence[PaymentPart | Mapping[str, object]] | None,
        cash_shift_id: uuid.UUID | None,
        use_bonus: bool,
        expected: tuple[int | None, int | None, int | None, int | None],
    ) -> Entitlement:
        if (
            existing.client_id != client_id
            or existing.tariff_id != tariff_id
            or existing.bonus_requested != use_bonus
            or existing.purchase_actor_id not in (None, actor)
            or existing.cash_shift_id != cash_shift_id
        ):
            raise ApplicationError(
                ErrorCode.CONFLICT,
                "Idempotency key belongs to another package",
            )
        actual = (
            existing.price_cents,
            existing.bonus_amount_cents,
            existing.price_cents - existing.bonus_amount_cents,
            (existing.price_cents - existing.bonus_amount_cents) * existing.bonus_rate_bps // 10000,
        )
        if any(value is not None and value != actual[i] for i, value in enumerate(expected)):
            raise ApplicationError(ErrorCode.CONFLICT, "Confirmed payment quote has changed")
        if not use_bonus:
            try:
                requested_parts = normalize_payment_parts(payment_parts, existing.price_cents)
                if not requested_parts and existing.price_cents:
                    requested_parts = (PaymentPart("balance", existing.price_cents),)
                original_parts = existing.payment_parts
                if not original_parts and existing.price_cents:
                    original_parts = (PaymentPart("balance", existing.price_cents),)
                if requested_parts != original_parts:
                    raise ValueError("Payment parts have changed")
            except ValueError as error:
                raise ApplicationError(ErrorCode.CONFLICT, str(error)) from error
        if existing.settlement_status is not EntitlementSettlementStatus.SETTLED and not (
            existing.settlement_status is EntitlementSettlementStatus.PENDING
            and existing.settlement_error is not None
        ):
            raise ApplicationError(
                ErrorCode.CONFLICT,
                existing.settlement_error or "Package payment has not completed",
            )
        return existing

    async def retry_pending_settlement(self, entitlement_id: uuid.UUID) -> Entitlement:
        async with self._reconciliation_lock:
            current = await self.get(entitlement_id)
            if current.settlement_status is EntitlementSettlementStatus.NEEDS_REVIEW:
                raise ApplicationError(
                    ErrorCode.CONFLICT,
                    "Entitlement settlement requires explicit supervisor review",
                )
            if current.settlement_status is EntitlementSettlementStatus.SETTLED:
                return current
            return await self._settle_pending(current, current.idempotency_key)

    async def retry_settlement_review(
        self,
        entitlement_id: uuid.UUID,
        reviewed_by: str,
    ) -> Entitlement:
        if not reviewed_by.strip():
            raise ApplicationError(ErrorCode.INVALID_ARGUMENT, "Review author is required")
        entitlement = await self.get(entitlement_id)
        if entitlement.settlement_status is EntitlementSettlementStatus.SETTLED:
            return entitlement
        if entitlement.settlement_status is EntitlementSettlementStatus.NEEDS_REVIEW:
            entitlement = await self._repository.save(
                entitlement.reopen_settlement_for_review(self._clock.now())
            )
        return await self.retry_pending_settlement(entitlement.id)

    async def _settle_pending(
        self,
        entitlement: Entitlement,
        actor_id: str,
    ) -> Entitlement:
        now = self._clock.now()
        actor_id = entitlement.purchase_actor_id or actor_id
        tariff = await self._tariffs.get_tariff(entitlement.tariff_id)
        purchase_reason = entitlement.purchase_reason or (
            f"Покупка тарифа «{tariff.name}»" if tariff is not None else "Покупка тарифа"
        )
        try:
            if entitlement.bonus_amount_cents:
                if self._bonuses is None:
                    raise ApplicationError(
                        ErrorCode.DEPENDENCY_UNAVAILABLE, "Bonus payment is not configured"
                    )
                await self._bonuses.apply_bonus_operation(
                    BonusCommand(
                        entitlement.client_id,
                        BonusOperationKind.DEBIT,
                        entitlement.bonus_amount_cents,
                        actor_id,
                        purchase_reason,
                        f"entitlement-bonus:{entitlement.id}",
                    )
                )
            debit_ids = []
            for index, part in enumerate(entitlement.payment_parts):
                if part.method == "balance":
                    debit_result = await self._clients.debit(
                        client_id=entitlement.client_id,
                        amount_cents=part.amount_cents,
                        reason=purchase_reason,
                        actor_id=actor_id,
                        idempotency_key=f"entitlement-purchase:{entitlement.idempotency_key}:{index}",
                        allow_negative_balance=True,
                    )
                    if self._bonuses is not None:
                        _, debit = debit_result
                        debit_ids.append(debit.id)
                elif part.method == "cash":
                    if self._cash is None or entitlement.cash_shift_id is None:
                        raise ApplicationError(
                            ErrorCode.DEPENDENCY_UNAVAILABLE,
                            "Cash settlement is not configured",
                        )
                    await self._cash.settle(
                        shift_id=entitlement.cash_shift_id,
                        amount_cents=part.amount_cents,
                        payment_idempotency_key=f"{entitlement.idempotency_key}:{index}",
                        actor_id=actor_id,
                    )
            async with self._transaction():
                settled = await self._repository.save(entitlement.mark_settled(now))
                if self._bonuses is not None:
                    await self._bonuses.confirm_bonus_earning(
                        BonusEarningCommand(
                            receipt_id=uuid.uuid5(settled.id, "bonus-earning"),
                            client_id=settled.client_id,
                            source_key=f"entitlement:{settled.id}",
                            source=BonusSource.GAME,
                            policy=BonusPolicy(game_rate_bps=settled.bonus_rate_bps),
                            debit_operation_ids=tuple(debit_ids),
                            external_paid_cents=sum(
                                p.amount_cents
                                for p in settled.payment_parts
                                if p.method != "balance"
                            ),
                            session_id=settled.bonus_session_id,
                            actor_id=actor_id,
                        )
                    )
            return await self._activate_after_settlement(settled, now)
        except Exception as error:
            try:
                if self._is_retryable(error):
                    updated = entitlement.schedule_settlement_retry(str(error), now)
                else:
                    updated = entitlement.mark_needs_review(str(error), now)
                await self._repository.save(updated)
            except Exception:
                pass
            raise

    async def _activate_after_settlement(
        self,
        created: Entitlement,
        now: datetime.datetime,
    ) -> Entitlement:
        if self._active_sessions is not None and self._workstations is not None:
            active_session = await self._active_sessions.get_active_for_client(created.client_id)
            if active_session is not None:
                workstation = await self._workstations.get(active_session.workstation_id)
                if workstation is not None:
                    if await self._repository.get_active_for_client(created.client_id) is not None:
                        return created
                    next_item = await self.next_compatible(
                        created.client_id,
                        workstation.group_id,
                        now,
                    )
                    if next_item is None:
                        return created
                    try:
                        return await self._repository.activate_for_client(
                            next_item.id,
                            created.client_id,
                            now,
                            workstation.group_id,
                        )
                    except ValueError as error:
                        raise ApplicationError(ErrorCode.CONFLICT, str(error)) from error
        return created

    @staticmethod
    def _is_retryable(error: Exception) -> bool:
        return isinstance(error, ApplicationError) and error.code in {
            ErrorCode.DEPENDENCY_UNAVAILABLE,
            ErrorCode.INTERNAL,
        }

    async def activate(self, entitlement_id: uuid.UUID, client_id: uuid.UUID) -> Entitlement:
        entitlement = await self.get(entitlement_id)
        if entitlement.client_id != client_id:
            raise ApplicationError(
                ErrorCode.PERMISSION_DENIED,
                "Entitlement belongs to another client",
            )
        active = await self._repository.get_active_for_client(client_id)
        if active is not None and active.id != entitlement_id:
            raise ApplicationError(ErrorCode.CONFLICT, "Client already has an active package")
        now = self._clock.now()
        try:
            return await self._repository.activate_for_client(
                entitlement_id,
                client_id,
                now,
            )
        except ValueError as error:
            raise ApplicationError(ErrorCode.CONFLICT, str(error)) from error

    async def consume(
        self,
        entitlement_id: uuid.UUID,
        client_id: uuid.UUID,
        minutes: int,
    ) -> Entitlement:
        entitlement = await self.get(entitlement_id)
        if entitlement.client_id != client_id:
            raise ApplicationError(
                ErrorCode.PERMISSION_DENIED,
                "Entitlement belongs to another client",
            )
        try:
            updated, _ = await self._repository.consume_for_client(
                entitlement_id,
                client_id,
                minutes,
                self._clock.now(),
            )
            return updated
        except ValueError as error:
            raise ApplicationError(ErrorCode.CONFLICT, str(error)) from error

    async def burn(
        self,
        entitlement_id: uuid.UUID,
        client_id: uuid.UUID,
        reason: str,
    ) -> Entitlement:
        entitlement = await self.get(entitlement_id)
        if entitlement.client_id != client_id:
            raise ApplicationError(
                ErrorCode.PERMISSION_DENIED,
                "Entitlement belongs to another client",
            )
        try:
            return await self._repository.burn_for_client(
                entitlement_id,
                client_id,
                reason,
                self._clock.now(),
            )
        except ValueError as error:
            raise ApplicationError(ErrorCode.INVALID_ARGUMENT, str(error)) from error

    async def next_compatible(
        self,
        client_id: uuid.UUID,
        zone_id: str | None,
        now: datetime.datetime | None = None,
    ) -> Entitlement | None:
        return await self._repository.next_compatible(
            client_id,
            zone_id,
            now=now or self._clock.now(),
        )

    async def activate_next_compatible(
        self,
        client_id: uuid.UUID,
        zone_id: str | None,
        now: datetime.datetime | None = None,
    ) -> Entitlement | None:
        """Activate the first usable queued package without consuming its time."""
        moment = now or self._clock.now()
        active = await self._repository.get_active_for_client(client_id)
        if active is not None:
            return active
        next_item = await self.next_compatible(client_id, zone_id, moment)
        if next_item is None:
            return None
        try:
            return await self._repository.activate_for_client(
                next_item.id,
                client_id,
                moment,
                zone_id,
            )
        except ValueError as error:
            # Другой запрос meter или кабинета мог первым активировать пакет
            # клиента. В таком случае нужно вернуть уже активное состояние.
            active = await self._repository.get_active_for_client(client_id)
            if active is not None:
                return active
            raise ApplicationError(ErrorCode.CONFLICT, str(error)) from error

    async def consume_for_session(
        self,
        client_id: uuid.UUID,
        zone_id: str | None,
        minutes: int,
        now: datetime.datetime | None = None,
        initial_entitlement_id: uuid.UUID | None = None,
    ) -> EntitlementConsumption:
        """Consume active package minutes and auto-start the next compatible item."""
        if minutes < 0:
            raise ApplicationError(
                ErrorCode.INVALID_ARGUMENT,
                "Consumed minutes cannot be negative",
            )
        if minutes == 0:
            active = await self._repository.get_active_for_client(client_id)
            return EntitlementConsumption(
                consumed_minutes=0,
                active_entitlement_id=active.id if active else None,
                active_remaining_minutes=active.remaining_minutes if active else 0,
            )
        moment = now or self._clock.now()
        remaining_to_consume = minutes
        consumed = 0
        exhausted: list[uuid.UUID] = []
        active = await self._repository.get_active_for_client(client_id)
        if initial_entitlement_id is not None:
            initial = await self._repository.get(initial_entitlement_id)
            if initial is None or initial.client_id != client_id:
                raise ApplicationError(ErrorCode.NOT_FOUND, "Session package not found")
            if (active is None and initial.status is not EntitlementStatus.EXHAUSTED) or (
                active is not None
                and active.id != initial_entitlement_id
                and initial.status is not EntitlementStatus.EXHAUSTED
            ):
                raise ApplicationError(ErrorCode.CONFLICT, "Session package is not active")
        if active is None and initial_entitlement_id is None:
            return EntitlementConsumption(
                consumed_minutes=0,
                active_entitlement_id=None,
                active_remaining_minutes=0,
            )
        while remaining_to_consume:
            active = await self._repository.get_active_for_client(client_id)
            if active is None:
                next_item = await self.next_compatible(client_id, zone_id, moment)
                if next_item is None:
                    break
                try:
                    active = await self._repository.activate_for_client(
                        next_item.id,
                        client_id,
                        moment,
                        zone_id,
                    )
                except ValueError as error:
                    active = await self._repository.get_active_for_client(client_id)
                    if active is None:
                        raise ApplicationError(ErrorCode.CONFLICT, str(error)) from error
            if not active.is_compatible(zone_id) or not active.is_available_at(moment):
                break
            take = min(remaining_to_consume, active.remaining_minutes)
            if take <= 0:
                exhausted.append(active.id)
                continue
            try:
                updated, consumed_now = await self._repository.consume_for_client(
                    active.id,
                    client_id,
                    take,
                    moment,
                )
            except ValueError as error:
                raise ApplicationError(ErrorCode.CONFLICT, str(error)) from error
            consumed += consumed_now
            remaining_to_consume -= consumed_now
            if consumed_now == 0:
                break
            if updated.status is EntitlementStatus.EXHAUSTED:
                exhausted.append(updated.id)
        active = await self._repository.get_active_for_client(client_id)
        return EntitlementConsumption(
            consumed_minutes=consumed,
            active_entitlement_id=active.id if active else None,
            active_remaining_minutes=active.remaining_minutes if active else 0,
            exhausted_entitlement_ids=tuple(exhausted),
        )
