"""Одна PostgreSQL-транзакция для signed snapshot, lease, audit и outbox."""

from __future__ import annotations

import datetime
import uuid

from sqlalchemy import select, text

from gameclub.v2 import offline_session_snapshot_pb2
from gameclub_backend.application.audit import AuditEvent
from gameclub_backend.infrastructure.audit_postgres import AuditEventModel
from gameclub_backend.infrastructure.database import EngineProvider, open_session
from gameclub_backend.modules.eventing_v2.application.lease import V2SessionLease
from gameclub_backend.modules.eventing_v2.application.snapshot_issue import (
    V2SignedSnapshotIssue,
    V2SnapshotIssueResult,
)
from gameclub_backend.modules.eventing_v2.domain import (
    V2Event,
    V2EventType,
    V2OutgoingEventStatus,
    V2OutgoingServerEvent,
)
from gameclub_backend.modules.eventing_v2.infrastructure.lease_postgres import V2SessionLeaseModel
from gameclub_backend.modules.eventing_v2.infrastructure.postgres import V2ServerOutboxModel
from gameclub_backend.modules.sessions.application.ports import SessionTransactionWriter
from gameclub_backend.modules.sessions.domain import Session, SessionStatus
from gameclub_backend.modules.sessions.infrastructure.postgres import SessionModel


class PostgresV2SnapshotIssueRepository:
    """Не отвечает клиенту, пока signed snapshot не сохранён с lease и outbox."""

    def __init__(
        self,
        engine_provider: EngineProvider,
        session_writer: SessionTransactionWriter | None = None,
    ) -> None:
        self._engine_provider = engine_provider
        self._session_writer = session_writer

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

    async def _issue(
        self,
        value: V2SignedSnapshotIssue,
        session_to_start: Session | None = None,
    ) -> V2SnapshotIssueResult:
        lease = value.lease
        async with open_session(self._engine_provider) as session:
            async with session.begin():
                if self._session_writer is not None:
                    await self._session_writer.require_access(session, lease.session_id)
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

                lease_model = V2SessionLeaseModel.from_domain(lease)
                lease_model.signing_key_id = value.signed_snapshot.signing_key_id.strip()
                lease_model.snapshot_payload = value.payload_bytes
                lease_model.snapshot_signature = bytes(value.signed_snapshot.signature)
                lease_model.snapshot_payload_hash = value.payload_hash
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
