import asyncio
import base64
import dataclasses
import datetime
import os
import uuid

import pytest
from aiokafka import AIOKafkaProducer
from google.protobuf.timestamp_pb2 import Timestamp
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from bonus_cleanup import clear_client_bonus_records
from gameclub.v2 import offline_session_snapshot_pb2
from gameclub_backend.jobs.reports import project_analytics_events
from gameclub_backend.modules.clients.domain import Client
from gameclub_backend.modules.clients.infrastructure.balance_transaction import (
    PostgresClientBalanceTransactionWriter,
)
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
from gameclub_backend.modules.sessions.application.service import SessionService
from gameclub_backend.modules.sessions.domain import Session, SessionStatus
from gameclub_backend.modules.sessions.infrastructure.postgres import (
    PostgresSessionRepository,
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
    occurred_at: datetime.datetime | None = None,
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
        occurred_at=occurred_at or datetime.datetime.now(datetime.UTC),
        payload={
            "amount_cents": 100,
            "tariff_id": "per-minute-test",
            "snapshot_id": str(snapshot_id),
            "snapshot_version": snapshot_version,
        },
        previous_hash=previous_hash,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(("starting_balance", "debt_limit"), [(500, 0), (-500, 800)])
async def test_postgres_v2_reconciliation_is_atomic_and_inbox_fans_out(
    postgres_dsn: str,
    starting_balance: int,
    debt_limit: int,
) -> None:
    """Проверяет заявленное поведение backend."""
    engine = create_async_engine(postgres_dsn, pool_pre_ping=True)
    client_id = uuid.uuid4()
    session_id = uuid.uuid4()
    snapshot_id = uuid.uuid4()
    server_session = Session(
        id=session_id,
        workstation_id=uuid.uuid4(),
        client_id=client_id,
        guest_name=None,
        status=SessionStatus.ACTIVE,
        started_at=datetime.datetime.now(datetime.UTC),
        ended_at=None,
        source="local_ledger",
        created_by="v2-postgres-test",
        created_at=datetime.datetime.now(datetime.UTC),
    )
    first = make_event(client_id=client_id, session_id=session_id, snapshot_id=snapshot_id)
    second = make_event(
        client_id=client_id,
        session_id=session_id,
        sequence=2,
        previous_hash=first.payload_hash,
        snapshot_id=snapshot_id,
    )
    stopped_at = datetime.datetime.now(datetime.UTC) + datetime.timedelta(minutes=1)
    before_stop = make_event(
        client_id=client_id,
        session_id=session_id,
        occurred_at=stopped_at - datetime.timedelta(seconds=1),
        sequence=3,
        previous_hash=second.payload_hash,
        snapshot_id=snapshot_id,
    )
    after_stop = make_event(
        client_id=client_id,
        session_id=session_id,
        occurred_at=stopped_at + datetime.timedelta(seconds=1),
        sequence=4,
        previous_hash=before_stop.payload_hash,
        snapshot_id=snapshot_id,
    )
    operation_ids = (first.operation_id, second.operation_id, before_stop.operation_id)
    try:
        now = datetime.datetime.now(datetime.UTC)
        await PostgresClientRepository(lambda: engine).save(
            Client(
                id=client_id,
                nickname=f"V2Reconcile{client_id.hex[:10]}",
                phone=None,
                discount_category=None,
                balance_cents=starting_balance,
                balance_bonus=0,
                created_at=now,
                updated_at=now,
            )
        )
        await PostgresSessionRepository(lambda: engine).save(server_session)
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
            PostgresV2ClientFactReconciliationRepository(
                lambda: engine,
                clients=PostgresClientBalanceTransactionWriter(),
            )
        )
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    "UPDATE v2_session_leases SET snapshot_payload = :payload "
                    "WHERE session_id = :id"
                ),
                {
                    "id": session_id,
                    "payload": offline_session_snapshot_pb2.OfflineSessionSnapshotPayload(
                        debt_limit_cents=debt_limit,
                    ).SerializeToString(),
                },
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
        await PostgresSessionRepository(lambda: engine).save(server_session.stop(stopped_at))
        accepted_before_stop = await service.accept(before_stop)
        rejected_after_stop = await service.accept(after_stop)
        if debt_limit:
            over_limit = make_event(
                client_id=client_id,
                session_id=session_id,
                snapshot_id=snapshot_id,
                sequence=4,
                previous_hash=before_stop.payload_hash,
                occurred_at=stopped_at - datetime.timedelta(milliseconds=1),
            )
            assert (await service.accept(over_limit)).status is V2ClientFactStatus.CONFLICT
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
        assert accepted_before_stop.status is V2ClientFactStatus.ACCEPTED
        assert rejected_after_stop.status is V2ClientFactStatus.CONFLICT
        assert analytics.status is V2InboxStatus.ACCEPTED

        async with engine.connect() as connection:
            balance = await connection.scalar(
                text("SELECT balance_cents FROM clients WHERE id = :client_id"),
                {"client_id": client_id},
            )
            debit_count = await connection.scalar(
                text("""
                    SELECT count(*) FROM balance_operations
                    WHERE client_id = :client_id AND operation_type = 'debit'
                """),
                {"client_id": client_id},
            )
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

        assert balance == starting_balance - 300
        assert debit_count == 3
        assert dict(counts) == {
            "inbox_rows": 4,
            "confirmed_rows": 3,
            "outbox_rows": 6,
            "audit_rows": 3,
            "last_sequence": 3,
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
            await connection.execute(
                text("DELETE FROM gaming_sessions WHERE id = :session_id"),
                {"session_id": session_id},
            )
            await connection.execute(
                text("DELETE FROM balance_operations WHERE client_id = :client_id"),
                {"client_id": client_id},
            )
            await clear_client_bonus_records(connection, client_id)
            await connection.execute(
                text("DELETE FROM clients WHERE id = :client_id"),
                {"client_id": client_id},
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
        await PostgresClientRepository(lambda: engine).save(
            Client(
                id=client_id,
                nickname=f"V2KafkaDebit{client_id.hex[:10]}",
                phone=None,
                discount_category=None,
                balance_cents=500,
                balance_bonus=0,
                created_at=now,
                updated_at=now,
            )
        )
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
        async with engine.connect() as connection:
            balance = await connection.scalar(
                text("SELECT balance_cents FROM clients WHERE id = :client_id"),
                {"client_id": client_id},
            )
        assert balance == 400

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
            await connection.execute(
                text("DELETE FROM balance_operations WHERE client_id = :client_id"),
                {"client_id": client_id},
            )
            await clear_client_bonus_records(connection, client_id)
            await connection.execute(
                text("DELETE FROM clients WHERE id = :client_id"),
                {"client_id": client_id},
            )
        await engine.dispose()


@pytest.mark.asyncio
async def test_postgres_v2_deposit_requires_matching_active_lease(postgres_dsn: str) -> None:
    """Проверяет заявленное поведение backend."""
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
        service = V2DepositCreditService(
            PostgresV2DepositCreditRepository(
                lambda: engine,
                clients=PostgresClientBalanceTransactionWriter(),
            )
        )

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
            await clear_client_bonus_records(connection, client_id)
            await connection.execute(
                text("DELETE FROM clients WHERE id = :client_id"),
                {"client_id": client_id},
            )
        await engine.dispose()


@pytest.mark.asyncio
async def test_postgres_v2_lease_issuer_is_exclusive_and_idempotent(postgres_dsn: str) -> None:
    """Проверяет заявленное поведение backend."""
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
    """Проверяет заявленное поведение backend."""
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
async def test_postgres_v2_snapshot_issue_cleans_lease_for_completed_session(
    postgres_dsn: str,
) -> None:
    """Проверяет повторный вход после завершения V2-сессии с устаревшим lease."""
    engine = create_async_engine(postgres_dsn, pool_pre_ping=True)
    now = datetime.datetime.now(datetime.UTC)
    client_id = uuid.uuid4()
    device_id = "v2-stale-lease-device"
    ended_at = now - datetime.timedelta(minutes=1)
    previous_session = Session(
        id=uuid.uuid4(),
        workstation_id=uuid.uuid4(),
        client_id=client_id,
        guest_name=None,
        status=SessionStatus.COMPLETED,
        started_at=ended_at - datetime.timedelta(minutes=10),
        ended_at=ended_at,
        source="local_ledger",
        created_by="v2-stale-lease-test",
        created_at=ended_at - datetime.timedelta(minutes=10),
    )
    previous_lease = V2SessionLease(
        session_id=previous_session.id,
        client_id=client_id,
        device_id=device_id,
        snapshot_id=uuid.uuid4(),
        snapshot_version=1,
        policy_version="test-policy",
        issued_at=previous_session.started_at,
    )
    next_lease = V2SessionLease(
        session_id=uuid.uuid4(),
        client_id=client_id,
        device_id=device_id,
        snapshot_id=uuid.uuid4(),
        snapshot_version=1,
        policy_version="test-policy",
        issued_at=now,
    )
    try:
        await PostgresSessionRepository(lambda: engine).save(previous_session)
        await PostgresV2SessionLeaseRepository(lambda: engine).issue_exclusively(previous_lease)
        payload = offline_session_snapshot_pb2.OfflineSessionSnapshotPayload(
            snapshot_id=str(next_lease.snapshot_id),
            schema_version=1,
            snapshot_version=next_lease.snapshot_version,
            client_id=str(client_id),
            session_id=str(next_lease.session_id),
            device_id=device_id,
            balance_cents=1_000,
            debt_limit_cents=0,
            login_grant_remaining_minutes=0,
            policy_version=next_lease.policy_version,
        )
        issued_at = Timestamp()
        issued_at.FromDatetime(now)
        payload.issued_at.CopyFrom(issued_at)
        signed_snapshot = sign_offline_session_snapshot(
            payload,
            "test-key-2026-09",
            V2Ed25519SnapshotSigner(base64.b64encode(bytes(range(32))).decode("ascii")),
        )

        result = await V2SnapshotIssueService(
            PostgresV2SnapshotIssueRepository(lambda: engine)
        ).issue(V2SignedSnapshotIssue(next_lease, signed_snapshot))

        assert not result.is_duplicate
        async with engine.connect() as connection:
            lease_statuses = dict(
                (
                    await connection.execute(
                        text("""
                            SELECT session_id, status FROM v2_session_leases
                            WHERE session_id = ANY(:session_ids)
                        """),
                        {"session_ids": [previous_session.id, next_lease.session_id]},
                    )
                ).all()
            )
        assert lease_statuses == {
            previous_session.id: "revoked",
            next_lease.session_id: "active",
        }
    finally:
        async with engine.begin() as connection:
            await connection.execute(
                text("DELETE FROM audit_events WHERE request_id = :request_id"),
                {"request_id": str(next_lease.snapshot_id)},
            )
            await connection.execute(
                text("DELETE FROM v2_server_outbox WHERE event_id = :event_id"),
                {"event_id": next_lease.snapshot_id},
            )
            await connection.execute(
                text("DELETE FROM v2_session_leases WHERE session_id = ANY(:session_ids)"),
                {"session_ids": [previous_session.id, next_lease.session_id]},
            )
            await connection.execute(
                text("DELETE FROM gaming_sessions WHERE id = :session_id"),
                {"session_id": previous_session.id},
            )
        await engine.dispose()


@pytest.mark.asyncio
async def test_postgres_v2_interruption_revokes_session_lease(
    postgres_dsn: str,
) -> None:
    """Проверяет, что досрочное завершение в серверной БД освобождает V2 lease."""
    engine = create_async_engine(postgres_dsn, pool_pre_ping=True)
    now = datetime.datetime.now(datetime.UTC)
    client_id = uuid.uuid4()
    session_id = uuid.uuid4()
    session = Session(
        id=session_id,
        workstation_id=uuid.uuid4(),
        client_id=client_id,
        guest_name=None,
        status=SessionStatus.ACTIVE,
        started_at=now - datetime.timedelta(minutes=2),
        ended_at=None,
        source="local_ledger",
        created_by="v2-interruption-test",
        created_at=now - datetime.timedelta(minutes=2),
    )
    lease = V2SessionLease(
        session_id=session_id,
        client_id=client_id,
        device_id="v2-interruption-device",
        snapshot_id=uuid.uuid4(),
        snapshot_version=1,
        policy_version="test-policy",
        issued_at=session.started_at,
    )
    try:
        sessions = PostgresSessionRepository(lambda: engine)
        leases = PostgresV2SessionLeaseRepository(lambda: engine)
        await sessions.save(session)
        await leases.issue_exclusively(lease)
        service = SessionService(
            sessions,
            workstations=None,
            clients=None,
            v2_session_leases=leases,
        )

        stopped = await service.interrupt(
            session_id,
            interrupted_by="v2-interruption-test",
            reason="test early stop",
            idempotency_key=f"v2-interruption-{uuid.uuid4()}",
        )

        assert stopped.status is SessionStatus.COMPLETED
        async with engine.connect() as connection:
            lease_status = await connection.scalar(
                text("SELECT status FROM v2_session_leases WHERE session_id = :session_id"),
                {"session_id": session_id},
            )
        assert lease_status == "revoked"
    finally:
        async with engine.begin() as connection:
            await connection.execute(
                text("DELETE FROM v2_session_leases WHERE session_id = :session_id"),
                {"session_id": session_id},
            )
            await connection.execute(
                text("DELETE FROM gaming_sessions WHERE id = :session_id"),
                {"session_id": session_id},
            )
        await engine.dispose()


@pytest.mark.asyncio
async def test_postgres_v2_deposit_lease_lookup_ignores_expired_active_status(
    postgres_dsn: str,
) -> None:
    """Просроченный lease не должен блокировать обычное пополнение баланса."""
    engine = create_async_engine(postgres_dsn, pool_pre_ping=True)
    now = datetime.datetime.now(datetime.UTC)
    expired_lease = V2SessionLease(
        session_id=uuid.uuid4(),
        client_id=uuid.uuid4(),
        device_id="v2-expired-deposit-lease",
        snapshot_id=uuid.uuid4(),
        snapshot_version=1,
        policy_version="test-policy",
        issued_at=now - datetime.timedelta(minutes=2),
        expires_at=now - datetime.timedelta(minutes=1),
    )
    active_lease = V2SessionLease(
        session_id=uuid.uuid4(),
        client_id=uuid.uuid4(),
        device_id="v2-current-deposit-lease",
        snapshot_id=uuid.uuid4(),
        snapshot_version=1,
        policy_version="test-policy",
        issued_at=now - datetime.timedelta(minutes=1),
        expires_at=now + datetime.timedelta(minutes=1),
    )
    try:
        leases = PostgresV2SessionLeaseRepository(lambda: engine)
        await leases.issue_exclusively(expired_lease)
        await leases.issue_exclusively(active_lease)
        deposits = PostgresV2DepositCreditRepository(
            lambda: engine,
            clients=PostgresClientBalanceTransactionWriter(),
        )

        assert not await deposits.has_active_lease_for_client(expired_lease.client_id)
        assert await deposits.has_active_lease_for_client(active_lease.client_id)
    finally:
        async with engine.begin() as connection:
            await connection.execute(
                text("DELETE FROM v2_session_leases WHERE session_id = ANY(:session_ids)"),
                {"session_ids": [expired_lease.session_id, active_lease.session_id]},
            )
        await engine.dispose()


@pytest.mark.asyncio
async def test_postgres_v2_login_rolls_back_new_session_when_lease_cannot_be_issued(
    postgres_dsn: str,
) -> None:
    """Проверяет заявленное поведение backend."""
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
        source="local_ledger",
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
    blocked_session = dataclasses.replace(
        session_to_start,
        id=blocked_lease_session_id,
        client_id=uuid.uuid4(),
        workstation_id=uuid.uuid4(),
        idempotency_key=None,
    )
    try:
        await PostgresSessionRepository(lambda: engine).save(blocked_session)
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
                    "client_id": blocked_session.client_id,
                    "device_id": lease.device_id,
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
            await connection.execute(
                text("DELETE FROM gaming_sessions WHERE id = :id"), {"id": blocked_lease_session_id}
            )
        await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("legacy_package_id", "total_minutes", "burn_after"),
    [(False, 180, False), (True, 180, False), (False, 5, False), (False, 180, True)],
)
async def test_confirmed_package_minutes_reduce_operator_snapshot_once(
    postgres_dsn: str,
    legacy_package_id: bool,
    total_minutes: int,
    burn_after: bool,
) -> None:
    """Уменьшает остаток пакета на пять минут, сохраняя окончание и идемпотентность."""
    from types import SimpleNamespace

    from gameclub_backend.modules.entitlements.application.service import EntitlementService
    from gameclub_backend.modules.entitlements.domain import Entitlement, EntitlementStatus
    from gameclub_backend.modules.entitlements.infrastructure.postgres import (
        PostgresEntitlementRepository,
        PostgresEntitlementTransactionWriter,
    )

    engine = create_async_engine(postgres_dsn)
    now = datetime.datetime.now(datetime.UTC).replace(second=0, microsecond=0)
    client_id, session_id, snapshot_id, package_id, tariff_id = [uuid.uuid4() for _ in range(5)]
    local_package_id = uuid.uuid4() if legacy_package_id else package_id
    client_repo = PostgresClientRepository(lambda: engine)
    session_repo = PostgresSessionRepository(lambda: engine)
    packages = PostgresEntitlementRepository(lambda: engine)
    server_session = Session(
        id=session_id,
        workstation_id=uuid.uuid4(),
        client_id=client_id,
        guest_name=None,
        status=SessionStatus.ACTIVE,
        started_at=now,
        ended_at=None,
        source="local_ledger",
        created_by="test",
        created_at=now,
    )
    event = make_event(client_id=client_id, session_id=session_id, snapshot_id=snapshot_id)
    try:
        await client_repo.save(
            Client(
                id=client_id,
                nickname=f"Package{client_id.hex[:10]}",
                phone=None,
                discount_category=None,
                balance_cents=-500,
                balance_bonus=0,
                created_at=now,
                updated_at=now,
            )
        )
        await session_repo.save(server_session)
        await packages.create(
            Entitlement(
                id=package_id,
                client_id=client_id,
                tariff_id=tariff_id,
                zone_id=None,
                duration_minutes=total_minutes,
                remaining_minutes=total_minutes,
                price_cents=100,
                queue_position=1,
                status=EntitlementStatus.ACTIVE,
                idempotency_key=str(package_id),
                purchased_at=now + datetime.timedelta(seconds=1),
                activated_at=now,
            )
        )
        async with engine.begin() as connection:
            await connection.execute(
                text("""INSERT INTO v2_session_leases
                (session_id, client_id, device_id, snapshot_id, snapshot_version,
                 policy_version, status, issued_at)
                VALUES (:session, :client, :device, :snapshot, 1, 'test', 'active', :now)"""),
                {
                    "session": session_id,
                    "client": client_id,
                    "device": event.device_id,
                    "snapshot": snapshot_id,
                    "now": now,
                },
            )
        reconciliation = V2ClientFactReconciliationService(
            PostgresV2ClientFactReconciliationRepository(
                lambda: engine,
                entitlement_writer=PostgresEntitlementTransactionWriter(),
                clients=PostgresClientBalanceTransactionWriter(),
            )
        )
        previous = None
        for minute in range(1, 6):
            event = V2Event.create(
                operation_id=uuid.uuid4(),
                event_type=V2EventType.PACKAGE_CONSUMED,
                producer_id="workstation:package-test",
                client_id=client_id,
                session_id=session_id,
                device_id=event.device_id,
                sequence=minute,
                previous_hash=previous,
                occurred_at=now + datetime.timedelta(minutes=minute),
                payload={
                    "snapshot_id": str(snapshot_id),
                    "snapshot_version": 1,
                    "package_id": str(local_package_id),
                    "tariff_id": str(tariff_id),
                    "remaining_minutes": total_minutes - minute,
                },
            )
            assert (await reconciliation.accept(event)).status is V2ClientFactStatus.ACCEPTED
            assert (await reconciliation.accept(event)).status is V2ClientFactStatus.DUPLICATE
            previous = event.payload_hash

        if burn_after:
            event = V2Event.create(
                operation_id=uuid.uuid4(),
                event_type=V2EventType.PACKAGE_BURNED,
                producer_id="workstation:package-test",
                client_id=client_id,
                session_id=session_id,
                device_id=event.device_id,
                sequence=6,
                previous_hash=previous,
                occurred_at=now + datetime.timedelta(minutes=5),
                payload={
                    "snapshot_id": str(snapshot_id),
                    "snapshot_version": 1,
                    "package_id": str(local_package_id),
                    "tariff_id": str(tariff_id),
                    "remaining_minutes": total_minutes - 5,
                },
            )
            assert (await reconciliation.accept(event)).status is V2ClientFactStatus.ACCEPTED
            assert (await reconciliation.accept(event)).status is V2ClientFactStatus.DUPLICATE

        class Workstations:
            async def get(self, workstation_id):
                return SimpleNamespace(id=workstation_id, device_id=event.device_id, group_id=None)

        service = SessionService(
            session_repo,
            workstations=Workstations(),
            clients=client_repo,
            entitlements=EntitlementService(packages, tariffs=None, clients=None),
        )
        snapshot = await service.snapshot(session_id, now=now + datetime.timedelta(minutes=5))
        if total_minutes == 5 or burn_after:
            assert snapshot.active_entitlement is None
            assert snapshot.entitlements[0].remaining_minutes == 0
            assert snapshot.entitlements[0].status is (
                EntitlementStatus.BURNED if burn_after else EntitlementStatus.EXHAUSTED
            )
        else:
            assert snapshot.active_entitlement.remaining_minutes == 175
            assert snapshot.server_time + datetime.timedelta(
                minutes=175
            ) == now + datetime.timedelta(minutes=180)
        assert snapshot.balance_cents == -500
    finally:
        async with engine.begin() as connection:
            for table in (
                "v2_server_outbox",
                "v2_confirmed_client_facts",
                "v2_event_inbox",
                "v2_session_chains",
                "v2_session_leases",
            ):
                await connection.execute(
                    text(f"DELETE FROM {table} WHERE session_id = :id"), {"id": session_id}
                )
            await connection.execute(
                text("DELETE FROM audit_events WHERE resource_path LIKE :path"),
                {"path": f"clients/{client_id}/sessions/{session_id}/operations/%"},
            )
            await connection.execute(
                text("DELETE FROM client_entitlements WHERE client_id = :id"), {"id": client_id}
            )
            await connection.execute(
                text("DELETE FROM gaming_sessions WHERE id = :id"), {"id": session_id}
            )
            await clear_client_bonus_records(connection, client_id)
            await connection.execute(text("DELETE FROM clients WHERE id = :id"), {"id": client_id})
        await engine.dispose()
