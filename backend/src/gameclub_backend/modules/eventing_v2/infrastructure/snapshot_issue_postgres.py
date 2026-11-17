"""Одна PostgreSQL-транзакция для signed snapshot, lease, audit и outbox."""

from __future__ import annotations

import datetime
import json
import uuid

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from gameclub.v2 import offline_session_snapshot_pb2
from gameclub_backend.application.audit import AuditEvent
from gameclub_backend.application.errors import ApplicationError, ErrorCode
from gameclub_backend.infrastructure.audit_postgres import AuditEventModel
from gameclub_backend.infrastructure.database import EngineProvider, open_session
from gameclub_backend.modules.entitlements.application.ports import EntitlementTransactionWriter
from gameclub_backend.modules.eventing_v2.application.lease import V2SessionLease
from gameclub_backend.modules.eventing_v2.application.snapshot_issue import (
    V2SignedSnapshotIssue,
    V2SnapshotIssueResult,
    V2TransferMinuteBonus,
    V2TransferSourceState,
)
from gameclub_backend.modules.eventing_v2.domain import (
    V2Event,
    V2EventType,
    V2OutgoingEventStatus,
    V2OutgoingServerEvent,
)
from gameclub_backend.modules.eventing_v2.infrastructure.bonus_budget_postgres import (
    V2BonusBudgetModel,
)
from gameclub_backend.modules.eventing_v2.infrastructure.lease_postgres import V2SessionLeaseModel
from gameclub_backend.modules.eventing_v2.infrastructure.postgres import (
    PostgresV2SessionChainRepository,
    V2ServerOutboxModel,
    lock_v2_client_session,
)
from gameclub_backend.modules.eventing_v2.infrastructure.reconciliation_postgres import (
    V2ConfirmedClientFactModel,
)
from gameclub_backend.modules.sessions.application.ports import SessionTransactionWriter
from gameclub_backend.modules.sessions.application.v2_transfer import (
    V2TransferReservation,
    V2TransferStatus,
)
from gameclub_backend.modules.sessions.domain import Session, SessionStatus
from gameclub_backend.modules.sessions.infrastructure.postgres import SessionModel


