from __future__ import annotations

import dataclasses
import datetime
import enum
import hashlib
import json
import re
import uuid
from typing import Any


class V2EventType(enum.StrEnum):
    """Allowed immutable facts exchanged by the V2 session protocol."""

    LOGIN_REQUESTED = "login_requested"
    LOGIN_SNAPSHOT_ISSUED = "login_snapshot_issued"
    LOGIN_GRANT_CONSUMED = "login_grant_consumed"
    LOGIN_GRANT_BURNED = "login_grant_burned"
    PACKAGE_PURCHASED = "package_purchased"
    PACKAGE_CONSUMED = "package_consumed"
    PER_MINUTE_DEBIT = "per_minute_debit"
    PACKAGE_BURNED = "package_burned"
    SESSION_STOPPED = "session_stopped"
    BALANCE_CREDIT_APPLIED = "balance_credit_applied"
    RECONCILIATION_COMPLETED = "reconciliation_completed"


class V2InboxStatus(enum.StrEnum):
    """Result of one idempotency-bound inbox acceptance attempt."""

    ACCEPTED = "accepted"
    DUPLICATE = "duplicate"
    CONFLICT = "conflict"


class V2SessionChainStatus(enum.StrEnum):
    """Итог проверки порядка immutable фактов одной клиентской сессии."""

    ACCEPTED = "accepted"
    GAP = "gap"
    CONFLICT = "conflict"


class V2OutgoingEventStatus(enum.StrEnum):
    """Состояние исходящего серверного сообщения до и после отправки."""

    PENDING = "pending"
    PUBLISHED = "published"
    ACKNOWLEDGED = "acknowledged"


