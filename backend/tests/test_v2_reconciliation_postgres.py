import asyncio
import dataclasses
import datetime
import os
import uuid

import pytest
from aiokafka import AIOKafkaProducer
from google.protobuf.timestamp_pb2 import Timestamp
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from gameclub.v2 import offline_session_snapshot_pb2
from gameclub_backend.jobs.reports import project_analytics_events
from gameclub_backend.modules.clients.domain import Client
from gameclub_backend.modules.clients.infrastructure.postgres import PostgresClientRepository
from gameclub_backend.modules.eventing_v2.application.deposit import (
    V2DepositCreditCommand,
    V2DepositCreditService,
)
from gameclub_backend.modules.eventing_v2.application.lease import (
    V2SessionLease,
    V2SessionLeaseService,
)
from gameclub_backend.modules.eventing_v2.application.reconciliation import (
    V2ClientFactReconciliationService,
    V2ClientFactStatus,
)
from gameclub_backend.modules.eventing_v2.application.service import V2InboxService
from gameclub_backend.modules.eventing_v2.application.snapshot_issue import (
    V2SignedSnapshotIssue,
    V2SnapshotIssueService,
)
from gameclub_backend.modules.eventing_v2.domain import V2Event, V2EventType, V2InboxStatus
from gameclub_backend.modules.eventing_v2.infrastructure.deposit_postgres import (
    PostgresV2DepositCreditRepository,
)
from gameclub_backend.modules.eventing_v2.infrastructure.lease_postgres import (
    PostgresV2SessionLeaseRepository,
)
from gameclub_backend.modules.eventing_v2.infrastructure.postgres import PostgresV2InboxRepository
from gameclub_backend.modules.eventing_v2.infrastructure.protobuf import event_to_protobuf
from gameclub_backend.modules.eventing_v2.infrastructure.reconciliation_postgres import (
    PostgresV2ClientFactReconciliationRepository,
)
from gameclub_backend.modules.eventing_v2.infrastructure.snapshot_ed25519 import (
    V2Ed25519SnapshotSigner,
)
from gameclub_backend.modules.eventing_v2.infrastructure.snapshot_issue_postgres import (
    PostgresV2SnapshotIssueRepository,
)
from gameclub_backend.modules.eventing_v2.infrastructure.snapshot_protobuf import (
    sign_offline_session_snapshot,
)
from gameclub_backend.modules.payment_methods.domain import PaymentPart
from gameclub_backend.modules.sessions.domain import Session, SessionStatus
from gameclub_backend.modules.sessions.infrastructure.postgres import (
    PostgresSessionTransactionWriter,
)

pytestmark = [pytest.mark.integration, pytest.mark.postgres, pytest.mark.concurrency]


@pytest.fixture
def postgres_dsn() -> str:
    dsn = os.getenv("GAMECLUB_TEST_POSTGRES_DSN")
    if not dsn:
        pytest.skip("Set GAMECLUB_TEST_POSTGRES_DSN to run V2 PostgreSQL tests")
    return dsn


def make_event(
    *,
    client_id: uuid.UUID,
    session_id: uuid.UUID,
    operation_id: uuid.UUID | None = None,
    sequence: int = 1,
    previous_hash: str | None = None,
    snapshot_id: uuid.UUID,
    snapshot_version: int = 1,
) -> V2Event:
    return V2Event.create(
        operation_id=operation_id or uuid.uuid4(),
        event_type=V2EventType.PER_MINUTE_DEBIT,
        producer_id="workstation:v2-postgres-test",
        client_id=client_id,
        session_id=session_id,
        device_id="v2-postgres-test-device",
        sequence=sequence,
        occurred_at=datetime.datetime.now(datetime.UTC),
        payload={
            "amount_cents": 100,
            "tariff_id": "per-minute-test",
            "snapshot_id": str(snapshot_id),
            "snapshot_version": snapshot_version,
        },
        previous_hash=previous_hash,
    )


