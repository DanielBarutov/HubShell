from __future__ import annotations

import dataclasses
import datetime
import enum
import hashlib
import json
import uuid
from typing import Any


class OfflineOperationKind(enum.StrEnum):
    METER_DELTA = "meter_delta"
    STOP = "stop"
    LOCK = "lock"


class OfflineOperationStatus(enum.StrEnum):
    PENDING = "pending"
    APPLIED = "applied"
    DUPLICATE = "duplicate"
    CONFLICT = "conflict"
    REJECTED = "rejected"


@dataclasses.dataclass(frozen=True)
class OfflineOperation:
    id: uuid.UUID
    session_id: uuid.UUID
    device_id: str
    sequence: int
    kind: OfflineOperationKind
    payload_json: str
    snapshot_version: int
    idempotency_key: str
    checksum: str
    created_at: datetime.datetime

    def __post_init__(self) -> None:
        if not self.device_id.strip():
            raise ValueError("Offline device id is required")
        if self.sequence <= 0:
            raise ValueError("Offline sequence must be positive")
        if self.snapshot_version < 1:
            raise ValueError("Offline snapshot version is invalid")
        if not self.idempotency_key.strip() or len(self.idempotency_key) > 128:
            raise ValueError("Offline idempotency key is required")
        if self.created_at.tzinfo is None:
            raise ValueError("Offline operation timestamp must include timezone")
        try:
            payload = json.loads(self.payload_json)
        except json.JSONDecodeError as error:
            raise ValueError("Offline payload must be valid JSON") from error
        if not isinstance(payload, dict):
            raise ValueError("Offline payload must be a JSON object")
        if self.checksum != self.calculate_checksum(
            self.session_id,
            self.device_id,
            self.sequence,
            self.kind,
            self.payload_json,
            self.snapshot_version,
            self.idempotency_key,
        ):
            raise ValueError("Offline operation checksum is invalid")

    @staticmethod
    def calculate_checksum(
        session_id: uuid.UUID,
        device_id: str,
        sequence: int,
        kind: OfflineOperationKind,
        payload_json: str,
        snapshot_version: int,
        idempotency_key: str,
    ) -> str:
        payload = json.loads(payload_json)
        canonical = json.dumps(
            {
                "session_id": str(session_id),
                "device_id": device_id.strip(),
                "sequence": sequence,
                "kind": kind.value,
                "payload": payload,
                "snapshot_version": snapshot_version,
                "idempotency_key": idempotency_key.strip(),
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    @classmethod
    def create(
        cls,
        *,
        session_id: uuid.UUID,
        device_id: str,
        sequence: int,
        kind: OfflineOperationKind,
        payload: dict[str, Any],
        snapshot_version: int,
        idempotency_key: str,
        created_at: datetime.datetime,
        operation_id: uuid.UUID | None = None,
    ) -> OfflineOperation:
        payload_json = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        checksum = cls.calculate_checksum(
            session_id,
            device_id,
            sequence,
            kind,
            payload_json,
            snapshot_version,
            idempotency_key,
        )
        return cls(
            id=operation_id or uuid.uuid4(),
            session_id=session_id,
            device_id=device_id,
            sequence=sequence,
            kind=kind,
            payload_json=payload_json,
            snapshot_version=snapshot_version,
            idempotency_key=idempotency_key,
            checksum=checksum,
            created_at=created_at,
        )

    @property
    def payload(self) -> dict[str, Any]:
        value = json.loads(self.payload_json)
        return value if isinstance(value, dict) else {}


@dataclasses.dataclass(frozen=True)
class OfflineOperationResult:
    operation_id: uuid.UUID
    sequence: int
    status: OfflineOperationStatus
    message: str
    applied_at: datetime.datetime | None = None


@dataclasses.dataclass(frozen=True)
class OfflineBatch:
    protocol_version: int
    device_id: str
    session_id: uuid.UUID
    operations: tuple[OfflineOperation, ...]

    def __post_init__(self) -> None:
        if self.protocol_version != 1:
            raise ValueError("Unsupported offline protocol version")
        if not self.device_id.strip():
            raise ValueError("Offline batch device id is required")
        if not self.operations:
            raise ValueError("Offline batch cannot be empty")
        if len(self.operations) > 100:
            raise ValueError("Offline batch cannot contain more than 100 operations")
        if any(
            item.device_id != self.device_id or item.session_id != self.session_id
            for item in self.operations
        ):
            raise ValueError("Offline operation scope does not match batch")
        sequences = [item.sequence for item in self.operations]
        if sequences != sorted(sequences) or len(sequences) != len(set(sequences)):
            raise ValueError("Offline operation sequences must be ordered and unique")


@dataclasses.dataclass(frozen=True)
class OfflineBatchResult:
    protocol_version: int
    session_id: uuid.UUID
    results: tuple[OfflineOperationResult, ...]
    snapshot: Any | None
