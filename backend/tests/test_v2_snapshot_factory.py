import datetime
import uuid

import pytest

from gameclub_backend.modules.catalog.domain import BillingMode, Tariff
from gameclub_backend.modules.clients.domain import Client
from gameclub_backend.modules.entitlements.domain import Entitlement, EntitlementStatus
from gameclub_backend.modules.eventing_v2.application.snapshot import (
    V2OfflineSnapshotFactory,
    V2OfflineSnapshotInput,
)
from gameclub_backend.modules.eventing_v2.infrastructure.snapshot_protobuf import (
    serialize_snapshot_payload,
)
from gameclub_backend.modules.sessions.domain import Session, SessionStatus


def test_v2_snapshot_factory_uses_server_owned_client_session_and_tariff_snapshots() -> None:
    """Проверяет заявленное поведение backend."""
    now = datetime.datetime(2026, 9, 27, 18, tzinfo=datetime.UTC)
    client_id = uuid.UUID("00000000-0000-0000-0000-000000000401")
    session_id = uuid.UUID("00000000-0000-0000-0000-000000000402")
    tariff_id = uuid.UUID("00000000-0000-0000-0000-000000000403")
    client = Client(
        id=client_id,
        nickname="V2 Snapshot Client",
        phone=None,
        discount_category=None,
        balance_cents=1_200,
        balance_bonus=0,
        created_at=now,
        updated_at=now,
    )
    session = Session(
        id=session_id,
        workstation_id=uuid.UUID("00000000-0000-0000-0000-000000000404"),
        client_id=client_id,
        guest_name=None,
        status=SessionStatus.ACTIVE,
        started_at=now,
        ended_at=None,
        source="v2-test",
        created_by="operator:test",
        created_at=now,
        login_grant_minutes=5,
    )
    entitlement = Entitlement(
        id=uuid.UUID("00000000-0000-0000-0000-000000000405"),
        client_id=client_id,
        tariff_id=tariff_id,
        zone_id="vip",
        duration_minutes=60,
        remaining_minutes=45,
        price_cents=600,
        queue_position=1,
        status=EntitlementStatus.QUEUED,
        idempotency_key="v2-snapshot-package",
        purchased_at=now,
    )
    tariff = Tariff(
        id=tariff_id,
        name="VIP час",
        group_id="vip",
        duration_minutes=60,
        price_cents=600,
        valid_from=now,
        valid_to=None,
        active=True,
        billing_mode=BillingMode.BLOCK,
        price_per_minute_cents=20,
    )
    input_value = V2OfflineSnapshotInput(
        snapshot_id=uuid.UUID("00000000-0000-0000-0000-000000000406"),
        snapshot_version=1,
        issued_at=now,
        client=client,
        session=session,
        device_id="v2-snapshot-device",
        workstation_zone_id="vip",
        debt_limit_cents=500,
        login_grant_remaining_minutes=5,
        entitlements=(entitlement,),
        tariffs=(tariff,),
        policy_version="v2-test-policy",
    )

    payload = V2OfflineSnapshotFactory.create_payload(input_value)

    assert payload.client_id == str(client_id)
    assert payload.session_id == str(session_id)
    assert payload.balance_cents == 1_200
    assert payload.debt_limit_cents == 500
    assert payload.packages[0].remaining_minutes == 45
    assert payload.tariffs[0].is_purchasable
    assert serialize_snapshot_payload(payload) == serialize_snapshot_payload(
        V2OfflineSnapshotFactory.create_payload(input_value)
    )


def test_v2_snapshot_factory_rejects_negative_debt_limit() -> None:
    """Проверяет заявленное поведение backend."""
    now = datetime.datetime(2026, 9, 27, 18, tzinfo=datetime.UTC)
    client_id = uuid.UUID("00000000-0000-0000-0000-000000000501")
    client = Client(
        id=client_id,
        nickname="V2 Debt Limit Client",
        phone=None,
        discount_category=None,
        balance_cents=0,
        balance_bonus=0,
        created_at=now,
        updated_at=now,
    )
    session = Session(
        id=uuid.UUID("00000000-0000-0000-0000-000000000502"),
        workstation_id=uuid.UUID("00000000-0000-0000-0000-000000000503"),
        client_id=client_id,
        guest_name=None,
        status=SessionStatus.ACTIVE,
        started_at=now,
        ended_at=None,
        source="v2-test",
        created_by="operator:test",
        created_at=now,
    )
    with pytest.raises(ValueError, match="debt limit"):
        V2OfflineSnapshotInput(
            snapshot_id=uuid.UUID("00000000-0000-0000-0000-000000000504"),
            snapshot_version=1,
            issued_at=now,
            client=client,
            session=session,
            device_id="v2-snapshot-device",
            workstation_zone_id="vip",
            debt_limit_cents=-1,
            login_grant_remaining_minutes=5,
            entitlements=(),
            tariffs=(),
            policy_version="v2-test-policy",
        )
