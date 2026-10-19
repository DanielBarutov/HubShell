from __future__ import annotations

import typing
import uuid

from gameclub_backend.modules.client_updates.domain import Deployment


class DeploymentRepository(typing.Protocol):
    async def create(self, deployment: Deployment) -> Deployment:
        """Create one active fleet deployment or return a content-matching repeat."""

    async def get(self, deployment_id: uuid.UUID) -> Deployment | None:
        """Read a durable deployment report."""

    async def latest(self) -> Deployment | None:
        """Read the most recent delivery for the operator status panel."""

    async def latest_for_device(self, device_id: str) -> Deployment | None:
        """Return the newest deployment including this device, even if completed."""

    def change(self, deployment_id: uuid.UUID) -> typing.AsyncContextManager[Deployment]:
        """Serialize a mutation and commit participating owner ports atomically."""


class ClientFactConfirmation(typing.Protocol):
    async def is_confirmed(
        self,
        device_id: str,
        session_id: uuid.UUID,
        last_sequence: int,
        last_payload_hash: str | None,
    ) -> bool:
        """Match the exact local checkpoint to server-confirmed financial facts."""
