from __future__ import annotations

import datetime
import uuid

from sqlalchemy import JSON, DateTime, String, select, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from gameclub_backend.infrastructure.database import EngineProvider, open_session
from gameclub_backend.modules.reservations.domain import Reservation, ReservationStatus


class ReservationBase(DeclarativeBase):
    pass


class ReservationModel(ReservationBase):
    __tablename__ = "reservations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    workstation_ids: Mapped[list[str]] = mapped_column(JSON)
    client_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
        index=True,
    )
    guest_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    guest_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True, index=True
    )
    start_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), index=True)
    end_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), index=True)
    status: Mapped[str] = mapped_column(String(32), index=True)
    notes: Mapped[str | None] = mapped_column(String(500), nullable=True)
    tariff_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    created_by: Mapped[str] = mapped_column(String(128))
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True))
    cancelled_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    idempotency_key: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
        unique=True,
        index=True,
    )

    def to_domain(self) -> Reservation:
        return Reservation(
            id=self.id,
            workstation_ids=tuple(uuid.UUID(value) for value in self.workstation_ids),
            client_id=self.client_id,
            guest_name=self.guest_name,
            guest_id=self.guest_id,
            start_at=self.start_at,
            end_at=self.end_at,
            status=ReservationStatus(self.status),
            notes=self.notes,
            tariff_id=self.tariff_id,
            created_by=self.created_by,
            created_at=self.created_at,
            cancelled_at=self.cancelled_at,
            idempotency_key=self.idempotency_key,
        )

    @classmethod
    def from_domain(cls, reservation: Reservation) -> ReservationModel:
        return cls(
            id=reservation.id,
            workstation_ids=[str(value) for value in reservation.workstation_ids],
            client_id=reservation.client_id,
            guest_name=reservation.guest_name,
            guest_id=reservation.guest_id,
            start_at=reservation.start_at,
            end_at=reservation.end_at,
            status=reservation.status.value,
            notes=reservation.notes,
            tariff_id=reservation.tariff_id,
            created_by=reservation.created_by,
            created_at=reservation.created_at,
            cancelled_at=reservation.cancelled_at,
            idempotency_key=reservation.idempotency_key,
        )


