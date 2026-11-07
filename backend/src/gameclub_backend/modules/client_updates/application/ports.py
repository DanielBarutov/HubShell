from __future__ import annotations

import typing
import uuid

from gameclub_backend.modules.client_updates.domain import (
    ClientReleaseObservation,
    ClientReleasePolicy,
    Deployment,
)


class DeploymentRepository(typing.Protocol):
    async def create(self, deployment: Deployment) -> Deployment:
        """Create one active fleet deployment or return a content-matching repeat."""

    async def publish_policy(self, policy: ClientReleasePolicy) -> ClientReleasePolicy:
        """Persist an idempotent policy change, serialized with job creation."""

    def policy_change(self) -> typing.AsyncContextManager[None]:
        """Hold deployment serialization and transaction while changing admission policy."""

    async def observe_release(
        self, device_id: str, workstation_id: uuid.UUID, installation_id: str, release_id: str
    ) -> None:
        """Store the current GUI release, bound to the active installation."""

    async def running_release(
        self, device_id: str, workstation_id: uuid.UUID, installation_id: str
    ) -> str | None:
        """Return the current installation's recent independently reported GUI release."""

    async def current_policy(self) -> ClientReleasePolicy | None:
        """Read the latest approved client release and explicit compatibility list."""

    async def assign_current(self, device_id: str, workstation_id: uuid.UUID) -> Deployment | None:
        """Keep an unfinished job or create one from the current policy atomically."""

    async def get(self, deployment_id: uuid.UUID) -> Deployment | None:
        """Read a durable deployment report."""

    async def latest_for_devices(self, device_ids: tuple[str, ...]) -> dict[str, Deployment]:
        """Read the latest job for each device without loading unbounded delivery history."""

    async def release_observations(
        self, device_ids: tuple[str, ...]
    ) -> dict[str, ClientReleaseObservation]:
        """Read independent GUI observations for the operator's fleet status."""

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
