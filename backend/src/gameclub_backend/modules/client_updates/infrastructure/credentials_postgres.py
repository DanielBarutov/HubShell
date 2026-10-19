from __future__ import annotations

import uuid

from sqlalchemy import String, delete
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from gameclub_backend.infrastructure.database import EngineProvider, begin_session, open_session
from gameclub_backend.modules.client_updates.application.identity import UpdaterCredential
from gameclub_backend.modules.client_updates.infrastructure.postgres import ClientUpdatesBase


class UpdaterCredentialModel(ClientUpdatesBase):
    __tablename__ = "client_updater_credentials"

    device_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, unique=True)
    workstation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    installation_id: Mapped[str] = mapped_column(String(128), nullable=False)
    secret_hash: Mapped[str] = mapped_column(String(64), nullable=False)


class PostgresUpdaterCredentialRepository:
    def __init__(self, engine_provider: EngineProvider) -> None:
        self._engine_provider = engine_provider

    async def get(self, device_id: str) -> UpdaterCredential | None:
        async with open_session(self._engine_provider) as transaction:
            row = await transaction.get(UpdaterCredentialModel, device_id)
            return (
                UpdaterCredential(
                    row.id, row.device_id, row.workstation_id, row.installation_id, row.secret_hash
                )
                if row
                else None
            )

    async def save(self, credential: UpdaterCredential) -> None:
        async with open_session(self._engine_provider) as transaction:
            async with begin_session(transaction):
                await transaction.merge(
                    UpdaterCredentialModel(
                        id=credential.id,
                        device_id=credential.device_id,
                        workstation_id=credential.workstation_id,
                        installation_id=credential.installation_id,
                        secret_hash=credential.secret_hash,
                    )
                )

    async def revoke(self, device_id: str) -> None:
        async with open_session(self._engine_provider) as transaction:
            async with begin_session(transaction):
                await transaction.execute(
                    delete(UpdaterCredentialModel).where(
                        UpdaterCredentialModel.device_id == device_id
                    )
                )
