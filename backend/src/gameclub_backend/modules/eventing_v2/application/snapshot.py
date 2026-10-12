"""Сборка подписываемого V2 offline snapshot из server-owned данных."""

from __future__ import annotations

import dataclasses
import datetime
import uuid

from google.protobuf.timestamp_pb2 import Timestamp

from gameclub.v2 import offline_session_snapshot_pb2
from gameclub_backend.modules.catalog.domain import (
    BillingMode,
    Tariff,
    TariffLifecycle,
    TariffSaleChannel,
)
from gameclub_backend.modules.clients.domain import Client
from gameclub_backend.modules.entitlements.domain import Entitlement, EntitlementStatus
from gameclub_backend.modules.sessions.domain import Session, SessionStatus


@dataclasses.dataclass(frozen=True)
class V2OfflineSnapshotInput:
    snapshot_id: uuid.UUID
    snapshot_version: int
    issued_at: datetime.datetime
    client: Client
    session: Session
    device_id: str
    workstation_zone_id: str | None
    debt_limit_cents: int
    login_grant_remaining_minutes: int
    entitlements: tuple[Entitlement, ...]
    tariffs: tuple[Tariff, ...]
    policy_version: str

    def __post_init__(self) -> None:
        if self.snapshot_version < 1:
            raise ValueError("V2 snapshot version must be positive")
        if self.issued_at.tzinfo is None:
            raise ValueError("V2 snapshot timestamp must include timezone")
        if self.session.status is not SessionStatus.ACTIVE:
            raise ValueError("V2 snapshot requires an active session")
        if self.session.client_id != self.client.id:
            raise ValueError("V2 snapshot session does not belong to client")
        if not self.device_id.strip() or not self.policy_version.strip():
            raise ValueError("V2 snapshot device and policy version are required")
        if self.debt_limit_cents < 0 or self.login_grant_remaining_minutes < 0:
            raise ValueError("V2 snapshot debt limit or login grant is invalid")


class V2OfflineSnapshotFactory:
    """Не подписывает сам: приватный ключ остаётся за отдельным signer port."""

    @staticmethod
    def create_payload(
        value: V2OfflineSnapshotInput,
    ) -> offline_session_snapshot_pb2.OfflineSessionSnapshotPayload:
        payload = offline_session_snapshot_pb2.OfflineSessionSnapshotPayload(
            snapshot_id=str(value.snapshot_id),
            schema_version=1,
            snapshot_version=value.snapshot_version,
            issued_at=V2OfflineSnapshotFactory._timestamp(value.issued_at),
            client_id=str(value.client.id),
            session_id=str(value.session.id),
            device_id=value.device_id.strip(),
            balance_cents=value.client.balance_cents,
            debt_limit_cents=value.debt_limit_cents,
            login_grant_remaining_minutes=value.login_grant_remaining_minutes,
            policy_version=value.policy_version.strip(),
        )
        if value.workstation_zone_id and value.workstation_zone_id.strip():
            payload.workstation_zone_id = value.workstation_zone_id.strip()
        payload.packages.extend(
            V2OfflineSnapshotFactory._package(item) for item in value.entitlements
        )
        payload.tariffs.extend(V2OfflineSnapshotFactory._tariff(item) for item in value.tariffs)
        return payload

    @staticmethod
    def _timestamp(value: datetime.datetime) -> Timestamp:
        result = Timestamp()
        result.FromDatetime(value)
        return result

    @staticmethod
    def _package(value: Entitlement) -> offline_session_snapshot_pb2.OfflinePackageSnapshot:
        status = {
            EntitlementStatus.ACTIVE: offline_session_snapshot_pb2.OFFLINE_PACKAGE_STATUS_ACTIVE,
            EntitlementStatus.QUEUED: offline_session_snapshot_pb2.OFFLINE_PACKAGE_STATUS_QUEUED,
            EntitlementStatus.EXHAUSTED: (
                offline_session_snapshot_pb2.OFFLINE_PACKAGE_STATUS_EXHAUSTED
            ),
            EntitlementStatus.BURNED: offline_session_snapshot_pb2.OFFLINE_PACKAGE_STATUS_BURNED,
        }[value.status]
        result = offline_session_snapshot_pb2.OfflinePackageSnapshot(
            package_id=str(value.id),
            tariff_id=str(value.tariff_id),
            remaining_minutes=value.remaining_minutes,
            status=status,
        )
        if value.zone_id:
            result.zone_id = value.zone_id
        return result

    @staticmethod
    def _tariff(value: Tariff) -> offline_session_snapshot_pb2.OfflineTariffSnapshot:
        result = offline_session_snapshot_pb2.OfflineTariffSnapshot(
            tariff_id=str(value.id),
            name=value.name,
            package_minutes=value.duration_minutes,
            package_price_cents=value.price_cents,
            per_minute_price_cents=(
                value.price_per_minute_cents if value.billing_mode is BillingMode.PER_MINUTE else 0
            ),
            is_purchasable=(
                value.active
                and value.lifecycle is TariffLifecycle.PUBLISHED
                and value.billing_mode is BillingMode.BLOCK
                and value.is_sellable_through(TariffSaleChannel.SELF_SERVICE)
            ),
        )
        if value.group_id:
            result.zone_id = value.group_id
        if value.usage_window_start_minute is not None:
            result.usage_window_start_minute = value.usage_window_start_minute
            result.usage_window_end_minute = value.usage_window_end_minute
            result.window_timezone = value.window_timezone
        return result