@pytest.mark.asyncio
async def test_postgres_v2_reconciliation_is_atomic_and_inbox_fans_out(
    postgres_dsn: str,
) -> None:
    engine = create_async_engine(postgres_dsn, pool_pre_ping=True)
    client_id = uuid.uuid4()
    session_id = uuid.uuid4()
    snapshot_id = uuid.uuid4()
    first = make_event(client_id=client_id, session_id=session_id, snapshot_id=snapshot_id)
    second = make_event(
        client_id=client_id,
        session_id=session_id,
        sequence=2,
        previous_hash=first.payload_hash,
        snapshot_id=snapshot_id,
    )
    operation_ids = (first.operation_id, second.operation_id)
    try:
        now = datetime.datetime.now(datetime.UTC)
        async with engine.begin() as connection:
            await connection.execute(
                text("""
                    INSERT INTO v2_session_leases (
                        session_id, client_id, device_id, snapshot_id, snapshot_version,
                        policy_version, status, issued_at, expires_at, revoked_at
                    ) VALUES (
                        :session_id, :client_id, :device_id, :snapshot_id, 1,
                        'test-policy', 'active', :issued_at, :expires_at, NULL
                    )
                """),
                {
                    "session_id": session_id,
                    "client_id": client_id,
                    "device_id": first.device_id,
                    "snapshot_id": snapshot_id,
                    "issued_at": now,
                    "expires_at": None,
                },
            )
        service = V2ClientFactReconciliationService(
            PostgresV2ClientFactReconciliationRepository(lambda: engine)
        )

        wrong_snapshot = await service.accept(
            make_event(
                client_id=client_id,
                session_id=session_id,
                snapshot_id=uuid.uuid4(),
            )
        )
        old_debit_field = await service.accept(
            V2Event.create(
                operation_id=uuid.uuid4(),
                event_type=V2EventType.PER_MINUTE_DEBIT,
                producer_id=first.producer_id,
                client_id=client_id,
                session_id=session_id,
                device_id=first.device_id,
                sequence=1,
                occurred_at=datetime.datetime.now(datetime.UTC),
                payload={
                    "debit_delta_cents": 100,
                    "tariff_id": "per-minute-test",
                    "snapshot_id": str(snapshot_id),
                    "snapshot_version": 1,
                },
            )
        )
        accepted = await service.accept(first)
        duplicate = await service.accept(first)
        accepted_next = await service.accept(second)
        analytics = await V2InboxService(
            PostgresV2InboxRepository(lambda: engine),
            "analytics_projection",
        ).accept(first)

        assert wrong_snapshot.status is V2ClientFactStatus.CONFLICT
        assert "Snapshot" in wrong_snapshot.message
        assert old_debit_field.status is V2ClientFactStatus.CONFLICT
        assert "Payload" in old_debit_field.message
        assert accepted.status is V2ClientFactStatus.ACCEPTED
        assert accepted.result_event_id is not None
        assert duplicate.status is V2ClientFactStatus.DUPLICATE
        assert accepted_next.status is V2ClientFactStatus.ACCEPTED
        assert analytics.status is V2InboxStatus.ACCEPTED

        async with engine.connect() as connection:
            counts = (
                (
                    await connection.execute(
                        text("""
                    SELECT
                        (SELECT count(*) FROM v2_event_inbox
                         WHERE session_id = :session_id) AS inbox_rows,
                        (SELECT count(*) FROM v2_confirmed_client_facts
                         WHERE session_id = :session_id) AS confirmed_rows,
                        (SELECT count(*) FROM v2_server_outbox
                         WHERE operation_id = ANY(:operation_ids)) AS outbox_rows,
                        (SELECT count(*) FROM audit_events
                         WHERE request_id = ANY(:request_ids)) AS audit_rows,
                        (SELECT last_sequence FROM v2_session_chains
                         WHERE session_id = :session_id) AS last_sequence
                """),
                        {
                            "session_id": session_id,
                            "operation_ids": list(operation_ids),
                            "request_ids": [str(value) for value in operation_ids],
                        },
                    )
                )
                .mappings()
                .one()
            )

        assert dict(counts) == {
            "inbox_rows": 3,
            "confirmed_rows": 2,
            "outbox_rows": 4,
            "audit_rows": 2,
            "last_sequence": 2,
        }
    finally:
        async with engine.begin() as connection:
            await connection.execute(
                text("DELETE FROM audit_events WHERE request_id = ANY(:request_ids)"),
                {"request_ids": [str(value) for value in operation_ids]},
            )
            await connection.execute(
                text("DELETE FROM v2_server_outbox WHERE operation_id = ANY(:operation_ids)"),
                {"operation_ids": list(operation_ids)},
            )
            await connection.execute(
                text("DELETE FROM v2_confirmed_client_facts WHERE session_id = :session_id"),
                {"session_id": session_id},
            )
            await connection.execute(
                text("DELETE FROM v2_event_inbox WHERE session_id = :session_id"),
                {"session_id": session_id},
            )
            await connection.execute(
                text("DELETE FROM v2_session_chains WHERE session_id = :session_id"),
                {"session_id": session_id},
            )
            await connection.execute(
                text("DELETE FROM v2_session_leases WHERE session_id = :session_id"),
                {"session_id": session_id},
            )
        await engine.dispose()


