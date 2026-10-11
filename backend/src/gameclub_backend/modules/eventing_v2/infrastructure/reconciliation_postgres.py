"""Атомарное подтверждение факта клиентской V2-сессии в PostgreSQL."""

from __future__ import annotations

import datetime
import json
import uuid

from sqlalchemy import DateTime, Integer, String, Text, select, text
from sqlalchemy.dialects.postgresql import UUID, insert
from sqlalchemy.orm import Mapped, mapped_column

from gameclub_backend.application.audit import AuditEvent
from gameclub_backend.infrastructure.audit_postgres import AuditEventModel
from gameclub_backend.infrastructure.database import EngineProvider, open_session
from gameclub_backend.modules.clients.domain import BalanceOperation, BalanceOperationType
from gameclub_backend.modules.clients.infrastructure.postgres import (
    BalanceOperationModel,
    ClientModel,
)
from gameclub_backend.modules.eventing_v2.application.reconciliation import (
    V2ClientFactResult,
    V2ClientFactStatus,
)
from gameclub_backend.modules.eventing_v2.domain import (
    V2Event,
    V2EventType,
    V2OutgoingEventStatus,
    V2OutgoingServerEvent,
    V2SessionChain,
    V2SessionChainStatus,
)
from gameclub_backend.modules.eventing_v2.infrastructure.lease_postgres import V2SessionLeaseModel
from gameclub_backend.modules.eventing_v2.infrastructure.postgres import (
    V2EventInboxModel,
    V2EventingBase,
    V2ServerOutboxModel,
    V2SessionChainModel,
)
from gameclub_backend.modules.sessions.application.ports import SessionTransactionWriter
from gameclub_backend.modules.sessions.domain import SessionStatus
from gameclub_backend.modules.sessions.infrastructure.postgres import SessionModel

CONSUMER_NAME = "client_session_facts"
ALLOWED_CLIENT_FACT_TYPES = frozenset(
    {
        V2EventType.LOGIN_GRANT_CONSUMED,
        V2EventType.LOGIN_GRANT_BURNED,
        V2EventType.PACKAGE_PURCHASED,
        V2EventType.PACKAGE_CONSUMED,
        V2EventType.PER_MINUTE_DEBIT,
        V2EventType.PACKAGE_BURNED,
        V2EventType.SESSION_STOPPED,
    }
)


class V2ConfirmedClientFactModel(V2EventingBase):
    """Подтверждённый immutable source fact до финансовых проекций."""

    __tablename__ = "v2_confirmed_client_facts"

    event_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    operation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, unique=True)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    producer_id: Mapped[str] = mapped_column(String(128), nullable=False)
    client_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    session_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    device_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    sequence: Mapped[int] = mapped_column(Integer(), nullable=False)
    occurred_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    causation_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    correlation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    traceparent: Mapped[str] = mapped_column(String(55), nullable=False)
    payload_json: Mapped[str] = mapped_column(Text(), nullable=False)
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    previous_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    schema_version: Mapped[int] = mapped_column(Integer(), nullable=False)
    confirmed_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    def to_domain(self) -> V2Event:
        return V2Event(
            event_id=self.event_id,
            operation_id=self.operation_id,
            event_type=V2EventType(self.event_type),
            producer_id=self.producer_id,
            client_id=self.client_id,
            session_id=self.session_id,
            device_id=self.device_id,
            sequence=self.sequence,
            occurred_at=self.occurred_at,
            causation_id=self.causation_id,
            correlation_id=self.correlation_id,
            traceparent=self.traceparent,
            payload_json=self.payload_json,
            payload_hash=self.payload_hash,
            previous_hash=self.previous_hash,
            schema_version=self.schema_version,
        )

    @classmethod
    def values_from_event(
        cls,
        event: V2Event,
        confirmed_at: datetime.datetime,
    ) -> dict[str, object]:
        return {
            "event_id": event.event_id,
            "operation_id": event.operation_id,
            "event_type": event.event_type.value,
            "producer_id": event.producer_id,
            "client_id": event.client_id,
            "session_id": event.session_id,
            "device_id": event.device_id,
            "sequence": event.sequence,
            "occurred_at": event.occurred_at,
            "causation_id": event.causation_id,
            "correlation_id": event.correlation_id,
            "traceparent": event.traceparent,
            "payload_json": event.payload_json,
            "payload_hash": event.payload_hash,
            "previous_hash": event.previous_hash,
            "schema_version": event.schema_version,
            "confirmed_at": confirmed_at,
        }