@dataclasses.dataclass(frozen=True)
class V2Event:
    """Immutable versioned message before a transport serializes it."""

    event_id: uuid.UUID
    operation_id: uuid.UUID
    event_type: V2EventType
    producer_id: str
    client_id: uuid.UUID
    session_id: uuid.UUID
    device_id: str
    sequence: int
    occurred_at: datetime.datetime
    payload_json: str
    payload_hash: str
    previous_hash: str | None
    schema_version: int = 1
    causation_id: uuid.UUID | None = None
    correlation_id: uuid.UUID | None = None
    traceparent: str | None = None

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("Unsupported V2 event schema version")
        if self.correlation_id is None:
            raise ValueError("V2 event correlation id is required")
        if not self._is_traceparent(self.traceparent):
            raise ValueError("V2 event traceparent is invalid")
        if not self.producer_id.strip():
            raise ValueError("V2 event producer id is required")
        if not self.device_id.strip():
            raise ValueError("V2 event device id is required")
        if self.sequence < 1:
            raise ValueError("V2 event sequence must be positive")
        if self.occurred_at.tzinfo is None:
            raise ValueError("V2 event timestamp must include timezone")
        if self.sequence == 1 and self.previous_hash is not None:
            raise ValueError("First V2 event cannot have previous hash")
        if self.sequence > 1 and not self._is_sha256(self.previous_hash):
            raise ValueError("V2 event previous hash is invalid")
        payload = self._parse_payload(self.payload_json)
        expected_hash = self.calculate_payload_hash(payload)
        if self.payload_hash != expected_hash:
            raise ValueError("V2 event payload hash is invalid")

    @classmethod
    def create(
        cls,
        *,
        operation_id: uuid.UUID,
        event_type: V2EventType,
        producer_id: str,
        client_id: uuid.UUID,
        session_id: uuid.UUID,
        device_id: str,
        sequence: int,
        occurred_at: datetime.datetime,
        payload: dict[str, Any],
        previous_hash: str | None = None,
        causation_id: uuid.UUID | None = None,
        correlation_id: uuid.UUID | None = None,
        traceparent: str | None = None,
        event_id: uuid.UUID | None = None,
    ) -> V2Event:
        """Create a canonical event whose payload hash is independent of dict order."""
        payload_json = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return cls(
            event_id=event_id or uuid.uuid4(),
            operation_id=operation_id,
            event_type=event_type,
            producer_id=producer_id,
            client_id=client_id,
            session_id=session_id,
            device_id=device_id,
            sequence=sequence,
            occurred_at=occurred_at,
            payload_json=payload_json,
            payload_hash=cls.calculate_payload_hash(payload),
            previous_hash=previous_hash,
            causation_id=causation_id,
            correlation_id=correlation_id or session_id,
            traceparent=traceparent or cls.new_traceparent(),
        )

    @classmethod
    def from_transport_payload(cls, message: dict[str, object]) -> V2Event:
        """Проверить Kafka-конверт до передачи факта бизнес-обработчику."""
        payload = message.get("payload")
        if not isinstance(payload, dict):
            raise ValueError("V2 transport payload must be a JSON object")
        schema_version = message.get("schema_version")
        if not isinstance(schema_version, int) or isinstance(schema_version, bool):
            raise ValueError("V2 transport schema version must be an integer")
        previous_hash = message.get("previous_hash")
        if previous_hash is not None and not isinstance(previous_hash, str):
            raise ValueError("V2 transport previous hash must be a string")
        causation_id = cls._parse_optional_uuid(message.get("causation_id"), "causation id")
        correlation_id = cls._parse_uuid(message.get("correlation_id"), "correlation id")
        return cls.create(
            event_id=cls._parse_uuid(message.get("event_id"), "event id"),
            operation_id=cls._parse_uuid(message.get("operation_id"), "operation id"),
            event_type=cls._parse_event_type(message.get("event_type")),
            producer_id=cls._parse_string(message.get("producer_id"), "producer id"),
            client_id=cls._parse_uuid(message.get("client_id"), "client id"),
            session_id=cls._parse_uuid(message.get("session_id"), "session id"),
            device_id=cls._parse_string(message.get("device_id"), "device id"),
            sequence=cls._parse_sequence(message.get("sequence")),
            occurred_at=cls._parse_timestamp(message.get("occurred_at")),
            payload=payload,
            previous_hash=previous_hash,
            causation_id=causation_id,
            correlation_id=correlation_id,
            traceparent=cls._parse_string(message.get("traceparent"), "traceparent"),
        )._with_payload_hash(cls._parse_string(message.get("payload_hash"), "payload hash"))

    def _with_payload_hash(self, payload_hash: str) -> V2Event:
        """Проверить полученный hash, не подменяя расчётное значение."""
        return dataclasses.replace(self, payload_hash=payload_hash)

    @staticmethod
    def calculate_payload_hash(payload: dict[str, Any]) -> str:
        """Hash a JSON object in its canonical V2 representation."""
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    @staticmethod
    def _is_sha256(value: str | None) -> bool:
        if value is None or len(value) != 64:
            return False
        try:
            int(value, 16)
        except ValueError:
            return False
        return True

    @staticmethod
    def _is_traceparent(value: str | None) -> bool:
        return (
            value is not None
            and re.fullmatch(r"00-[0-9a-f]{32}-[0-9a-f]{16}-[0-9a-f]{2}", value) is not None
        )

    @staticmethod
    def new_traceparent() -> str:
        """Создать совместимый W3C trace context для нового корневого факта."""
        return f"00-{uuid.uuid4().hex}-{uuid.uuid4().hex[:16]}-01"

    @staticmethod
    def _parse_uuid(value: object, field_name: str) -> uuid.UUID:
        if not isinstance(value, str):
            raise ValueError(f"V2 transport {field_name} must be a UUID string")
        try:
            return uuid.UUID(value)
        except ValueError as error:
            raise ValueError(f"V2 transport {field_name} is invalid") from error

    @classmethod
    def _parse_optional_uuid(cls, value: object, field_name: str) -> uuid.UUID | None:
        if value is None:
            return None
        return cls._parse_uuid(value, field_name)

    @staticmethod
    def _parse_event_type(value: object) -> V2EventType:
        if not isinstance(value, str):
            raise ValueError("V2 transport event type must be a string")
        try:
            return V2EventType(value)
        except ValueError as error:
            raise ValueError("V2 transport event type is invalid") from error

    @staticmethod
    def _parse_string(value: object, field_name: str) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"V2 transport {field_name} is required")
        return value

    @staticmethod
    def _parse_sequence(value: object) -> int:
        if not isinstance(value, int) or isinstance(value, bool):
            raise ValueError("V2 transport sequence must be an integer")
        return value

    @staticmethod
    def _parse_timestamp(value: object) -> datetime.datetime:
        if not isinstance(value, str):
            raise ValueError("V2 transport occurred at must be an ISO timestamp")
        try:
            timestamp = datetime.datetime.fromisoformat(value)
        except ValueError as error:
            raise ValueError("V2 transport occurred at is invalid") from error
        if timestamp.tzinfo is None:
            raise ValueError("V2 transport occurred at must include timezone")
        return timestamp

    @staticmethod
    def _parse_payload(payload_json: str) -> dict[str, Any]:
        try:
            payload = json.loads(payload_json)
        except json.JSONDecodeError as error:
            raise ValueError("V2 event payload must be valid JSON") from error
        if not isinstance(payload, dict):
            raise ValueError("V2 event payload must be a JSON object")
        return payload


@dataclasses.dataclass(frozen=True)
class V2InboxResult:
    """Stable result returned for an accepted, duplicated or conflicting event."""

    status: V2InboxStatus
    event_id: uuid.UUID
    operation_id: uuid.UUID
    message: str


