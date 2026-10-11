from __future__ import annotations

import dataclasses
import datetime
import typing
import uuid

from google.protobuf import timestamp_pb2

from gameclub.v2 import offline_session_snapshot_pb2
from gameclub_backend.application.errors import ApplicationError, ErrorCode
from gameclub_backend.modules.direct_payments.domain import (
    DirectPaymentStatus,
    GuestSessionPayment,
)
from gameclub_backend.modules.eventing_v2.infrastructure.snapshot_protobuf import (
    V2OfflineSnapshotSigner,
)
from gameclub_backend.modules.sessions.application.service import SessionService
from gameclub_backend.modules.sessions.domain import SessionStatus
from gameclub_backend.modules.workstations.application.service import WorkstationService
from gameclub_backend.modules.workstations.domain import WorkstationSessionMode

GUEST_SOURCE = "guest_local_ledger"


@dataclasses.dataclass(frozen=True)
class GuestAccessGrant:
    id: uuid.UUID
    payment_id: uuid.UUID
    workstation_id: uuid.UUID
    expires_at: datetime.datetime
    session_id: uuid.UUID | None = None
    payload: bytes | None = None
    signature: bytes | None = None
    signing_key_id: str | None = None

    @property
    def redeemed(self) -> bool:
        return (
            self.session_id is not None
            and self.payload is not None
            and self.signature is not None
        )


class GuestAccessGrantRepository(typing.Protocol):
    async def get_by_payment(self, payment_id: uuid.UUID) -> GuestAccessGrant | None: ...

    async def get_pending_for_workstation(
        self, workstation_id: uuid.UUID, now: datetime.datetime
    ) -> GuestAccessGrant | None: ...

    async def save(self, grant: GuestAccessGrant) -> GuestAccessGrant: ...