@pytest.mark.asyncio
async def test_faststream_client_facts_worker_reconciles_kafka_event(
    postgres_dsn: str,
) -> None:
    """Проверяет реальный путь Kafka → worker → PostgreSQL без server minute tick."""

    kafka_bootstrap_servers = os.getenv("GAMECLUB_TEST_KAFKA_BOOTSTRAP_SERVERS")
    redis_url = os.getenv("GAMECLUB_REDIS_URL")
    if not kafka_bootstrap_servers or not redis_url:
        pytest.skip("Set Kafka and Redis settings for V2 Kafka worker test")
    engine = create_async_engine(postgres_dsn, pool_pre_ping=True)
    client_id = uuid.uuid4()
    session_id = uuid.uuid4()
    snapshot_id = uuid.uuid4()
    event = make_event(client_id=client_id, session_id=session_id, snapshot_id=snapshot_id)
    producer = AIOKafkaProducer(bootstrap_servers=kafka_bootstrap_servers, acks="all")
    try:
        now = datetime.datetime.now(datetime.UTC)
        async with engine.begin() as connection:
            await connection.execute(
                text("""
                    INSERT INTO v2_session_leases (
                        session_id, client_id, device_id, snapshot_id, snapshot_version,
                        policy_version, status, issued_at, expires_at, revoked_at
                    ) VALUES (
                        :session_id, :client_id, :device_id, :snapshot_id, 1,
                        'kafka-worker-test', 'active', :issued_at, NULL, NULL
                    )
                """),
                {
                    "session_id": session_id,
                    "client_id": client_id,
                    "device_id": event.device_id,
                    "snapshot_id": snapshot_id,
                    "issued_at": now,
                },
            )
        await producer.start()
        await producer.send_and_wait(
            "v2.client-events",
            event_to_protobuf(event).SerializeToString(),
            key=f"{client_id}:{session_id}".encode(),
        )

        accepted = False
        analytics_received = False
        for _ in range(50):
            async with engine.connect() as connection:
                confirmed = await connection.scalar(
                    text("""
                        SELECT count(*) FROM v2_confirmed_client_facts
                        WHERE event_id = :event_id
                    """),
                    {"event_id": event.event_id},
                )
                analytics_outbox = await connection.scalar(
                    text(
                        """
                        SELECT count(*) FROM analytics_outbox_events
                        WHERE aggregate_type = 'v2_per_minute_debit'
                          AND aggregate_id = :aggregate_id
                        """
                    ),
                    {"aggregate_id": str(event.operation_id)},
                )
            if confirmed == 1:
                accepted = True
            if analytics_outbox == 1:
                analytics_received = True
            if accepted and analytics_received:
                break
            await asyncio.sleep(0.1)

        assert accepted, "V2 FastStream worker did not reconcile the Kafka fact in time"
        assert analytics_received, "Confirmed V2 debit did not reach the analytics worker in time"

        project_analytics_events.send()
        projected = False
        for _ in range(50):
            async with engine.connect() as connection:
                projection_count = await connection.scalar(
                    text(
                        """
                        SELECT count(*)
                        FROM analytics_projection_events
                        WHERE event_id IN (
                            SELECT id FROM analytics_outbox_events
                            WHERE aggregate_type = 'v2_per_minute_debit'
                              AND aggregate_id = :aggregate_id
                        )
                        """
                    ),
                    {"aggregate_id": str(event.operation_id)},
                )
            if projection_count == 1:
                projected = True
                break
            await asyncio.sleep(0.1)
        assert projected, "Analytics projection worker did not apply the confirmed V2 debit in time"

        async with engine.connect() as connection:
            inbox_rows = await connection.scalar(
                text("""
                    SELECT count(*) FROM v2_event_inbox
                    WHERE consumer_name = 'client_session_facts' AND event_id = :event_id
                """),
                {"event_id": event.event_id},
            )
            audit_rows = await connection.scalar(
                text("SELECT count(*) FROM audit_events WHERE request_id = :request_id"),
                {"request_id": str(event.operation_id)},
            )
        assert inbox_rows == 1
        assert audit_rows == 1
    finally:
        await producer.stop()
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    """
                    DELETE FROM analytics_projection_events
                    WHERE event_id IN (
                        SELECT id FROM analytics_outbox_events
                        WHERE aggregate_type = 'v2_per_minute_debit'
                          AND aggregate_id = :aggregate_id
                    )
                    """
                ),
                {"aggregate_id": str(event.operation_id)},
            )
            await connection.execute(
                text(
                    """
                    DELETE FROM analytics_outbox_events
                    WHERE aggregate_type = 'v2_per_minute_debit'
                      AND aggregate_id = :aggregate_id
                    """
                ),
                {"aggregate_id": str(event.operation_id)},
            )
            await connection.execute(
                text("DELETE FROM audit_events WHERE request_id = :request_id"),
                {"request_id": str(event.operation_id)},
            )
            await connection.execute(
                text("DELETE FROM v2_server_outbox WHERE operation_id = :operation_id"),
                {"operation_id": event.operation_id},
            )
            await connection.execute(
                text("DELETE FROM v2_confirmed_client_facts WHERE event_id = :event_id"),
                {"event_id": event.event_id},
            )
            await connection.execute(
                text(
                    """
                    DELETE FROM v2_event_inbox
                    WHERE event_id = :event_id
                       OR (producer_id = 'server:reconciliation' AND operation_id = :operation_id)
                    """
                ),
                {"event_id": event.event_id, "operation_id": event.operation_id},
            )
            await connection.execute(
                text("DELETE FROM v2_session_chains WHERE session_id = :session_id"),
                {"session_id": session_id},
            )
            await connection.execute(
                text("DELETE FROM v2_session_leases WHERE session_id = :session_id"),
                {"session_id": session_id},
            )
        await engine.dispose()