@dataclasses.dataclass(frozen=True)
class V2SessionChain:
    """Последняя подтверждённая точка цепочки одного client/session/device."""

    client_id: uuid.UUID
    session_id: uuid.UUID
    device_id: str
    producer_id: str
    last_sequence: int = 0
    last_payload_hash: str | None = None

    def accept(self, event: V2Event) -> tuple[V2SessionChainStatus, V2SessionChain | None]:
        """Не принимать пропуск или смену владельца цепочки как обычный факт."""
        if (
            event.client_id != self.client_id
            or event.session_id != self.session_id
            or event.device_id != self.device_id
            or event.producer_id != self.producer_id
        ):
            return V2SessionChainStatus.CONFLICT, None
        if event.sequence != self.last_sequence + 1:
            return V2SessionChainStatus.GAP, None
        if event.previous_hash != self.last_payload_hash:
            return V2SessionChainStatus.CONFLICT, None
        return (
            V2SessionChainStatus.ACCEPTED,
            dataclasses.replace(
                self,
                last_sequence=event.sequence,
                last_payload_hash=event.payload_hash,
            ),
        )

    @classmethod
    def from_first_event(cls, event: V2Event) -> V2SessionChain:
        """Начать цепочку можно только с первого факта без previous hash."""
        if event.sequence != 1 or event.previous_hash is not None:
            raise ValueError("V2 session chain must begin from sequence one")
        return cls(
            client_id=event.client_id,
            session_id=event.session_id,
            device_id=event.device_id,
            producer_id=event.producer_id,
            last_sequence=event.sequence,
            last_payload_hash=event.payload_hash,
        )


@dataclasses.dataclass(frozen=True)
class V2OutgoingServerEvent:
    """Подтверждённое серверное сообщение, ожидающее отправки в Kafka."""

    event: V2Event
    topic: str
    partition_key: str
    created_at: datetime.datetime
    status: V2OutgoingEventStatus = V2OutgoingEventStatus.PENDING
    attempts: int = 0
    last_error: str | None = None
    published_at: datetime.datetime | None = None

    def __post_init__(self) -> None:
        if not self.topic.strip():
            raise ValueError("V2 outgoing event topic is required")
        if not self.partition_key.strip():
            raise ValueError("V2 outgoing event partition key is required")
        if self.created_at.tzinfo is None:
            raise ValueError("V2 outgoing event timestamp must include timezone")
        if self.attempts < 0:
            raise ValueError("V2 outgoing event attempts cannot be negative")
        if self.status in {
            V2OutgoingEventStatus.PUBLISHED,
            V2OutgoingEventStatus.ACKNOWLEDGED,
        } and self.published_at is None:
            raise ValueError("Published V2 outgoing event requires timestamp")
        if self.status is V2OutgoingEventStatus.PENDING and self.published_at is not None:
            raise ValueError("Pending V2 outgoing event cannot have published timestamp")

    def record_publish_failure(self, error: str) -> V2OutgoingServerEvent:
        """Сохранить ошибку отправки, оставив запись доступной для следующей попытки."""
        if self.status is not V2OutgoingEventStatus.PENDING:
            return self
        return dataclasses.replace(
            self,
            attempts=self.attempts + 1,
            last_error=error[:2_000],
        )

    def record_published(self, published_at: datetime.datetime) -> V2OutgoingServerEvent:
        """Отметить запись отправленной только после подтверждения Kafka."""
        if published_at.tzinfo is None:
            raise ValueError("V2 outgoing published timestamp must include timezone")
        return dataclasses.replace(
            self,
            status=V2OutgoingEventStatus.PUBLISHED,
            published_at=published_at,
            last_error=None,
        )

    def record_acknowledged(self) -> V2OutgoingServerEvent:
        """Зафиксировать применение события конкретным V2-клиентом."""
        if self.status is V2OutgoingEventStatus.ACKNOWLEDGED:
            return self
        if self.status is not V2OutgoingEventStatus.PUBLISHED:
            raise ValueError("Only published V2 outgoing events can be acknowledged")
        return dataclasses.replace(
            self,
            status=V2OutgoingEventStatus.ACKNOWLEDGED,
        )


def event_to_transport_payload(event: V2Event) -> dict[str, object]:
    """Сериализовать весь V2-конверт, не меняя его идентификаторы и payload."""
    return {
        "event_id": str(event.event_id),
        "operation_id": str(event.operation_id),
        "event_type": event.event_type.value,
        "schema_version": event.schema_version,
        "producer_id": event.producer_id,
        "client_id": str(event.client_id),
        "session_id": str(event.session_id),
        "device_id": event.device_id,
        "sequence": event.sequence,
        "occurred_at": event.occurred_at.isoformat(),
        "causation_id": str(event.causation_id) if event.causation_id else None,
        "correlation_id": str(event.correlation_id),
        "traceparent": event.traceparent,
        "payload_hash": event.payload_hash,
        "previous_hash": event.previous_hash,
        "payload": json.loads(event.payload_json),
    }
