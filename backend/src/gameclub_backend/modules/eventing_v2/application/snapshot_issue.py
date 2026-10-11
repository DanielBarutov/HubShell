"""Атомарная фиксация уже подписанного V2 snapshot, lease и outbox-маркера."""

from __future__ import annotations

import dataclasses
import hashlib
import typing
import uuid

from gameclub.v2 import offline_session_snapshot_pb2
from gameclub_backend.modules.eventing_v2.application.lease import V2SessionLease
from gameclub_backend.modules.eventing_v2.infrastructure.snapshot_protobuf import (
    serialize_snapshot_payload,
)
from gameclub_backend.modules.sessions.domain import Session


@dataclasses.dataclass(frozen=True)
class V2SignedSnapshotIssue:
    """Подписанный snapshot, который сервер обязан сохранить до ответа клиенту."""

    lease: V2SessionLease
    signed_snapshot: offline_session_snapshot_pb2.SignedOfflineSessionSnapshot

    def __post_init__(self) -> None:
        snapshot = self.signed_snapshot
        if (
            snapshot.payload is None
            or not snapshot.signing_key_id.strip()
            or not snapshot.signature
        ):
            raise ValueError("V2 signed snapshot is incomplete")
        payload = snapshot.payload
        try:
            snapshot_id = uuid.UUID(payload.snapshot_id)
            client_id = uuid.UUID(payload.client_id)
            session_id = uuid.UUID(payload.session_id)
        except ValueError as error:
            raise ValueError("V2 signed snapshot identifiers are invalid") from error
        if (
            payload.schema_version != 1
            or snapshot_id != self.lease.snapshot_id
            or payload.snapshot_version != self.lease.snapshot_version
            or client_id != self.lease.client_id
            or session_id != self.lease.session_id
            or payload.device_id != self.lease.device_id
            or payload.policy_version != self.lease.policy_version
        ):
            raise ValueError("V2 signed snapshot does not match its lease")

    @property
    def payload_bytes(self) -> bytes:
        return serialize_snapshot_payload(self.signed_snapshot.payload)

    @property
    def payload_hash(self) -> str:
        return hashlib.sha256(self.payload_bytes).hexdigest()


@dataclasses.dataclass(frozen=True)
class V2SnapshotIssueResult:
    signed_snapshot: offline_session_snapshot_pb2.SignedOfflineSessionSnapshot
    login_event_id: uuid.UUID
    is_duplicate: bool


class V2SnapshotIssueRepository(typing.Protocol):
    async def has_active_lease(
        self,
        session_id: uuid.UUID,
        client_id: uuid.UUID,
        device_id: str,
    ) -> bool:
        """Check the active server-owned lease for a client/device/session tuple."""

    async def issue(self, value: V2SignedSnapshotIssue) -> V2SnapshotIssueResult:
        """Atomically save snapshot bytes, exclusive lease, audit and server outbox."""

    async def issue_with_new_session(
        self,
        value: V2SignedSnapshotIssue,
        session: Session,
    ) -> V2SnapshotIssueResult:
        """Atomically start a new session together with snapshot, lease and outbox."""


class V2SnapshotIssueService:
    def __init__(self, repository: V2SnapshotIssueRepository) -> None:
        self._repository = repository

    async def has_active_lease(
        self,
        session_id: uuid.UUID,
        client_id: uuid.UUID,
        device_id: str,
    ) -> bool:
        return await self._repository.has_active_lease(session_id, client_id, device_id)

    async def issue(self, value: V2SignedSnapshotIssue) -> V2SnapshotIssueResult:
        return await self._repository.issue(value)

    async def issue_with_new_session(
        self,
        value: V2SignedSnapshotIssue,
        session: Session,
    ) -> V2SnapshotIssueResult:
        return await self._repository.issue_with_new_session(value, session)