@pytest.mark.asyncio
async def test_postgres_v2_deposit_requires_matching_active_lease(postgres_dsn: str) -> None:
    engine = create_async_engine(postgres_dsn, pool_pre_ping=True)
    now = datetime.datetime.now(datetime.UTC)
    client_id = uuid.uuid4()
    session_id = uuid.uuid4()
    operation_id = uuid.uuid4()
    try:
        await PostgresClientRepository(lambda: engine).save(
            Client(
                id=client_id,
                nickname=f"V2LeaseDeposit{client_id.hex[:10]}",
                phone=None,
                discount_category=None,
                balance_cents=0,
                balance_bonus=0,
                created_at=now,
                updated_at=now,
            )
        )
        command = V2DepositCreditCommand(
            payment_operation_id=operation_id,
            client_id=client_id,
            session_id=session_id,
            device_id="v2-deposit-test-device",
            amount_delta_cents=500,
            currency="RUB",
            reason="V2 lease deposit test",
            actor_id="integration-test",
            payment_parts=(PaymentPart("transfer", 500),),
        )
        service = V2DepositCreditService(PostgresV2DepositCreditRepository(lambda: engine))

        with pytest.raises(ValueError, match="active V2 lease"):
            await service.apply(command)

        async with engine.begin() as connection:
            await connection.execute(
                text("""
                    INSERT INTO v2_session_leases (
                        session_id, client_id, device_id, snapshot_id, snapshot_version,
                        policy_version, status, issued_at, expires_at, revoked_at
                    ) VALUES (
                        :session_id, :client_id, :device_id, :snapshot_id, 1,
                        'test-policy', 'active', :issued_at, :expires_at, NULL
                    )
                """),
                {
                    "session_id": session_id,
                    "client_id": client_id,
                    "device_id": command.device_id,
                    "snapshot_id": uuid.uuid4(),
                    "issued_at": now,
                    "expires_at": now + datetime.timedelta(hours=1),
                },
            )

        accepted = await service.apply(command)
        duplicate = await service.apply(command)

        assert not accepted.is_duplicate
        assert duplicate.is_duplicate
        async with engine.connect() as connection:
            counts = (
                (
                    await connection.execute(
                        text("""
                    SELECT
                        (SELECT balance_cents FROM clients WHERE id = :client_id) AS balance_cents,
                        (SELECT count(*) FROM balance_operations
                         WHERE client_id = :client_id) AS ledger_rows,
                        (SELECT count(*) FROM v2_deposit_credits
                         WHERE payment_operation_id = :operation_id) AS deposit_rows,
                        (SELECT count(*) FROM v2_server_outbox
                         WHERE operation_id = :operation_id) AS outbox_rows
                """),
                        {"client_id": client_id, "operation_id": operation_id},
                    )
                )
                .mappings()
                .one()
            )
        assert dict(counts) == {
            "balance_cents": 500,
            "ledger_rows": 1,
            "deposit_rows": 1,
            "outbox_rows": 2,
        }
    finally:
        async with engine.begin() as connection:
            await connection.execute(
                text("DELETE FROM audit_events WHERE request_id = :request_id"),
                {"request_id": str(operation_id)},
            )
            await connection.execute(
                text("DELETE FROM v2_server_outbox WHERE operation_id = :operation_id"),
                {"operation_id": operation_id},
            )
            await connection.execute(
                text("DELETE FROM v2_deposit_credits WHERE payment_operation_id = :operation_id"),
                {"operation_id": operation_id},
            )
            await connection.execute(
                text("DELETE FROM balance_operations WHERE client_id = :client_id"),
                {"client_id": client_id},
            )
            await connection.execute(
                text("DELETE FROM v2_session_leases WHERE session_id = :session_id"),
                {"session_id": session_id},
            )
            await connection.execute(
                text("DELETE FROM clients WHERE id = :client_id"),
                {"client_id": client_id},
            )
        await engine.dispose()


