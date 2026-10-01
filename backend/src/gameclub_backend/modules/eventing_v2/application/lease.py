"""Выдача server-owned lease после будущего V2 login/snapshot use case."""

from __future__ import annotations

import dataclasses
import datetime
import typing
import uuid


@dataclasses.dataclass(frozen=True)
class V2SessionLease:
    session_id: uuid.UUID
    client_id: uuid.UUID
    device_id: str
    snapshot_id: uuid.UUID
    snapshot_version: int
    policy_version: str
    issued_at: datetime.datetime
    expires_at: datetime.datetime | None = None

    def __post_init__(self) -> None:
        device_id = self.device_id.strip()
        policy_version = self.policy_version.strip()
        if not device_id or not policy_version:
            raise ValueError("V2 lease device and policy version are required")
        if self.snapshot_version < 1:
            raise ValueError("V2 lease snapshot version must be positive")
        if self.issued_at.tzinfo is None:
            raise ValueError("V2 lease issue timestamp must include timezone")
        if self.expires_at is not None:
            if self.expires_at.tzinfo is None or self.expires_at <= self.issued_at:
                raise ValueError("V2 lease expiry must be after issue time")
        object.__setattr__(self, "device_id", device_id)
        object.__setattr__(self, "policy_version", policy_version)


class V2SessionLeaseRepository(typing.Protocol):
    async def issue_exclusively(self, lease: V2SessionLease) -> tuple[V2SessionLease, bool]:
        """Return lease and duplicate flag; do not silently replace an active lease."""


class V2SessionLeaseService:
    def __init__(self, repository: V2SessionLeaseRepository) -> None:
        self._repository = repository

    async def issue(self, lease: V2SessionLease) -> tuple[V2SessionLease, bool]:
        return await self._repository.issue_exclusively(lease)
