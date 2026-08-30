import dataclasses

import redis.asyncio as redis_asyncio
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from gameclub_backend.application.health import HealthCheck
from gameclub_backend.config import Settings


class PostgresHealthCheck:
    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def check(self) -> bool:
        try:
            async with self._engine.connect() as connection:
                await connection.exec_driver_sql("SELECT 1")
        except Exception:
            return False
        return True


class RedisHealthCheck:
    def __init__(self, client: redis_asyncio.Redis) -> None:
        self._client = client

    async def check(self) -> bool:
        try:
            return bool(await self._client.ping())
        except Exception:
            return False


@dataclasses.dataclass
class InfrastructureResources:
    checks: dict[str, HealthCheck]
    engine: AsyncEngine | None = None
    redis: redis_asyncio.Redis | None = None

    async def close(self) -> None:
        if self.redis is not None:
            await self.redis.aclose()
        if self.engine is not None:
            await self.engine.dispose()


def create_resources(settings: Settings) -> InfrastructureResources:
    engine = None
    redis_client = None
    checks: dict[str, HealthCheck] = {}

    if settings.postgres_dsn:
        engine = create_async_engine(settings.postgres_dsn, pool_pre_ping=True)
        checks["postgres"] = PostgresHealthCheck(engine)

    if settings.redis_url:
        redis_client = redis_asyncio.from_url(settings.redis_url, decode_responses=True)
        checks["redis"] = RedisHealthCheck(redis_client)

    return InfrastructureResources(checks=checks, engine=engine, redis=redis_client)