@pytest.mark.asyncio
async def test_postgres_v2_lease_issuer_is_exclusive_and_idempotent(postgres_dsn: str) -> None:
    engine = create_async_engine(postgres_dsn, pool_pre_ping=True)
    now = datetime.datetime.now(datetime.UTC)
    lease = V2SessionLease(
        session_id=uuid.uuid4(),
        client_id=uuid.uuid4(),
        device_id="v2-lease-issuer-device",
        snapshot_id=uuid.uuid4(),
        snapshot_version=1,
        policy_version="test-policy",
        issued_at=now,
    )
    try:
        service = V2SessionLeaseService(PostgresV2SessionLeaseRepository(lambda: engine))
        issued, duplicate = await service.issue(lease)
        repeated, repeated_duplicate = await service.issue(lease)

        assert issued == lease
        assert not duplicate
        assert repeated == lease
        assert repeated_duplicate
        with pytest.raises(ValueError, match="active V2 lease"):
            await service.issue(
                V2SessionLease(
                    session_id=uuid.uuid4(),
                    client_id=uuid.uuid4(),
                    device_id=lease.device_id,
                    snapshot_id=uuid.uuid4(),
                    snapshot_version=1,
                    policy_version="test-policy",
                    issued_at=now,
                )
            )
        with pytest.raises(ValueError, match="active V2 lease"):
            await service.issue(
                V2SessionLease(
                    session_id=uuid.uuid4(),
                    client_id=lease.client_id,
                    device_id="v2-lease-other-device",
                    snapshot_id=uuid.uuid4(),
                    snapshot_version=1,
                    policy_version="test-policy",
                    issued_at=now,
                )
            )
    finally:
        async with engine.begin() as connection:
            await connection.execute(
                text("DELETE FROM v2_session_leases WHERE session_id = :session_id"),
                {"session_id": lease.session_id},
            )
        await engine.dispose()


