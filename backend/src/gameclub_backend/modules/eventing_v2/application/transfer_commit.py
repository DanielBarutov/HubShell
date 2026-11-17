from __future__ import annotations

import dataclasses
import datetime
import typing
import uuid

from gameclub.v2 import offline_session_snapshot_pb2
from gameclub_backend.application.errors import ApplicationError, ErrorCode
from gameclub_backend.domain.equipment import EquipmentType
from gameclub_backend.modules.client_groups.application.service import ClientGroupService
from gameclub_backend.modules.clients.application.portal import ClientPortalService
from gameclub_backend.modules.entitlements.application.service import EntitlementService
from gameclub_backend.modules.entitlements.domain import EntitlementStatus
from gameclub_backend.modules.eventing_v2.application.guest_transfer_time import (
    GuestTransferSnapshots,
)
from gameclub_backend.modules.eventing_v2.application.snapshot import (
    V2OfflineSnapshotFactory,
    V2OfflineSnapshotInput,
)
from gameclub_backend.modules.eventing_v2.application.snapshot_issue import (
    V2SignedSnapshotIssue,
    V2TransferSourceState,
)
from gameclub_backend.modules.eventing_v2.application.transfer_start import V2TransferStartService
from gameclub_backend.modules.eventing_v2.infrastructure.snapshot_protobuf import (
    V2OfflineSnapshotSigner,
    sign_offline_session_snapshot,
)
from gameclub_backend.modules.reservations.application.ports import TransferReservationEntryLookup
from gameclub_backend.modules.sessions.application.service import SessionService
from gameclub_backend.modules.sessions.application.v2_transfer import (
    TransferRightsWriter,
    V2TransferReservation,
    V2TransferStatus,
)
from gameclub_backend.modules.sessions.domain import Session, SessionStatus
from gameclub_backend.modules.workstations.application.service import WorkstationService
from gameclub_backend.modules.workstations.domain import (
    Workstation,
    WorkstationSessionMode,
    WorkstationStatus,
)


class TransferCommitRepository(typing.Protocol):
    async def get_for_workstation(
        self, operation_id: uuid.UUID, workstation_id: uuid.UUID
    ) -> V2TransferReservation: ...

    async def commit(
        self,
        operation_id: uuid.UUID,
        source_workstation_id: uuid.UUID,
        apply_rights: TransferRightsWriter,
    ) -> V2TransferReservation: ...


class TransferEventChain(typing.Protocol):
    def transfer_transaction(self, session_id: uuid.UUID) -> typing.AsyncContextManager[None]: ...


class TransferSnapshots(typing.Protocol):
    async def transfer_source_state(
        self, operation: V2TransferReservation, source_device_id: str
    ) -> V2TransferSourceState: ...

    async def transfer_lease(
        self, operation: V2TransferReservation, source_device_id: str, value: V2SignedSnapshotIssue
    ) -> None: ...

    async def get_transfer_snapshot(
        self, operation: V2TransferReservation, target_device_id: str
    ) -> offline_session_snapshot_pb2.SignedOfflineSessionSnapshot | None: ...


