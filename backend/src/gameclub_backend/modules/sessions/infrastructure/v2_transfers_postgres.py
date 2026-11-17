from __future__ import annotations

import datetime
import typing
import uuid

from sqlalchemy import and_, exists, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from gameclub_backend.application.errors import ApplicationError, ErrorCode
from gameclub_backend.infrastructure.database import EngineProvider, open_session
from gameclub_backend.modules.sessions.application.ports import ClientReleaseAdmission
from gameclub_backend.modules.sessions.application.service import SessionService
from gameclub_backend.modules.sessions.application.v2_transfer import (
    TransferRightsWriter,
    V2TransferCheckpoint,
    V2TransferReservation,
    V2TransferStatus,
)
from gameclub_backend.modules.sessions.domain import SessionStatus
from gameclub_backend.modules.sessions.infrastructure.postgres import (
    PostgresSessionAdmission,
    SessionModel,
    V2TransferReservationModel,
    require_session_admission,
)


class PostgresV2TransferReservations:
    def __init__(
        self,
        engine_provider: EngineProvider,
        release_admission: ClientReleaseAdmission | None = None,
        sale_hold: typing.Callable[[uuid.UUID, uuid.UUID | None], typing.Awaitable[bool]]
        | None = None,
    ) -> None:
        self._engine_provider = engine_provider
        self._release_admission = release_admission
        self._sale_hold = sale_hold
        self._admission = PostgresSessionAdmission(engine_provider)

    async def list_reserved_targets(self) -> set[uuid.UUID]:
        async with open_session(self._engine_provider) as db:
            return set(
                await db.scalars(
                    select(V2TransferReservationModel.target_workstation_id).where(
                        V2TransferReservationModel.status == V2TransferStatus.PREPARING,
                        V2TransferReservationModel.expires_at > func.clock_timestamp(),
                    )
                )
            )

    async def expire_due(self) -> int:
        async with self._admission.policy_change(), open_session(self._engine_provider) as db:
            now = await db.scalar(select(func.clock_timestamp()))
            return await self._expire_due(db, now)

    @staticmethod
    async def _expire_due(db: AsyncSession, now: datetime.datetime) -> int:
        expired_ids = await db.scalars(
            update(V2TransferReservationModel)
            .where(
                V2TransferReservationModel.status == V2TransferStatus.PREPARING,
                V2TransferReservationModel.expires_at <= now,
            )
            .values(status=V2TransferStatus.EXPIRED)
            .returning(V2TransferReservationModel.operation_id)
        )
        return len(expired_ids.all())

    async def prepare(
        self,
        operation_id: uuid.UUID,
        session_id: uuid.UUID,
        source_workstation_id: uuid.UUID,
        target_workstation_id: uuid.UUID,
        quote_token: str | None = None,
    ) -> V2TransferReservation:
        if source_workstation_id == target_workstation_id:
            raise ApplicationError(
                ErrorCode.INVALID_ARGUMENT, "Transfer requires another workstation"
            )
        async with self._admission.policy_change(), open_session(self._engine_provider) as db:
            now = await db.scalar(select(func.clock_timestamp()))
            await self._expire_due(db, now)
            existing = await db.get(V2TransferReservationModel, operation_id)
            if existing is not None:
                if (
                    existing.session_id != session_id
                    or existing.source_workstation_id != source_workstation_id
                    or existing.target_workstation_id != target_workstation_id
                    or existing.quote_token != quote_token
                ):
                    raise ApplicationError(
                        ErrorCode.CONFLICT, "Transfer operation parameters changed"
                    )
                return existing.to_domain()

            source = await db.get(SessionModel, session_id)
            if (
                source is None
                or source.workstation_id != source_workstation_id
                or source.status != SessionStatus.ACTIVE.value
                or source.source
                not in (
                    SessionService.LOCAL_LEDGER_SOURCE,
                    SessionService.GUEST_LOCAL_LEDGER_SOURCE,
                )
            ):
                raise ApplicationError(ErrorCode.CONFLICT, "Source must own the active V2 session")

            pending = await db.scalar(
                select(V2TransferReservationModel.operation_id).where(
                    V2TransferReservationModel.session_id == session_id,
                    V2TransferReservationModel.status == V2TransferStatus.PREPARING,
                )
            )
            if pending is not None:
                raise ApplicationError(ErrorCode.CONFLICT, "Session already has a pending transfer")
            await require_session_admission(db, target_workstation_id)
            await self._require_no_guest_sales(
                source_workstation_id, session_id, target_workstation_id
            )
            if self._release_admission is not None:
                await self._release_admission.require_release(target_workstation_id)
            active_target = await db.scalar(
                select(SessionModel.id).where(
                    SessionModel.workstation_id == target_workstation_id,
                    SessionModel.status == SessionStatus.ACTIVE.value,
                )
            )
            if active_target is not None:
                raise ApplicationError(
                    ErrorCode.CONFLICT, "Transfer target already has an active session"
                )

            reservation = V2TransferReservationModel(
                operation_id=operation_id,
                session_id=session_id,
                source_workstation_id=source_workstation_id,
                target_workstation_id=target_workstation_id,
                status=V2TransferStatus.PREPARING,
                expires_at=now + datetime.timedelta(seconds=60),
                target_ready=False,
                quote_token=quote_token,
            )
            db.add(reservation)
            return reservation.to_domain()

    async def cancel(
        self, operation_id: uuid.UUID, source_workstation_id: uuid.UUID
    ) -> V2TransferReservation:
        async with self._admission.policy_change(), open_session(self._engine_provider) as db:
            reservation = await db.get(V2TransferReservationModel, operation_id)
            if reservation is None or reservation.source_workstation_id != source_workstation_id:
                raise ApplicationError(ErrorCode.NOT_FOUND, "Transfer operation not found")
            await self._expire_if_due(db, reservation)
            if reservation.status == V2TransferStatus.PREPARING:
                reservation.status = V2TransferStatus.CANCELLED
            return reservation.to_domain()

    async def pending_for_target(
        self, target_workstation_id: uuid.UUID
    ) -> V2TransferReservation | None:
        async with open_session(self._engine_provider) as db:
            reservation = await db.scalar(
                select(V2TransferReservationModel)
                .where(
                    V2TransferReservationModel.target_workstation_id == target_workstation_id,
                    or_(
                        and_(
                            V2TransferReservationModel.status == V2TransferStatus.PREPARING,
                            V2TransferReservationModel.expires_at > func.clock_timestamp(),
                        ),
                        and_(
                            V2TransferReservationModel.status == V2TransferStatus.COMMITTED,
                            exists().where(
                                SessionModel.id == V2TransferReservationModel.session_id,
                                SessionModel.workstation_id == target_workstation_id,
                                SessionModel.status == SessionStatus.ACTIVE.value,
                            ),
                        ),
                    ),
                )
                .order_by(
                    V2TransferReservationModel.expires_at.desc(),
                    V2TransferReservationModel.operation_id.desc(),
                )
                .limit(1)
            )
            return reservation.to_domain() if reservation is not None else None

    async def get_for_workstation(
        self, operation_id: uuid.UUID, workstation_id: uuid.UUID
    ) -> V2TransferReservation:
        async with self._admission.policy_change(), open_session(self._engine_provider) as db:
            reservation = await db.get(V2TransferReservationModel, operation_id)
            if reservation is None or workstation_id not in (
                reservation.source_workstation_id,
                reservation.target_workstation_id,
            ):
                raise ApplicationError(ErrorCode.NOT_FOUND, "Transfer operation not found")
            await self._expire_if_due(db, reservation)
            return reservation.to_domain()

    async def ready_target(
        self, operation_id: uuid.UUID, target_workstation_id: uuid.UUID
    ) -> V2TransferReservation:
        async with self._admission.policy_change(), open_session(self._engine_provider) as db:
            reservation = await db.get(V2TransferReservationModel, operation_id)
            if reservation is None or reservation.target_workstation_id != target_workstation_id:
                raise ApplicationError(ErrorCode.NOT_FOUND, "Transfer operation not found")
            await self._expire_if_due(db, reservation)
            if reservation.status == V2TransferStatus.PREPARING:
                reservation.target_ready = True
            return reservation.to_domain()

    async def record_source_checkpoint(
        self,
        operation_id: uuid.UUID,
        source_workstation_id: uuid.UUID,
        checkpoint: V2TransferCheckpoint,
    ) -> V2TransferReservation:
        """Store the source position; commit must compare it with the confirmed event chain."""
        async with self._admission.policy_change(), open_session(self._engine_provider) as db:
            reservation = await db.get(V2TransferReservationModel, operation_id)
            if reservation is None or reservation.source_workstation_id != source_workstation_id:
                raise ApplicationError(ErrorCode.NOT_FOUND, "Transfer operation not found")
            await self._expire_if_due(db, reservation)
            if reservation.status == V2TransferStatus.PREPARING:
                if reservation.source_sequence is not None and (
                    reservation.source_sequence != checkpoint.sequence
                    or reservation.source_payload_hash != checkpoint.payload_hash
                ):
                    raise ApplicationError(ErrorCode.CONFLICT, "Transfer checkpoint changed")
                reservation.source_sequence = checkpoint.sequence
                reservation.source_payload_hash = checkpoint.payload_hash
            return reservation.to_domain()

    async def commit(
        self,
        operation_id: uuid.UUID,
        source_workstation_id: uuid.UUID,
        apply_rights: TransferRightsWriter,
    ) -> V2TransferReservation:
        # The caller must first serialize the event chain in the ambient transaction.
        async with self._admission.policy_change(), open_session(self._engine_provider) as db:
            reservation = await db.get(V2TransferReservationModel, operation_id)
            if reservation is None or reservation.source_workstation_id != source_workstation_id:
                raise ApplicationError(ErrorCode.NOT_FOUND, "Transfer operation not found")
            await self._expire_if_due(db, reservation)
            operation = reservation.to_domain()
            if operation.status is not V2TransferStatus.PREPARING:
                return operation
            if not operation.target_ready or operation.source_checkpoint is None:
                raise ApplicationError(ErrorCode.CONFLICT, "Transfer devices are not ready")

            source = await db.get(SessionModel, operation.session_id, with_for_update=True)
            if (
                source is None
                or source.workstation_id != source_workstation_id
                or source.status != SessionStatus.ACTIVE.value
                or source.source not in SessionService.LOCAL_SOURCES
            ):
                raise ApplicationError(ErrorCode.CONFLICT, "Source must own the active V2 session")
            target_id = operation.target_workstation_id
            await require_session_admission(db, target_id, transfer_id=operation_id)
            await self._require_no_guest_sales(
                source_workstation_id, operation.session_id, target_id
            )
            if self._release_admission is not None:
                await self._release_admission.require_release(target_id)
            if (
                await db.scalar(
                    select(SessionModel.id).where(
                        SessionModel.workstation_id == target_id,
                        SessionModel.status == SessionStatus.ACTIVE.value,
                    )
                )
                is not None
            ):
                raise ApplicationError(
                    ErrorCode.CONFLICT, "Transfer target already has an active session"
                )

            billing_boundary = await apply_rights(operation, source.to_domain())
            now = await db.scalar(select(func.clock_timestamp()))
            if now >= reservation.expires_at:
                raise ApplicationError(ErrorCode.CONFLICT, "Transfer deadline passed during commit")
            if billing_boundary is not None and now >= billing_boundary:
                raise ApplicationError(
                    ErrorCode.CONFLICT, "Billing boundary passed during transfer"
                )
            source.workstation_id = target_id
            reservation.status = V2TransferStatus.COMMITTED
            return reservation.to_domain()

    async def _require_no_guest_sales(
        self, source_id: uuid.UUID, session_id: uuid.UUID, target_id: uuid.UUID
    ) -> None:
        if self._sale_hold is not None and (
            await self._sale_hold(target_id, None) or await self._sale_hold(source_id, session_id)
        ):
            raise ApplicationError(ErrorCode.CONFLICT, "A pending guest sale blocks the transfer")

    @staticmethod
    async def _expire_if_due(db: AsyncSession, reservation: V2TransferReservationModel) -> None:
        if reservation.status == V2TransferStatus.PREPARING:
            now = await db.scalar(select(func.clock_timestamp()))
            if reservation.expires_at <= now:
                reservation.status = V2TransferStatus.EXPIRED