@pytest.mark.asyncio
async def test_postgres_v2_snapshot_issue_persists_exact_snapshot_lease_and_outbox(
    postgres_dsn: str,
) -> None:
    engine = create_async_engine(postgres_dsn, pool_pre_ping=True)
    now = datetime.datetime.now(datetime.UTC)
    lease = V2SessionLease(
        session_id=uuid.uuid4(),
        client_id=uuid.uuid4(),
        device_id="v2-snapshot-issue-device",
        snapshot_id=uuid.uuid4(),
        snapshot_version=1,
        policy_version="test-policy",
        issued_at=now,
    )
    payload = offline_session_snapshot_pb2.OfflineSessionSnapshotPayload(
        snapshot_id=str(lease.snapshot_id),
        schema_version=1,
        snapshot_version=lease.snapshot_version,
        client_id=str(lease.client_id),
        session_id=str(lease.session_id),
        device_id=lease.device_id,
        balance_cents=1_000,
        debt_limit_cents=500,
        login_grant_remaining_minutes=5,
        policy_version=lease.policy_version,
    )
    issued_at = Timestamp()
    issued_at.FromDatetime(now)
    payload.issued_at.CopyFrom(issued_at)
    signed_snapshot = sign_offline_session_snapshot(
        payload,
        "test-key-2026-09",
        V2Ed25519SnapshotSigner("nWGxne/9WmC6hEr0kuwsxERJxWl7MmkZcDusAxyuf2A="),
    )
    try:
        service = V2SnapshotIssueService(PostgresV2SnapshotIssueRepository(lambda: engine))
        issue = V2SignedSnapshotIssue(lease=lease, signed_snapshot=signed_snapshot)

        accepted = await service.issue(issue)
        duplicate = await service.issue(issue)
        retry_lease = dataclasses.replace(lease, snapshot_id=uuid.uuid4())
        retry_payload = offline_session_snapshot_pb2.OfflineSessionSnapshotPayload()
        retry_payload.CopyFrom(payload)
        retry_payload.snapshot_id = str(retry_lease.snapshot_id)
        retry_snapshot = sign_offline_session_snapshot(
            retry_payload,
            "test-key-2026-09",
            V2Ed25519SnapshotSigner("nWGxne/9WmC6hEr0kuwsxERJxWl7MmkZcDusAxyuf2A="),
        )
        recovered = await service.issue(
            V2SignedSnapshotIssue(lease=retry_lease, signed_snapshot=retry_snapshot)
        )

        assert not accepted.is_duplicate
        assert accepted.login_event_id == lease.snapshot_id
        assert duplicate.is_duplicate
        assert duplicate.signed_snapshot.SerializeToString(deterministic=True) == (
            signed_snapshot.SerializeToString(deterministic=True)
        )
        assert recovered.is_duplicate
        assert recovered.signed_snapshot.SerializeToString(deterministic=True) == (
            signed_snapshot.SerializeToString(deterministic=True)
        )
        async with engine.connect() as connection:
            counts = (
                (
                    await connection.execute(
                        text("""
                    SELECT
                        (SELECT count(*) FROM v2_session_leases
                         WHERE session_id = :session_id
                           AND signing_key_id = :signing_key_id
                           AND snapshot_payload IS NOT NULL
                           AND snapshot_signature IS NOT NULL
                           AND snapshot_payload_hash IS NOT NULL) AS lease_rows,
                        (SELECT count(*) FROM v2_server_outbox
                         WHERE event_id = :snapshot_id
                           AND event_type = 'login_snapshot_issued') AS outbox_rows,
                        (SELECT count(*) FROM audit_events
                         WHERE request_id = :request_id) AS audit_rows
                """),
                        {
                            "session_id": lease.session_id,
                            "signing_key_id": "test-key-2026-09",
                            "snapshot_id": lease.snapshot_id,
                            "request_id": str(lease.snapshot_id),
                        },
                    )
                )
                .mappings()
                .one()
            )
        assert dict(counts) == {"lease_rows": 1, "outbox_rows": 1, "audit_rows": 1}
    finally:
        async with engine.begin() as connection:
            await connection.execute(
                text("DELETE FROM audit_events WHERE request_id = :request_id"),
                {"request_id": str(lease.snapshot_id)},
            )
            await connection.execute(
                text("DELETE FROM v2_server_outbox WHERE event_id = :snapshot_id"),
                {"snapshot_id": lease.snapshot_id},
            )
            await connection.execute(
                text("DELETE FROM v2_session_leases WHERE session_id = :session_id"),
                {"session_id": lease.session_id},
            )
        await engine.dispose()