class PostgresReservationRepository:
    def __init__(self, engine_provider: EngineProvider) -> None:
        self._engine_provider = engine_provider

    async def get(self, reservation_id: uuid.UUID) -> Reservation | None:
        async with open_session(self._engine_provider) as session:
            model = await session.get(ReservationModel, reservation_id)
            return model.to_domain() if model else None

    async def get_by_idempotency_key(self, idempotency_key: str) -> Reservation | None:
        async with open_session(self._engine_provider) as session:
            model = await session.scalar(
                select(ReservationModel).where(ReservationModel.idempotency_key == idempotency_key)
            )
            return model.to_domain() if model else None

    async def list(
        self,
        start_at: datetime.datetime,
        end_at: datetime.datetime,
    ) -> list[Reservation]:
        async with open_session(self._engine_provider) as session:
            result = await session.scalars(
                select(ReservationModel)
                .where(
                    ReservationModel.start_at < end_at,
                    ReservationModel.end_at > start_at,
                )
                .order_by(ReservationModel.start_at)
            )
            return [model.to_domain() for model in result]

    async def list_for_client(
        self,
        client_id: uuid.UUID,
        start_at: datetime.datetime,
        limit: int,
    ) -> list[Reservation]:
        async with open_session(self._engine_provider) as session:
            result = await session.scalars(
                select(ReservationModel)
                .where(
                    ReservationModel.client_id == client_id,
                    ReservationModel.status == ReservationStatus.CONFIRMED.value,
                    ReservationModel.start_at >= start_at,
                )
                .order_by(ReservationModel.start_at, ReservationModel.id)
                .limit(limit)
            )
            return [model.to_domain() for model in result]

    async def list_pending_no_show(self, cutoff_at: datetime.datetime) -> list[Reservation]:
        async with open_session(self._engine_provider) as session:
            result = await session.scalars(
                select(ReservationModel)
                .where(
                    ReservationModel.status == ReservationStatus.CONFIRMED.value,
                    ReservationModel.start_at <= cutoff_at,
                )
                .order_by(ReservationModel.start_at)
            )
            return [model.to_domain() for model in result]

    async def mark_no_show_if_eligible(
        self,
        reservation_id: uuid.UUID,
        now: datetime.datetime,
        grace_period_minutes: int,
    ) -> Reservation | None:
        async with open_session(self._engine_provider) as session:
            async with session.begin():
                model = await session.scalar(
                    select(ReservationModel)
                    .where(ReservationModel.id == reservation_id)
                    .with_for_update()
                )
                if model is None or model.status != ReservationStatus.CONFIRMED.value:
                    return None
                try:
                    updated = model.to_domain().mark_no_show(now, grace_period_minutes)
                except ValueError:
                    return None
                self._copy_values(model, updated)
                return updated

    async def save(self, reservation: Reservation) -> Reservation:
        async with open_session(self._engine_provider) as session:
            async with session.begin():
                model = await session.get(ReservationModel, reservation.id)
                if model is not None:
                    resource_ids = sorted(
                        set(model.workstation_ids)
                        | {str(value) for value in reservation.workstation_ids}
                    )
                    for workstation_id in resource_ids:
                        await session.execute(
                            text("SELECT pg_advisory_xact_lock(hashtext(:lock_key))"),
                            {"lock_key": f"reservation-resource:{workstation_id}"},
                        )
                    if reservation.status in {
                        ReservationStatus.CONFIRMED,
                        ReservationStatus.ACTIVE,
                    }:
                        overlapping = await session.scalars(
                            select(ReservationModel).where(
                                ReservationModel.id != reservation.id,
                                ReservationModel.start_at < reservation.end_at,
                                ReservationModel.end_at > reservation.start_at,
                                ReservationModel.status.in_(
                                    [
                                        ReservationStatus.CONFIRMED.value,
                                        ReservationStatus.ACTIVE.value,
                                    ]
                                ),
                            )
                        )
                        requested_resources = set(
                            str(value) for value in reservation.workstation_ids
                        )
                        if any(
                            requested_resources.intersection(item.workstation_ids)
                            for item in overlapping
                        ):
                            raise ValueError("Workstation is already reserved for this period")
                    self._copy_values(model, reservation)
                    return reservation

                if reservation.idempotency_key:
                    await session.execute(
                        text("SELECT pg_advisory_xact_lock(hashtext(:lock_key))"),
                        {"lock_key": f"reservation-key:{reservation.idempotency_key}"},
                    )
                    repeated = await session.scalar(
                        select(ReservationModel).where(
                            ReservationModel.idempotency_key == reservation.idempotency_key
                        )
                    )
                    if repeated is not None:
                        return repeated.to_domain()

                resource_ids = sorted(str(value) for value in reservation.workstation_ids)
                for workstation_id in resource_ids:
                    await session.execute(
                        text("SELECT pg_advisory_xact_lock(hashtext(:lock_key))"),
                        {"lock_key": f"reservation-resource:{workstation_id}"},
                    )

                active_statuses = [
                    ReservationStatus.CONFIRMED.value,
                    ReservationStatus.ACTIVE.value,
                ]
                overlapping = await session.scalars(
                    select(ReservationModel).where(
                        ReservationModel.start_at < reservation.end_at,
                        ReservationModel.end_at > reservation.start_at,
                        ReservationModel.status.in_(active_statuses),
                    )
                )
                requested_resources = set(resource_ids)
                if any(
                    requested_resources.intersection(item.workstation_ids) for item in overlapping
                ):
                    raise ValueError("Workstation is already reserved for this period")

                session.add(ReservationModel.from_domain(reservation))
                return reservation

    @staticmethod
    def _copy_values(model: ReservationModel, reservation: Reservation) -> None:
        values = ReservationModel.from_domain(reservation).__dict__
        for key, value in values.items():
            if not key.startswith("_"):
                setattr(model, key, value)
