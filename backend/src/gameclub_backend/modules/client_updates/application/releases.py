"""Local release metadata used before assigning a signed client package."""

from __future__ import annotations

import typing


class ClientReleaseStore(typing.Protocol):
    async def executable_hash(self, release_id: str) -> str:
        """Verify the published package with the pinned key and return its EXE hash."""