class PostgresV2ClientFactReconciliationRepository:
    """Сериализует один session chain и фиксирует все side effects в одном commit."""

    def __init__(
        self,
        engine_provider: EngineProvider,
        session_writer: SessionTransactionWriter | None = None,
    ) -> None:
        self._engine_provider = engine_provider
        self._session_writer = session_writer

    async def accept(self, event: V2Event) -> V2ClientFactResult:
        if event.event_type not in ALLOWED_CLIENT_FACT_TYPES:
            return V2ClientFactResult(
                V2ClientFactStatus.CONFLICT,
                event.event_id,
                event.operation_id,
                "Тип V2-события не может быть фактом клиентской сессии",
            )
        async with open_session(self._engine_provider) as session:
            async with session.begin():
                await self._lock(
                    session,
                    f"v2-client-operation:{event.producer_id}:{event.operation_id}",
                )
                await self._lock(session, f"v2-client-session:{event.session_id}")
                lease = await self._active_lease(session, event)
                if lease is None:
                    return V2ClientFactResult(
                        V2ClientFactStatus.CONFLICT,
                        event.event_id,
                        event.operation_id,
                        "Нет активного V2 lease для client/device/session",
                    )
                if not self._matches_snapshot(lease, event):
                    return V2ClientFactResult(
                        V2ClientFactStatus.CONFLICT,
                        event.event_id,
                        event.operation_id,
                        "Snapshot клиента не совпадает с active V2 lease",
                    )
                if not self._has_valid_fact_payload(event):
                    return V2ClientFactResult(
                        V2ClientFactStatus.CONFLICT,
                        event.event_id,
                        event.operation_id,
                        "Payload клиентского V2-факта не соответствует контракту",
                    )
                existing = await session.scalar(
                    select(V2EventInboxModel).where(
                        V2EventInboxModel.consumer_name == CONSUMER_NAME,
                        V2EventInboxModel.producer_id == event.producer_id,
                        V2EventInboxModel.operation_id == event.operation_id,
                    )
                )
                if existing is not None:
                    if self._matches(existing.to_domain(), event):
                        return V2ClientFactResult(
                            V2ClientFactStatus.DUPLICATE,
                            existing.event_id,
                            event.operation_id,
                            "Клиентский V2-факт уже подтверждён",
                        )
                    return V2ClientFactResult(
                        V2ClientFactStatus.CONFLICT,
                        existing.event_id,
                        event.operation_id,
                        "operation_id уже принадлежит другому факту клиента",
                    )

                chain_status, next_chain = await self._next_chain(session, event)
                if chain_status is not V2SessionChainStatus.ACCEPTED or next_chain is None:
                    return V2ClientFactResult(
                        self._to_fact_status(chain_status),
                        event.event_id,
                        event.operation_id,
                        "Нарушен порядок или hash-chain клиентской V2-сессии",
                    )

                now = datetime.datetime.now(datetime.UTC)
                if event.event_type is V2EventType.PER_MINUTE_DEBIT:
                    if not await self._apply_per_minute_debit(session, event, now):
                        return V2ClientFactResult(
                            V2ClientFactStatus.CONFLICT,
                            event.event_id,
                            event.operation_id,
                            "Недостаточно средств на серверном балансе для поминутного списания",
                        )
                if event.event_type is V2EventType.SESSION_STOPPED:
                    if self._session_writer is not None:
                        closed_session = await self._session_writer.complete(
                            session,
                            event.session_id,
                            event.occurred_at,
                        )
                        if (
                            closed_session is None
                            or closed_session.client_id != event.client_id
                            or closed_session.source != "local_ledger"
                        ):
                            return V2ClientFactResult(
                                V2ClientFactStatus.CONFLICT,
                                event.event_id,
                                event.operation_id,
                                "V2 event does not match its server session",
                            )
                    lease.status = "revoked"
                    lease.revoked_at = now
                await session.execute(
                    insert(V2EventInboxModel).values(
                        **V2EventInboxModel.values_from_domain(CONSUMER_NAME, event)
                    )
                )
                await self._save_chain(session, next_chain)
                await session.execute(
                    insert(V2ConfirmedClientFactModel).values(
                        **V2ConfirmedClientFactModel.values_from_event(event, now)
                    )
                )
                result_event = self._result_event(event, now)
                session.add(
                    V2ServerOutboxModel(
                        **V2ServerOutboxModel.values_from_domain(
                            V2OutgoingServerEvent(
                                event=result_event,
                                topic="v2.server-events",
                                partition_key=(
                                    f"client-session:{event.client_id}:{event.session_id}"
                                ),
                                created_at=now,
                                status=V2OutgoingEventStatus.PENDING,
                            )
                        )
                    )
                )
                confirmed_domain_event = confirmed_per_minute_debit_event(event, now)
                if confirmed_domain_event is not None:
                    session.add(
                        V2ServerOutboxModel(
                            **V2ServerOutboxModel.values_from_domain(
                                V2OutgoingServerEvent(
                                    event=confirmed_domain_event,
                                    topic="v2.confirmed-domain-events",
                                    partition_key=(
                                        f"client-session:{event.client_id}:{event.session_id}"
                                    ),
                                    created_at=now,
                                    status=V2OutgoingEventStatus.PENDING,
                                )
                            )
                        )
                    )
                session.add(
                    AuditEventModel.from_domain(
                        AuditEvent(
                            id=uuid.uuid4(),
                            actor_id=None,
                            action="v2.client_fact.accepted",
                            resource_path=(
                                f"clients/{event.client_id}/sessions/{event.session_id}/"
                                f"operations/{event.operation_id}"
                            ),
                            outcome="success",
                            status_code=202,
                            request_id=str(event.operation_id),
                            created_at=now,
                        )
                    )
                )
                return V2ClientFactResult(
                    V2ClientFactStatus.ACCEPTED,
                    event.event_id,
                    event.operation_id,
                    "Клиентский V2-факт подтверждён",
                    result_event.event_id,
                )

    @staticmethod
    async def _lock(session, lock_key: str) -> None:
        await session.execute(
            text("SELECT pg_advisory_xact_lock(hashtext(:lock_key))"),
            {"lock_key": lock_key},
        )

    @staticmethod
    async def _next_chain(
        session,
        event: V2Event,
    ) -> tuple[V2SessionChainStatus, V2SessionChain | None]:
        stored = await session.scalar(
            select(V2SessionChainModel)
            .where(V2SessionChainModel.session_id == event.session_id)
            .with_for_update()
        )
        if stored is None:
            try:
                return V2SessionChainStatus.ACCEPTED, V2SessionChain.from_first_event(event)
            except ValueError:
                return V2SessionChainStatus.GAP, None
        return stored.to_domain().accept(event)

    @staticmethod
    async def _active_lease(session, event: V2Event) -> V2SessionLeaseModel | None:
        lease = await session.scalar(
            select(V2SessionLeaseModel)
            .where(V2SessionLeaseModel.session_id == event.session_id)
            .with_for_update()
        )
        server_session = await session.get(SessionModel, event.session_id)
        now = datetime.datetime.now(datetime.UTC)
        lease_matches = (
            lease is not None
            and lease.client_id == event.client_id
            and lease.device_id == event.device_id
        )
        session_matches = (
            server_session is not None
            and server_session.source == "local_ledger"
            and server_session.client_id == event.client_id
        )
        active_session_lease = (
            lease_matches
            and session_matches
            and lease.status == "active"
            and (lease.expires_at is None or lease.expires_at >= now)
            and server_session.status == SessionStatus.ACTIVE.value
        )
        fact_occurred_before_stop = (
            lease_matches
            and session_matches
            and server_session.status == SessionStatus.COMPLETED.value
            and server_session.ended_at is not None
            and event.occurred_at <= server_session.ended_at
        )
        if (
            not lease_matches
            or not session_matches
            or not (active_session_lease or fact_occurred_before_stop)
        ):
            return None
        return lease

    @staticmethod
    def _matches_snapshot(lease: V2SessionLeaseModel, event: V2Event) -> bool:
        """Не принимать факт от старого или чужого signed snapshot."""
        try:
            payload = json.loads(event.payload_json)
            snapshot_id = uuid.UUID(str(payload.get("snapshot_id", "")))
            snapshot_version = payload.get("snapshot_version")
        except (TypeError, ValueError, json.JSONDecodeError):
            return False
        return (
            isinstance(snapshot_version, int)
            and not isinstance(snapshot_version, bool)
            and snapshot_id == lease.snapshot_id
            and snapshot_version == lease.snapshot_version
        )

    @staticmethod
    def _has_valid_fact_payload(event: V2Event) -> bool:
        """Проверить только уже утверждённую форму факта до его подтверждения."""
        if event.event_type is not V2EventType.PER_MINUTE_DEBIT:
            return True
        try:
            payload = json.loads(event.payload_json)
        except json.JSONDecodeError:
            return False
        if not isinstance(payload, dict):
            return False
        amount_cents = payload.get("amount_cents")
        tariff_id = payload.get("tariff_id")
        return (
            isinstance(amount_cents, int)
            and not isinstance(amount_cents, bool)
            and amount_cents > 0
            and isinstance(tariff_id, str)
            and bool(tariff_id.strip())
        )

    @staticmethod
    async def _apply_per_minute_debit(
        session,
        event: V2Event,
        occurred_at: datetime.datetime,
    ) -> bool:
        """Списать минуту с серверного баланса в той же транзакции, что и подтверждение факта."""
        payload = json.loads(event.payload_json)
        amount_cents = payload["amount_cents"]
        client = await session.scalar(
            select(ClientModel)
            .where(ClientModel.id == event.client_id)
            .with_for_update()
        )
        if client is None or client.balance_cents < amount_cents:
            return False

        operation = BalanceOperation(
            id=uuid.uuid5(event.operation_id, "v2-per-minute-balance-operation"),
            client_id=event.client_id,
            amount_cents=-amount_cents,
            bonus_amount=0,
            reason=f"Поминутное списание за сессию {event.session_id}",
            actor_id=f"v2-device:{event.device_id[:117]}",
            idempotency_key=f"v2-per-minute-debit:{event.operation_id}",
            created_at=event.occurred_at,
            operation_type=BalanceOperationType.DEBIT,
        )
        client.balance_cents -= amount_cents
        client.updated_at = occurred_at
        session.add(BalanceOperationModel.from_domain(operation))
        return True

    @staticmethod
    async def _save_chain(session, chain: V2SessionChain) -> None:
        stored = await session.get(V2SessionChainModel, chain.session_id)
        if stored is None:
            session.add(V2SessionChainModel(**V2SessionChainModel.values_from_domain(chain)))
            return
        values = V2SessionChainModel.values_from_domain(chain)
        for key, value in values.items():
            setattr(stored, key, value)

    @staticmethod
    def _result_event(source: V2Event, occurred_at: datetime.datetime) -> V2Event:
        return V2Event.create(
            operation_id=source.operation_id,
            event_type=V2EventType.RECONCILIATION_COMPLETED,
            producer_id="server:reconciliation",
            client_id=source.client_id,
            session_id=source.session_id,
            device_id=source.device_id,
            sequence=1,
            occurred_at=occurred_at,
            causation_id=source.event_id,
            correlation_id=source.correlation_id,
            payload={
                "result": V2ClientFactStatus.ACCEPTED.value,
                "source_event_id": str(source.event_id),
                "source_operation_id": str(source.operation_id),
            },
        )

    @staticmethod
    def _matches(existing: V2Event, candidate: V2Event) -> bool:
        return (
            existing.event_id == candidate.event_id
            and existing.payload_hash == candidate.payload_hash
            and existing.event_type is candidate.event_type
            and existing.client_id == candidate.client_id
            and existing.session_id == candidate.session_id
            and existing.device_id == candidate.device_id
            and existing.sequence == candidate.sequence
            and existing.previous_hash == candidate.previous_hash
        )

    @staticmethod
    def _to_fact_status(status: V2SessionChainStatus) -> V2ClientFactStatus:
        if status is V2SessionChainStatus.GAP:
            return V2ClientFactStatus.GAP
        return V2ClientFactStatus.CONFLICT


def confirmed_per_minute_debit_event(
    source: V2Event,
    confirmed_at: datetime.datetime,
) -> V2Event | None:
    """Восстановить server-owned confirmed debit только из принятого source fact."""
    if source.event_type is not V2EventType.PER_MINUTE_DEBIT:
        return None
    payload = json.loads(source.payload_json)
    amount_cents = payload["amount_cents"]
    tariff_id = payload["tariff_id"].strip()
    return V2Event.create(
        event_id=uuid.uuid5(source.event_id, "confirmed-per-minute-debit"),
        operation_id=source.operation_id,
        event_type=V2EventType.PER_MINUTE_DEBIT,
        producer_id="server:reconciliation",
        client_id=source.client_id,
        session_id=source.session_id,
        device_id=source.device_id,
        sequence=1,
        occurred_at=confirmed_at,
        causation_id=source.event_id,
        correlation_id=source.correlation_id,
        traceparent=source.traceparent,
        payload={
            "amount_cents": amount_cents,
            "tariff_id": tariff_id,
            "source_event_id": str(source.event_id),
            "source_event_type": source.event_type.value,
            "source_payload_hash": source.payload_hash,
        },
    )
