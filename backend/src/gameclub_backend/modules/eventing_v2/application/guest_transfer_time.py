from __future__ import annotations

import dataclasses
import datetime
import typing
import uuid

from gameclub.v2 import offline_session_snapshot_pb2
from gameclub_backend.application.errors import ApplicationError, ErrorCode
from gameclub_backend.modules.entitlements.domain import EntitlementStatus
from gameclub_backend.modules.eventing_v2.application.guest_access import (
    GuestAccessGrant,
    GuestAccessGrantRepository,
)
from gameclub_backend.modules.sessions.application.v2_transfer import V2TransferReservation
from gameclub_backend.modules.sessions.domain import Session


@dataclasses.dataclass(frozen=True)
class GuestTransferPackage:
    grant_id: uuid.UUID
    tariff_id: str
    tariff_name: str
    zone_id: str | None
    remaining_minutes: int
    status: EntitlementStatus

    def compatible_with(self, zone_id: str | None) -> bool:
        return self.zone_id is None or self.zone_id == zone_id


@dataclasses.dataclass(frozen=True)
class GuestTransferTime:
    """Guest minutes are reconstructed from server grants and the signed starting boundary."""

    boundary: datetime.datetime
    zone_id: str | None
    grant_minutes: int
    packages: tuple[GuestTransferPackage, ...]
    exhausted: bool = False
    applied_grant_ids: tuple[uuid.UUID, ...] = ()
    snapshot_version: int = 1

    def advance(self, now: datetime.datetime) -> GuestTransferTime:
        boundary = now.replace(second=0, microsecond=0)
        minutes = (boundary - self.boundary) // datetime.timedelta(minutes=1)
        if minutes <= 0 or self.exhausted:
            return self
        grant_spent = min(minutes, self.grant_minutes)
        minutes -= grant_spent
        packages = list(self.packages)
        order = sorted(
            range(len(packages)),
            key=lambda index: packages[index].status is not EntitlementStatus.ACTIVE,
        )
        for index in order:
            package = packages[index]
            if not minutes:
                break
            if package.status not in (EntitlementStatus.ACTIVE, EntitlementStatus.QUEUED):
                continue
            if not package.compatible_with(self.zone_id) or not package.remaining_minutes:
                continue
            spent = min(minutes, package.remaining_minutes)
            remaining = package.remaining_minutes - spent
            packages[index] = dataclasses.replace(
                package,
                remaining_minutes=remaining,
                status=EntitlementStatus.ACTIVE if remaining else EntitlementStatus.EXHAUSTED,
            )
            minutes -= spent
        return dataclasses.replace(
            self,
            boundary=boundary,
            grant_minutes=self.grant_minutes - grant_spent,
            packages=tuple(packages),
            exhausted=minutes > 0,
        )

    def move(
        self, zone_id: str | None, fallback_grant_minutes: int
    ) -> tuple[GuestTransferTime, GuestTransferPackage | None]:
        if self.exhausted:
            raise ValueError("Guest source has no time left")
        burned = next(
            (
                item
                for item in self.packages
                if item.status is EntitlementStatus.ACTIVE and not item.compatible_with(zone_id)
            ),
            None,
        )
        packages = tuple(
            dataclasses.replace(item, remaining_minutes=0, status=EntitlementStatus.BURNED)
            if item is burned
            else item
            for item in self.packages
        )
        usable_package = any(
            item.status in (EntitlementStatus.ACTIVE, EntitlementStatus.QUEUED)
            and item.remaining_minutes > 0
            and item.compatible_with(zone_id)
            for item in packages
        )
        return dataclasses.replace(
            self,
            zone_id=zone_id,
            grant_minutes=self.grant_minutes if usable_package else fallback_grant_minutes,
            packages=packages,
        ), burned


class GuestTransferSnapshots(typing.Protocol):
    async def latest_transfer_for_session(
        self, session_id: uuid.UUID, workstation_id: uuid.UUID
    ) -> offline_session_snapshot_pb2.SignedOfflineSessionSnapshot | None: ...

    async def save_guest_transfer(
        self,
        operation: V2TransferReservation,
        snapshot: offline_session_snapshot_pb2.SignedOfflineSessionSnapshot,
    ) -> None: ...