@pytest.mark.asyncio
async def test_postgres_v2_login_rolls_back_new_session_when_lease_cannot_be_issued(
    postgres_dsn: str,
) -> None:
    engine = create_async_engine(postgres_dsn, pool_pre_ping=True)
    now = datetime.datetime.now(datetime.UTC)
    client_id = uuid.uuid4()
    blocked_lease_session_id = uuid.uuid4()
    new_session_id = uuid.uuid4()
    lease = V2SessionLease(
        session_id=new_session_id,
        client_id=client_id,
        device_id="v2-atomic-login-device",
        snapshot_id=uuid.uuid4(),
        snapshot_version=1,
        policy_version="test-policy",
        issued_at=now,
    )
    session_to_start = Session(
        id=new_session_id,
        workstation_id=uuid.uuid4(),
        client_id=client_id,
        guest_name=None,
        status=SessionStatus.ACTIVE,
        started_at=now,
        ended_at=None,
        source="v2_local_ledger",
        created_by=f"client:{client_id}",
        created_at=now,
        idempotency_key="v2-atomic-login-rollback",
        login_grant_minutes=5,
    )
    payload = offline_session_snapshot_pb2.OfflineSessionSnapshotPayload(
        snapshot_id=str(lease.snapshot_id),
        schema_version=1,
        snapshot_version=lease.snapshot_version,
        client_id=str(client_id),
        session_id=str(new_session_id),
        device_id=lease.device_id,
        debt_limit_cents=0,
        policy_version=lease.policy_version,
    )
    issued_at = Timestamp()
    issued_at.FromDatetime(now)
    payload.issued_at.CopyFrom(issued_at)
    signed_snapshot = sign_offline_session_snapshot(
        payload,
        "test-key-2026-09",
        V2Ed25519SnapshotSigner("nWGxne/9WmC6hEr0kuwsxERJxWl7MmkZcDusAxyuf2A="),
    )
    try:
        async with engine.begin() as connection:
            await connection.execute(
                text("""
                    INSERT INTO v2_session_leases (
                        session_id, client_id, device_id, snapshot_id, snapshot_version,
                        policy_version, status, issued_at, expires_at, revoked_at
                    ) VALUES (
                        :session_id, :client_id, :device_id, :snapshot_id, 1,
                        'test-policy', 'active', :issued_at, NULL, NULL
                    )
                """),
                {
                    "session_id": blocked_lease_session_id,
                    "client_id": client_id,
                    "device_id": "another-device",
                    "snapshot_id": uuid.uuid4(),
                    "issued_at": now,
                },
            )
        service = V2SnapshotIssueService(
            PostgresV2SnapshotIssueRepository(
                lambda: engine,
                PostgresSessionTransactionWriter(),
            )
        )
        with pytest.raises(ValueError, match="active V2 lease"):
            await service.issue_with_new_session(
                V2SignedSnapshotIssue(lease=lease, signed_snapshot=signed_snapshot),
                session_to_start,
            )
        async with engine.connect() as connection:
            stored = await connection.scalar(
                text("SELECT count(*) FROM gaming_sessions WHERE id = :session_id"),
                {"session_id": new_session_id},
            )
        assert stored == 0
    finally:
        async with engine.begin() as connection:
            await connection.execute(
                text("DELETE FROM gaming_sessions WHERE id = :session_id"),
                {"session_id": new_session_id},
            )
            await connection.execute(
                text("DELETE FROM v2_session_leases WHERE session_id = :session_id"),
                {"session_id": blocked_lease_session_id},
            )
        await engine.dispose()
