import datetime
import uuid

from gameclub.v2 import offline_session_snapshot_pb2
from gameclub_backend.modules.entitlements.domain import EntitlementStatus
from gameclub_backend.modules.eventing_v2.application.guest_access import GuestAccessGrant
from gameclub_backend.modules.eventing_v2.application.guest_transfer_time import GuestTransferClock
from gameclub_backend.modules.eventing_v2.application.transfer_start import V2TransferStartService
from gameclub_backend.modules.eventing_v2.infrastructure.guest_access_memory import (
    InMemoryGuestAccessGrantRepository,
)
from gameclub_backend.modules.sessions.domain import Session, SessionStatus
from gameclub_backend.modules.workstations.domain import Workstation


async def test_guest_transfer_charges_elapsed_minutes_and_preserves_unused_queue():
    initial = datetime.datetime(2026, 11, 16, 10, 0, 20, tzinfo=datetime.UTC)
    source = Session(
        id=uuid.uuid4(),
        workstation_id=uuid.uuid4(),
        client_id=None,
        guest_name="Гость",
        status=SessionStatus.ACTIVE,
        started_at=initial,
        ended_at=None,
        source="guest_local_ledger",
        created_by="test",
        created_at=initial,
        guest_payment_id=uuid.uuid4(),
    )
    grants = InMemoryGuestAccessGrantRepository()

    async def issue(minutes, offset, *, extension=False, zone="vip"):
        grant_id = uuid.uuid4()
        payment_id = uuid.uuid4() if extension else source.guest_payment_id
        payload = offline_session_snapshot_pb2.GuestSessionAccessPayload(
            grant_id=str(grant_id),
            payment_id=str(payment_id),
            session_id=str(source.id),
            tariff_id=str(uuid.uuid4()),
            tariff_name="Гостевой пакет",
            duration_minutes=minutes,
            tariff_quantity=1,
        )
        if zone is not None:
            payload.workstation_zone_id = zone
        issued_at = initial + datetime.timedelta(minutes=offset)
        payload.issued_at.FromDatetime(issued_at)
        await grants.save(
            GuestAccessGrant(
                id=grant_id,
                payment_id=payment_id,
                workstation_id=source.workstation_id,
                expires_at=issued_at + datetime.timedelta(minutes=10),
                session_id=source.id,
                payload=payload.SerializeToString(),
                signature=b"signature",
                signing_key_id="key",
                is_extension=extension,
            )
        )
        return grant_id

    initial_id = await issue(10, 0)
    queued_id = await issue(20, 1, extension=True)
    now = initial + datetime.timedelta(minutes=3)
    clock = GuestTransferClock(grants)
    state = await clock.at(source, "vip", now)

    active, queued = state.packages
    assert (active.grant_id, active.remaining_minutes) == (initial_id, 7)
    assert (queued.grant_id, queued.remaining_minutes) == (queued_id, 20)
    kept, burned = state.move("vip", fallback_grant_minutes=0)
    assert kept == state and burned is None

    moved, burned = state.move("standard", fallback_grant_minutes=1)
    assert burned == active
    assert moved.packages[0].status is EntitlementStatus.BURNED
    assert moved.packages[1] == queued
    assert moved.grant_minutes == 1
    assert (await clock.at(source, "vip", now)) == state
    assert moved.advance(now + datetime.timedelta(minutes=1)).grant_minutes == 0

    end = await clock.at(source, "vip", initial + datetime.timedelta(minutes=11))
    assert end.packages[0].status is EntitlementStatus.EXHAUSTED
    assert end.packages[1].remaining_minutes == 19
    assert (await clock.at(source, "vip", initial + datetime.timedelta(minutes=31))).exhausted

    class Workstations:
        async def get(self, workstation_id):
            assert workstation_id == source.workstation_id
            return Workstation(
                id=source.workstation_id, device_id="vip", name="VIP", group_id="vip"
            )

    service = V2TransferStartService(
        None,
        Workstations(),
        None,
        None,
        None,
        None,
        0,
        clock=lambda: now,
        guest_clock=clock,
    )
    quote = await service.quote_for_target(
        source, Workstation(uuid.uuid4(), "standard", "Standard", group_id="standard")
    )
    assert quote.burned_package_id == initial_id
    assert quote.burned_package_minutes == 7
    assert quote.fallback_grant_minutes == 0
    assert quote.per_minute_price_cents is None