class PostgresV2SnapshotIssueRepository:
    """Не отвечает клиенту, пока signed snapshot не сохранён с lease и outbox."""

    def __init__(
        self,
        engine_provider: EngineProvider,
        session_writer: SessionTransactionWriter | None = None,
        entitlements: EntitlementTransactionWriter | None = None,
    ) -> None:
        self._engine_provider = engine_provider
        self._session_writer = session_writer
        self._entitlements = entitlements

    async def has_active_lease(
        self,
        session_id: uuid.UUID,
        client_id: uuid.UUID,
        device_id: str,
    ) -> bool:
        async with open_session(self._engine_provider) as session:
            lease = await session.get(V2SessionLeaseModel, session_id)
            return bool(
                lease is not None
                and lease.status == "active"
                and lease.client_id == client_id
                and lease.device_id == device_id
                and (
                    lease.expires_at is None
                    or lease.expires_at >= datetime.datetime.now(datetime.UTC)
                )
            )

    async def issue(self, value: V2SignedSnapshotIssue) -> V2SnapshotIssueResult:
        return await self._issue(value)

    async def issue_with_new_session(
        self,
        value: V2SignedSnapshotIssue,
        session_to_start: Session,
    ) -> V2SnapshotIssueResult:
        if self._session_writer is None:
            raise RuntimeError("V2 snapshot issuer has no session transaction writer")
        self._validate_new_session(value, session_to_start)
        return await self._issue(value, session_to_start)

    async def transfer_source_state(
        self,
        operation: V2TransferReservation,
        source_device_id: str,
    ) -> V2TransferSourceState:
        async with open_session(self._engine_provider) as db:
            if not db.in_transaction():
                raise RuntimeError("Transfer billing state requires the session commit transaction")
            lease = await db.get(V2SessionLeaseModel, operation.session_id, with_for_update=True)
            if lease is None or lease.status != "active" or lease.device_id != source_device_id:
                raise ApplicationError(ErrorCode.CONFLICT, "Transfer source lease changed")
            budget = await self._active_transfer_bonus(db, lease)

            checkpoint = operation.source_checkpoint
            if checkpoint is None:
                raise ApplicationError(ErrorCode.CONFLICT, "Transfer source is not ready")
            payload = self._signed_snapshot(lease).payload
            query = (
                select(V2ConfirmedClientFactModel)
                .where(
                    V2ConfirmedClientFactModel.session_id == operation.session_id,
                    V2ConfirmedClientFactModel.device_id == source_device_id,
                    V2ConfirmedClientFactModel.sequence <= checkpoint.sequence,
                    V2ConfirmedClientFactModel.occurred_at >= lease.issued_at,
                )
                .order_by(V2ConfirmedClientFactModel.sequence.desc())
                .limit(1)
            )
            grant = await db.scalar(
                query.where(
                    V2ConfirmedClientFactModel.event_type.in_(
                        (
                            V2EventType.LOGIN_GRANT_CONSUMED.value,
                            V2EventType.LOGIN_GRANT_BURNED.value,
                        )
                    )
                )
            )
            grant_minutes = payload.login_grant_remaining_minutes
            if grant is not None:
                grant_minutes = (
                    json.loads(grant.payload_json).get("remaining_minutes")
                    if grant.event_type == V2EventType.LOGIN_GRANT_CONSUMED.value
                    else 0
                )
            if (
                type(grant_minutes) is not int
                or not 0 <= grant_minutes <= payload.login_grant_remaining_minutes
            ):
                raise ApplicationError(ErrorCode.CONFLICT, "Transfer login grant is inconsistent")

            billed = await db.scalar(
                query.where(
                    V2ConfirmedClientFactModel.event_type.in_(
                        (
                            V2EventType.LOGIN_GRANT_CONSUMED.value,
                            V2EventType.PACKAGE_CONSUMED.value,
                            V2EventType.PER_MINUTE_DEBIT.value,
                        )
                    )
                )
            )
            return V2TransferSourceState(
                lease.to_domain(),
                grant_minutes,
                billed.occurred_at if billed is not None else lease.issued_at,
                any(
                    tariff.is_per_minute and tariff.per_minute_price_cents == 0
                    for tariff in payload.tariffs
                ),
                V2TransferMinuteBonus(
                    budget.id,
                    budget.version,
                    budget.budget_cents - budget.spent_cents,
                    budget.payment_limit_bps,
                )
                if budget is not None
                else None,
            )

    @staticmethod
    async def _active_transfer_bonus(
        db: AsyncSession, lease: V2SessionLeaseModel
    ) -> V2BonusBudgetModel | None:
        budget = await db.scalar(
            select(V2BonusBudgetModel)
            .where(
                V2BonusBudgetModel.session_id == lease.session_id,
                V2BonusBudgetModel.active,
            )
            .with_for_update()
        )
        if budget is not None and (
            budget.cancelled
            or budget.client_id != lease.client_id
            or budget.device_id != lease.device_id
            or budget.snapshot_id != lease.snapshot_id
            or budget.snapshot_version != lease.snapshot_version
        ):
            raise ApplicationError(
                ErrorCode.CONFLICT, "Transfer minute bonus no longer matches the lease"
            )
        return budget

    async def transfer_lease(
        self,
        operation: V2TransferReservation,
        source_device_id: str,
        value: V2SignedSnapshotIssue,
    ) -> None:
        """Replace the lease inside the transaction committing a prepared transfer."""
        lease = value.lease
        checkpoint = operation.source_checkpoint
        payload = value.signed_snapshot.payload
        handoff = payload.transfer_handoff
        if (
            operation.status is not V2TransferStatus.PREPARING
            or not operation.target_ready
            or checkpoint is None
            or not payload.HasField("transfer_handoff")
            or handoff.operation_id != str(operation.operation_id)
            or handoff.last_sequence != checkpoint.sequence
            or (handoff.last_payload_hash or None) != checkpoint.payload_hash
            or operation.session_id != lease.session_id
            or source_device_id == lease.device_id
            or payload.purchase_idempotency_key
            or payload.HasField("purchase_money_cents")
            or payload.purchase_bonus_cents
        ):
            raise ApplicationError(
                ErrorCode.CONFLICT, "Signed snapshot does not match the transfer"
            )

        chains = PostgresV2SessionChainRepository(self._engine_provider)
        async with open_session(self._engine_provider) as db:
            if not db.in_transaction():
                raise RuntimeError("Transfer lease requires the session commit transaction")
            await lock_v2_client_session(db, lease.session_id)
            for key in (
                f"v2-lease-client:{lease.client_id}",
                f"v2-lease-device:{lease.device_id}",
                f"v2-lease-session:{lease.session_id}",
            ):
                await db.execute(
                    text("SELECT pg_advisory_xact_lock(hashtext(:lock_key))"), {"lock_key": key}
                )

            current = await db.get(V2SessionLeaseModel, lease.session_id, with_for_update=True)
            now = datetime.datetime.now(datetime.UTC)
            if (
                current is None
                or current.status != "active"
                or current.device_id != source_device_id
                or current.client_id != lease.client_id
                or lease.snapshot_version != current.snapshot_version + 1
                or lease.snapshot_id == current.snapshot_id
                or (current.expires_at is not None and current.expires_at <= now)
            ):
                raise ApplicationError(ErrorCode.CONFLICT, "Transfer source lease changed")
            existing_target = await db.scalar(
                select(V2SessionLeaseModel.session_id)
                .where(
                    V2SessionLeaseModel.device_id == lease.device_id,
                    V2SessionLeaseModel.status == "active",
                )
                .limit(1)
            )
            if existing_target is not None:
                raise ApplicationError(
                    ErrorCode.CONFLICT, "Transfer target already has an active lease"
                )
            budget = await self._active_transfer_bonus(db, current)
            bonus = handoff.minute_bonus
            if handoff.HasField("minute_bonus") != (budget is not None) or (
                budget is not None
                and (
                    bonus.grant_id != str(budget.id)
                    or bonus.version != budget.version
                    or bonus.remaining_cents != budget.budget_cents - budget.spent_cents
                    or bonus.payment_limit_bps != budget.payment_limit_bps
                )
            ):
                raise ApplicationError(ErrorCode.CONFLICT, "Signed transfer minute bonus changed")
            if budget is not None:
                budget.device_id = lease.device_id
                budget.snapshot_id = lease.snapshot_id
                budget.snapshot_version = lease.snapshot_version
                budget.last_sequence = checkpoint.sequence
                budget.last_payload_hash = checkpoint.payload_hash
            await chains.transfer_checkpoint(
                lease.session_id,
                source_device_id,
                lease.device_id,
                checkpoint.sequence,
                checkpoint.payload_hash,
            )
            current.device_id = lease.device_id
            current.snapshot_id = lease.snapshot_id
            current.snapshot_version = lease.snapshot_version
            current.policy_version = lease.policy_version
            current.issued_at = lease.issued_at
            current.expires_at = lease.expires_at
            self._store_signed_snapshot(current, value)

    async def get_transfer_snapshot(
        self, operation: V2TransferReservation, target_device_id: str
    ) -> offline_session_snapshot_pb2.SignedOfflineSessionSnapshot | None:
        if operation.status is not V2TransferStatus.COMMITTED:
            return None
        async with open_session(self._engine_provider) as db:
            lease = await db.get(V2SessionLeaseModel, operation.session_id)
            if (
                lease is None
                or lease.status != "active"
                or lease.device_id != target_device_id
                or (
                    lease.expires_at is not None
                    and lease.expires_at <= datetime.datetime.now(datetime.UTC)
                )
            ):
                return None
            signed = self._signed_snapshot(lease)
            if signed.payload.transfer_handoff.operation_id != str(operation.operation_id):
                return None
            return signed

    @staticmethod
    def _store_signed_snapshot(
        lease_model: V2SessionLeaseModel, value: V2SignedSnapshotIssue
    ) -> None:
        lease_model.signing_key_id = value.signed_snapshot.signing_key_id.strip()
        lease_model.snapshot_payload = value.payload_bytes
        lease_model.snapshot_signature = bytes(value.signed_snapshot.signature)
        lease_model.snapshot_payload_hash = value.payload_hash

    async def _issue(
        self,
        value: V2SignedSnapshotIssue,
        session_to_start: Session | None = None,
    ) -> V2SnapshotIssueResult:
        if value.signed_snapshot.payload.HasField("transfer_handoff"):
            raise ValueError("Transfer snapshots require a committed transfer")
        lease = value.lease
        async with open_session(self._engine_provider) as session:
            async with session.begin():
                if self._session_writer is not None:
                    await self._session_writer.require_access(
                        session,
                        lease.session_id,
                        session_to_start.workstation_id if session_to_start is not None else None,
                    )
                for lock_key in (
                    f"v2-lease-client:{lease.client_id}",
                    f"v2-lease-device:{lease.device_id}",
                    f"v2-lease-session:{lease.session_id}",
                ):
                    await session.execute(
                        text("SELECT pg_advisory_xact_lock(hashtext(:lock_key))"),
                        {"lock_key": lock_key},
                    )
                if session_to_start is not None:
                    assert self._session_writer is not None
                    persisted_session = await self._session_writer.save(session, session_to_start)
                    if persisted_session.id != session_to_start.id:
                        return await self._existing_snapshot_for_repeated_session(
                            session,
                            persisted_session,
                            lease,
                        )
                current = await session.get(V2SessionLeaseModel, lease.session_id)
                if current is not None:
                    if self._matches(current, value):
                        return V2SnapshotIssueResult(
                            signed_snapshot=self._signed_snapshot(current),
                            login_event_id=current.snapshot_id,
                            is_duplicate=True,
                        )
                    if self._is_same_active_session(current, lease):
                        return V2SnapshotIssueResult(
                            signed_snapshot=self._signed_snapshot(current),
                            login_event_id=current.snapshot_id,
                            is_duplicate=True,
                        )
                    raise ValueError("V2 session id belongs to another signed snapshot")

                active = await session.scalars(
                    select(V2SessionLeaseModel)
                    .where(
                        V2SessionLeaseModel.status == "active",
                        (V2SessionLeaseModel.client_id == lease.client_id)
                        | (V2SessionLeaseModel.device_id == lease.device_id),
                    )
                    .with_for_update()
                )
                has_live_lease = False
                for active_lease in active:
                    previous_session = await session.get(
                        SessionModel,
                        active_lease.session_id,
                        with_for_update=True,
                    )
                    if previous_session is None or (
                        previous_session.source == "local_ledger"
                        and previous_session.status == SessionStatus.COMPLETED.value
                    ):
                        active_lease.status = "revoked"
                        active_lease.revoked_at = (
                            previous_session.ended_at if previous_session is not None else None
                        ) or lease.issued_at
                    else:
                        has_live_lease = True
                if has_live_lease:
                    raise ValueError("Client or device already has an active V2 lease")

                packages = value.signed_snapshot.payload.packages
                if self._entitlements is not None and packages:
                    if await self._entitlements.contains_removed_packages(
                        session,
                        lease.client_id,
                        tuple(uuid.UUID(item.package_id) for item in packages),
                    ):
                        raise ValueError("Очередь тарифов изменилась. Повторите вход.")

                lease_model = V2SessionLeaseModel.from_domain(lease)
                self._store_signed_snapshot(lease_model, value)
                session.add(lease_model)

                event = self._login_event(value)
                session.add(
                    V2ServerOutboxModel(
                        **V2ServerOutboxModel.values_from_domain(
                            V2OutgoingServerEvent(
                                event=event,
                                topic="v2.server-events",
                                partition_key=(
                                    f"client-session:{lease.client_id}:{lease.session_id}"
                                ),
                                created_at=lease.issued_at,
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
                            action="v2.snapshot.issued",
                            resource_path=(
                                f"clients/{lease.client_id}/sessions/{lease.session_id}/"
                                f"snapshots/{lease.snapshot_id}"
                            ),
                            outcome="success",
                            status_code=201,
                            request_id=str(lease.snapshot_id),
                            created_at=lease.issued_at,
                        )
                    )
                )
                return V2SnapshotIssueResult(
                    signed_snapshot=value.signed_snapshot,
                    login_event_id=event.event_id,
                    is_duplicate=False,
                )

    @staticmethod
    def _validate_new_session(value: V2SignedSnapshotIssue, session: Session) -> None:
        lease = value.lease
        if (
            session.id != lease.session_id
            or session.client_id != lease.client_id
            or session.status is not SessionStatus.ACTIVE
            or session.source != "local_ledger"
        ):
            raise ValueError("New V2 session does not match its signed snapshot lease")

    async def _existing_snapshot_for_repeated_session(
        self,
        transaction,
        persisted_session: Session,
        requested_lease: V2SessionLease,
    ) -> V2SnapshotIssueResult:
        current = await transaction.get(V2SessionLeaseModel, persisted_session.id)
        if current is None or not self._is_same_active_session(current, requested_lease):
            raise ValueError("Existing V2 session has no matching signed snapshot")
        return V2SnapshotIssueResult(
            signed_snapshot=self._signed_snapshot(current),
            login_event_id=current.snapshot_id,
            is_duplicate=True,
        )

    @staticmethod
    def _matches(current: V2SessionLeaseModel, value: V2SignedSnapshotIssue) -> bool:
        return (
            current.status == "active"
            and current.snapshot_id == value.lease.snapshot_id
            and current.snapshot_payload_hash == value.payload_hash
            and current.signing_key_id == value.signed_snapshot.signing_key_id.strip()
            and current.snapshot_signature == bytes(value.signed_snapshot.signature)
            and current.snapshot_payload == value.payload_bytes
        )

    @staticmethod
    def _is_same_active_session(
        current: V2SessionLeaseModel,
        lease: V2SessionLease,
    ) -> bool:
        """A lost gRPC response must return the persisted snapshot, not make another one."""
        return (
            current.status == "active"
            and current.client_id == lease.client_id
            and current.device_id == lease.device_id
            and current.policy_version == lease.policy_version
            and current.signing_key_id is not None
            and current.snapshot_payload is not None
            and current.snapshot_signature is not None
        )

    @staticmethod
    def _signed_snapshot(
        lease: V2SessionLeaseModel,
    ) -> offline_session_snapshot_pb2.SignedOfflineSessionSnapshot:
        if (
            lease.signing_key_id is None
            or lease.snapshot_payload is None
            or lease.snapshot_signature is None
        ):
            raise RuntimeError("Active V2 lease does not retain signed snapshot bytes")
        payload = offline_session_snapshot_pb2.OfflineSessionSnapshotPayload()
        payload.ParseFromString(lease.snapshot_payload)
        return offline_session_snapshot_pb2.SignedOfflineSessionSnapshot(
            payload=payload,
            signing_key_id=lease.signing_key_id,
            signature=lease.snapshot_signature,
        )

    @staticmethod
    def _login_event(value: V2SignedSnapshotIssue) -> V2Event:
        lease = value.lease
        return V2Event.create(
            event_id=lease.snapshot_id,
            operation_id=lease.snapshot_id,
            event_type=V2EventType.LOGIN_SNAPSHOT_ISSUED,
            producer_id="server:v2-snapshot",
            client_id=lease.client_id,
            session_id=lease.session_id,
            device_id=lease.device_id,
            sequence=1,
            occurred_at=lease.issued_at,
            payload={
                "snapshot_id": str(lease.snapshot_id),
                "snapshot_version": lease.snapshot_version,
                "signing_key_id": value.signed_snapshot.signing_key_id.strip(),
                "snapshot_payload_hash": value.payload_hash,
            },
        )