class V2GuestAccessService:
    def __init__(
        self,
        *,
        payments: typing.Any,
        workstations: WorkstationService,
        sessions: SessionService,
        grants: GuestAccessGrantRepository,
        signing_key_id: str,
        signer: V2OfflineSnapshotSigner,
        clock: typing.Callable[[], datetime.datetime] | None = None,
    ) -> None:
        self._payments = payments
        self._workstations = workstations
        self._sessions = sessions
        self._grants = grants
        self._signing_key_id = signing_key_id.strip()
        self._signer = signer
        self._clock = clock or (lambda: datetime.datetime.now(datetime.UTC))
        if not self._signing_key_id:
            raise ValueError("V2 guest signing key id is required")

    async def prepare(self, payment_id: uuid.UUID) -> GuestAccessGrant:
        payment = await self._payments.get(payment_id)
        self._validate_payment(payment)
        workstation = await self._workstations.get(payment.workstation_id)
        if workstation is None:
            raise ApplicationError(ErrorCode.NOT_FOUND, "Workstation not found")
        if workstation.session_mode is not WorkstationSessionMode.LOCAL_LEDGER:
            raise ApplicationError(ErrorCode.CONFLICT, "Guest V2 access requires a V2 workstation")
        if await self._sessions._repository.get_active_for_workstation(workstation.id):
            raise ApplicationError(ErrorCode.CONFLICT, "Workstation already has an active session")
        existing = await self._grants.get_by_payment(payment_id)
        if existing is not None:
            return existing
        now = self._clock()
        return await self._grants.save(
            GuestAccessGrant(
                id=uuid.uuid4(),
                payment_id=payment_id,
                workstation_id=payment.workstation_id,
                expires_at=now + datetime.timedelta(minutes=10),
            )
        )

    async def redeem(
        self, device_id: str
    ) -> offline_session_snapshot_pb2.SignedGuestSessionAccess:
        workstation = await self._workstations.get_by_device_id(device_id)
        if workstation.session_mode is not WorkstationSessionMode.LOCAL_LEDGER:
            raise ApplicationError(ErrorCode.CONFLICT, "Guest V2 access requires a V2 workstation")
        now = self._clock()
        grant = await self._grants.get_pending_for_workstation(workstation.id, now)
        if grant is None:
            raise ApplicationError(ErrorCode.NOT_FOUND, "No pending guest access grant")
        if grant.redeemed:
            existing_session = await self._sessions._repository.get(grant.session_id)
            if existing_session is None or existing_session.status is not SessionStatus.ACTIVE:
                raise ApplicationError(ErrorCode.CONFLICT, "Guest access grant is no longer active")
            return self._decode(grant)
        payment = await self._payments.get(grant.payment_id)
        self._validate_payment(payment)
        session = await self._sessions.start(
            workstation_id=workstation.id,
            client_id=None,
            guest_id=payment.guest_id,
            guest_name=payment.guest_name,
            created_by=f"guest-payment:{payment.id}",
            source=GUEST_SOURCE,
            idempotency_key=f"guest-v2-grant:{grant.id}",
            device_id=device_id,
            tariff_id=payment.tariff_id,
            tariff_quantity=payment.tariff_quantity,
            guest_payment_id=payment.id,
            persist=True,
        )
        payload = offline_session_snapshot_pb2.GuestSessionAccessPayload(
            grant_id=str(grant.id),
            schema_version=1,
            issued_at=self._timestamp(now),
            expires_at=self._timestamp(grant.expires_at),
            payment_id=str(payment.id),
            session_id=str(session.id),
            device_id=device_id,
            guest_name=payment.guest_name,
            tariff_id=str(payment.tariff_id),
            tariff_quantity=payment.tariff_quantity,
        )
        tariff = await self._sessions._tariffs.get_tariff(payment.tariff_id)
        if tariff is not None:
            payload.tariff_name = tariff.name
            payload.duration_minutes = tariff.duration_minutes
        if workstation.group_id and workstation.group_id.strip():
            payload.workstation_zone_id = workstation.group_id.strip()
        signed = offline_session_snapshot_pb2.SignedGuestSessionAccess(
            payload=payload,
            signing_key_id=self._signing_key_id,
            signature=self._signer.sign(payload.SerializeToString(deterministic=True)),
        )
        await self._grants.save(
            dataclasses.replace(
                grant,
                session_id=session.id,
                payload=payload.SerializeToString(deterministic=True),
                signature=bytes(signed.signature),
                signing_key_id=self._signing_key_id,
            )
        )
        return signed

    async def stop(self, device_id: str, session_id: uuid.UUID, payment_id: uuid.UUID) -> None:
        workstation = await self._workstations.get_by_device_id(device_id)
        session = await self._sessions._repository.get(session_id)
        if session is None or session.workstation_id != workstation.id:
            raise ApplicationError(ErrorCode.NOT_FOUND, "Guest session not found")
        if session.source != GUEST_SOURCE or session.guest_payment_id != payment_id:
            raise ApplicationError(ErrorCode.PERMISSION_DENIED, "Session is not a guest V2 session")
        await self._sessions.stop(session_id, device_id=device_id)

    @staticmethod
    def _validate_payment(payment: GuestSessionPayment | None) -> None:
        if payment is None:
            raise ApplicationError(ErrorCode.NOT_FOUND, "Guest payment not found")
        if payment.status is not DirectPaymentStatus.CONFIRMED:
            raise ApplicationError(ErrorCode.CONFLICT, "Guest payment is not confirmed")

    @staticmethod
    def _timestamp(value: datetime.datetime) -> timestamp_pb2.Timestamp:
        result = timestamp_pb2.Timestamp()
        result.FromDatetime(value)
        return result

    @staticmethod
    def _decode(grant: GuestAccessGrant) -> offline_session_snapshot_pb2.SignedGuestSessionAccess:
        payload = offline_session_snapshot_pb2.GuestSessionAccessPayload.FromString(
            grant.payload or b""
        )
        return offline_session_snapshot_pb2.SignedGuestSessionAccess(
            payload=payload,
            signing_key_id=grant.signing_key_id or "",
            signature=grant.signature or b"",
        )