class GuestTransferClock:
    def __init__(
        self, grants: GuestAccessGrantRepository, transfers: GuestTransferSnapshots | None = None
    ) -> None:
        self._grants = grants
        self._transfers = transfers

    async def at(
        self, session: Session, source_zone_id: str | None, now: datetime.datetime
    ) -> GuestTransferTime:
        if session.guest_payment_id is None:
            raise ApplicationError(ErrorCode.CONFLICT, "Guest transfer requires a paid session")
        grants = await self._grants.list_redeemed_for_session(session.id)
        issued = []
        for grant in grants:
            payload = offline_session_snapshot_pb2.GuestSessionAccessPayload.FromString(
                grant.payload or b""
            )
            if (
                payload.session_id != str(session.id)
                or payload.grant_id != str(grant.id)
                or payload.payment_id != str(grant.payment_id)
                or not payload.HasField("issued_at")
                or not payload.duration_minutes
                or not payload.tariff_quantity
            ):
                raise ApplicationError(ErrorCode.CONFLICT, "Guest transfer has an invalid grant")
            issued.append((grant, payload, payload.issued_at.ToDatetime(datetime.UTC)))

        previous = (
            await self._transfers.latest_transfer_for_session(session.id, session.workstation_id)
            if self._transfers is not None
            else None
        )
        if previous is not None:
            state = self._previous_state(previous, session, source_zone_id, now)
        else:
            paid = next(
                (item for item in issued if item[0].payment_id == session.guest_payment_id), None
            )
            if paid is None or paid[0].is_extension or paid[2] > now:
                raise ApplicationError(ErrorCode.CONFLICT, "Guest's paid access is unavailable")
            state = GuestTransferTime(
                paid[2].replace(second=0, microsecond=0),
                source_zone_id,
                0,
                (self._package(paid[0], paid[1], EntitlementStatus.ACTIVE),),
                applied_grant_ids=(paid[0].id,),
            )
        extensions = sorted(
            (
                item
                for item in issued
                if item[0].is_extension
                and item[2] <= now
                and item[0].id not in state.applied_grant_ids
            ),
            key=lambda item: (item[2], item[0].id),
        )
        for grant, payload, issued_at in extensions:
            state = state.advance(issued_at)
            if state.exhausted:
                break
            state = dataclasses.replace(
                state,
                packages=(*state.packages, self._package(grant, payload, EntitlementStatus.QUEUED)),
                applied_grant_ids=(*state.applied_grant_ids, grant.id),
            )
        return state.advance(now)

    @staticmethod
    def _previous_state(
        previous: offline_session_snapshot_pb2.SignedOfflineSessionSnapshot,
        session: Session,
        source_zone_id: str | None,
        now: datetime.datetime,
    ) -> GuestTransferTime:
        payload = previous.payload
        issued_at = payload.issued_at.ToDatetime(datetime.UTC)
        if (
            payload.session_id != str(session.id)
            or payload.transfer_handoff.guest.payment_id != str(session.guest_payment_id)
            or (payload.workstation_zone_id or None) != source_zone_id
            or issued_at > now
        ):
            raise ApplicationError(ErrorCode.CONFLICT, "Guest transfer starting state is invalid")
        names = {tariff.tariff_id: tariff.name for tariff in payload.tariffs}
        return GuestTransferTime(
            issued_at.replace(second=0, microsecond=0),
            source_zone_id,
            payload.login_grant_remaining_minutes,
            tuple(
                GuestTransferPackage(
                    uuid.UUID(package.package_id),
                    package.tariff_id,
                    names.get(package.tariff_id, "Пакет"),
                    package.zone_id if package.HasField("zone_id") else None,
                    package.remaining_minutes,
                    EntitlementStatus.ACTIVE
                    if package.status == offline_session_snapshot_pb2.OFFLINE_PACKAGE_STATUS_ACTIVE
                    else EntitlementStatus.QUEUED,
                )
                for package in payload.packages
            ),
            applied_grant_ids=tuple(
                uuid.UUID(value) for value in payload.transfer_handoff.guest.applied_grant_ids
            ),
            snapshot_version=payload.snapshot_version,
        )

    @staticmethod
    def _package(
        grant: GuestAccessGrant,
        payload: offline_session_snapshot_pb2.GuestSessionAccessPayload,
        status: EntitlementStatus,
    ) -> GuestTransferPackage:
        return GuestTransferPackage(
            grant.id,
            payload.tariff_id,
            payload.tariff_name,
            payload.workstation_zone_id if payload.HasField("workstation_zone_id") else None,
            payload.duration_minutes * payload.tariff_quantity,
            status,
        )
