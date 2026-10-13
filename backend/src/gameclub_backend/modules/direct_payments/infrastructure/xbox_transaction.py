import asyncio
import contextlib
import typing
import uuid

from sqlalchemy import text

from gameclub_backend.infrastructure.database import EngineProvider, application_transaction


class PostgresXboxTransaction:
    def __init__(self, provider: EngineProvider) -> None:
        self._provider = provider

    @contextlib.asynccontextmanager
    async def __call__(self, workstation_id: uuid.UUID) -> typing.AsyncIterator[None]:
        async with application_transaction(self._provider) as session:
            await session.execute(
                text("SELECT pg_advisory_xact_lock(hashtext(:key))"),
                {"key": f"gaming-session-workstation:{workstation_id}"},
            )
            yield


class MemoryXboxTransaction:
    """Serializes developer-host requests; production uses a PostgreSQL transaction."""

    def __init__(self) -> None:
        self._lock = asyncio.Lock()

    @contextlib.asynccontextmanager
    async def __call__(self, workstation_id: uuid.UUID) -> typing.AsyncIterator[None]:
        async with self._lock:
            yield