class V2TransferCommitService:
    def __init__(
        self,
        *,
        workstations: WorkstationService,
        reservations: TransferReservationEntryLookup,
        operations: TransferCommitRepository,
        chains: TransferEventChain,
        snapshots: TransferSnapshots,
        start: V2TransferStartService,
        portal: ClientPortalService,
        client_groups: ClientGroupService,
        entitlements: EntitlementService,
        signing_key_id: str,
        signer: V2OfflineSnapshotSigner,
        clock: typing.Callable[[], datetime.datetime] | None = None,
        guest_transfers: GuestTransferSnapshots | None = None,
        sessions: SessionService | None = None,
    ) -> None:
        self._workstations = workstations
        self._reservations = reservations
        self._operations = operations
        self._chains = chains
        self._snapshots = snapshots
        self._start = start
        self._portal = portal
        self._client_groups = client_groups
        self._entitlements = entitlements
        self._signing_key_id = signing_key_id
        self._signer = signer
        self._clock = clock or (lambda: datetime.datetime.now(datetime.UTC))
        self._guest_transfers = guest_transfers
        self._sessions = sessions

    async def commit(self, device_id: str, operation_id: uuid.UUID) -> V2TransferReservation:
        source = await self._workstations.get_by_device_id(device_id)
        operation = await self._operations.get_for_workstation(operation_id, source.id)
        if operation.source_workstation_id != source.id:
            raise ApplicationError(ErrorCode.NOT_FOUND, "Transfer operation not found")

        async def write_rights(
            current: V2TransferReservation, session: Session
        ) -> datetime.datetime:
            return await self._write_rights(device_id, current, session)

        async with self._chains.transfer_transaction(operation.session_id):
            return await self._operations.commit(operation_id, source.id, write_rights)

    async def _write_rights(
        self, device_id: str, operation: V2TransferReservation, session: Session
    ) -> datetime.datetime:
        checkpoint = operation.source_checkpoint
        if checkpoint is None:
            raise ApplicationError(ErrorCode.CONFLICT, "Transfer source is not ready")
        places = await self._workstations.list()
        source = next((item for item in places if item.id == operation.source_workstation_id), None)
        target = next((item for item in places if item.id == operation.target_workstation_id), None)
        if (
            source is None
            or source.device_id != device_id
            or source.status is not WorkstationStatus.ONLINE
            or target is None
            or not target.device_id
            or target.status is not WorkstationStatus.ONLINE
            or target.equipment_type is not EquipmentType.PC
            or target.session_mode is not WorkstationSessionMode.LOCAL_LEDGER
        ):
            raise ApplicationError(ErrorCode.CONFLICT, "Transfer devices are no longer available")

        decision = await self._reservations.check_entry_for_transfer(
            target.id, client_id=session.client_id, guest_id=session.guest_id
        )
        if not decision.allowed:
            raise ApplicationError(ErrorCode.CONFLICT, "Transfer target entry is no longer allowed")
        if session.client_id is None:
            return await self._write_guest_rights(operation, session, target)
        source_state = await self._snapshots.transfer_source_state(operation, device_id)
        target_state = await self._portal.v2_offline_snapshot_for_device(
            session.client_id, target.device_id
        )
        quote = await self._start.quote_for_target(session, target, target_state)
        if quote.token != operation.quote_token:
            raise ApplicationError(
                ErrorCode.CONFLICT, "Transfer terms changed; request a new quote"
            )
        group = (
            await self._client_groups.get(target_state.client.client_group_id)
            if target_state.client.client_group_id is not None
            else await self._client_groups.get_default()
        )
        if not group.active:
            raise ApplicationError(ErrorCode.CONFLICT, "Client group is inactive")

        now = self._clock()
        boundary = now.replace(second=0, microsecond=0)
        source_has_package = any(
            item.remaining_minutes > 0
            and item.is_compatible(source.group_id)
            and item.is_available_at(now)
            for item in target_state.entitlements
        )
        free_source = (
            source_state.free_per_minute
            and not source_state.login_grant_remaining_minutes
            and not source_has_package
        )
        if not free_source and source_state.last_billed_at < boundary:
            raise ApplicationError(
                ErrorCode.CONFLICT, "Transfer source billing must reach the current minute"
            )
        if quote.burned_package_id is not None:
            await self._entitlements.burn(
                quote.burned_package_id, session.client_id, "transfer_zone_incompatible"
            )

        lease = dataclasses.replace(
            source_state.lease,
            device_id=target.device_id,
            snapshot_id=uuid.uuid4(),
            snapshot_version=source_state.lease.snapshot_version + 1,
            issued_at=now,
        )
        grant_minutes = quote.fallback_grant_minutes
        if grant_minutes is None:
            grant_minutes = source_state.login_grant_remaining_minutes
        payload = V2OfflineSnapshotFactory.create_payload(
            V2OfflineSnapshotInput(
                snapshot_id=lease.snapshot_id,
                snapshot_version=lease.snapshot_version,
                issued_at=now,
                client=target_state.client,
                session=session,
                device_id=target.device_id,
                workstation_zone_id=target.group_id,
                debt_limit_cents=group.negative_balance_limit_cents
                if group.allow_negative_balance
                else 0,
                login_grant_remaining_minutes=grant_minutes,
                entitlements=tuple(
                    item
                    for item in target_state.entitlements
                    if item.is_compatible(target.group_id)
                ),
                tariffs=target_state.tariffs,
                policy_version=lease.policy_version,
            )
        )
        payload.transfer_handoff.operation_id = str(operation.operation_id)
        payload.transfer_handoff.last_sequence = checkpoint.sequence
        payload.transfer_handoff.last_payload_hash = checkpoint.payload_hash or ""
        bonus = source_state.minute_bonus
        if bonus is not None:
            payload.transfer_handoff.minute_bonus.grant_id = str(bonus.grant_id)
            payload.transfer_handoff.minute_bonus.version = bonus.version
            payload.transfer_handoff.minute_bonus.remaining_cents = bonus.remaining_cents
            payload.transfer_handoff.minute_bonus.payment_limit_bps = bonus.payment_limit_bps
        signed = sign_offline_session_snapshot(payload, self._signing_key_id, self._signer)
        await self._snapshots.transfer_lease(
            operation, device_id, V2SignedSnapshotIssue(lease, signed)
        )
        return boundary + datetime.timedelta(minutes=1)

    async def _write_guest_rights(
        self,
        operation: V2TransferReservation,
        session: Session,
        target: Workstation,
    ) -> datetime.datetime:
        if (
            self._guest_transfers is None
            or session.guest_payment_id is None
            or not target.device_id
        ):
            raise ApplicationError(ErrorCode.CONFLICT, "Guest transfer access is unavailable")
        checkpoint = operation.source_checkpoint
        if checkpoint is None or checkpoint.sequence != 0 or checkpoint.payload_hash is not None:
            raise ApplicationError(ErrorCode.CONFLICT, "Guest transfer checkpoint is invalid")
        now = self._clock()
        quote, moved = await self._start.guest_transfer_terms(session, target, now)
        if quote.token != operation.quote_token:
            raise ApplicationError(
                ErrorCode.CONFLICT, "Transfer terms changed; request a new quote"
            )

        api = offline_session_snapshot_pb2
        payload = api.OfflineSessionSnapshotPayload(
            snapshot_id=str(operation.operation_id),
            schema_version=1,
            snapshot_version=moved.snapshot_version + 1,
            client_id=str(uuid.UUID(int=0)),
            session_id=str(session.id),
            device_id=target.device_id,
            login_grant_remaining_minutes=moved.grant_minutes,
            policy_version="guest-transfer-v2",
        )
        payload.issued_at.FromDatetime(now)
        if target.group_id is not None:
            payload.workstation_zone_id = target.group_id
        handoff = payload.transfer_handoff
        handoff.operation_id = str(operation.operation_id)
        handoff.guest.payment_id = str(session.guest_payment_id)
        handoff.guest.name = session.guest_name or "Гость"
        handoff.guest.applied_grant_ids.extend(str(value) for value in moved.applied_grant_ids)
        tariffs_seen: set[str] = set()
        for package in moved.packages:
            if package.status not in (EntitlementStatus.ACTIVE, EntitlementStatus.QUEUED):
                continue
            package_snapshot = payload.packages.add(
                package_id=str(package.grant_id),
                tariff_id=package.tariff_id,
                remaining_minutes=package.remaining_minutes,
                status=api.OFFLINE_PACKAGE_STATUS_ACTIVE
                if package.status is EntitlementStatus.ACTIVE
                else api.OFFLINE_PACKAGE_STATUS_QUEUED,
            )
            if package.zone_id is not None:
                package_snapshot.zone_id = package.zone_id
            if package.tariff_id not in tariffs_seen:
                payload.tariffs.add(tariff_id=package.tariff_id, name=package.tariff_name)
                tariffs_seen.add(package.tariff_id)
        signed = sign_offline_session_snapshot(payload, self._signing_key_id, self._signer)
        await self._guest_transfers.save_guest_transfer(operation, signed)
        return moved.boundary + datetime.timedelta(minutes=1)

    async def get_snapshot(
        self, device_id: str, operation_id: uuid.UUID
    ) -> offline_session_snapshot_pb2.SignedOfflineSessionSnapshot:
        target = await self._workstations.get_by_device_id(device_id)
        operation = await self._operations.get_for_workstation(operation_id, target.id)
        if (
            operation.target_workstation_id != target.id
            or operation.status is not V2TransferStatus.COMMITTED
        ):
            raise ApplicationError(ErrorCode.NOT_FOUND, "Committed transfer access not found")
        snapshot = await self._snapshots.get_transfer_snapshot(operation, device_id)
        if snapshot is None and self._guest_transfers is not None and self._sessions is not None:
            session = await self._sessions.get(operation.session_id)
            if session.workstation_id == target.id and session.status is SessionStatus.ACTIVE:
                guest = await self._guest_transfers.latest_transfer_for_session(
                    session.id, target.id
                )
                if (
                    guest is not None
                    and guest.payload.device_id == device_id
                    and guest.payload.transfer_handoff.operation_id == str(operation_id)
                ):
                    snapshot = guest
        if snapshot is None:
            raise ApplicationError(ErrorCode.NOT_FOUND, "Committed transfer access not found")
        return snapshot
