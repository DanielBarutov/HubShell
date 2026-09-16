from __future__ import annotations

import asyncio
import typing

import redis.asyncio as redis_asyncio

RedisProvider = typing.Callable[[], redis_asyncio.Redis | None]


class RedisCommandNotifier:
    """Cross-process wake-up channel for the durable workstation command queue."""

    _channel_prefix = "gameclub:workstations:commands:v1:"

    def __init__(self, redis_provider: RedisProvider) -> None:
        self._redis_provider = redis_provider

    async def notify(self, device_id: str) -> None:
        client = self._redis_provider()
        if client is None:
            return
        try:
            await client.publish(self._channel(device_id), "ready")
        except Exception:
            # PostgreSQL remains the source of truth. A Redis outage only turns
            # this into the bounded polling fallback in WorkstationCommandService.
            return

    async def wait(self, device_id: str, timeout_seconds: float = 15.0) -> None:
        client = self._redis_provider()
        if client is None:
            await asyncio.sleep(timeout_seconds)
            return

        pubsub = client.pubsub()
        channel = self._channel(device_id)
        try:
            await pubsub.subscribe(channel)
            deadline = asyncio.get_running_loop().time() + timeout_seconds
            while True:
                remaining = deadline - asyncio.get_running_loop().time()
                if remaining <= 0:
                    return
                message = await pubsub.get_message(
                    ignore_subscribe_messages=True,
                    timeout=min(remaining, 1.0),
                )
                if message is not None:
                    return
        except Exception:
            return
        finally:
            try:
                await pubsub.unsubscribe(channel)
            finally:
                await pubsub.close()

    @classmethod
    def _channel(cls, device_id: str) -> str:
        return f"{cls._channel_prefix}{device_id.strip()}"
