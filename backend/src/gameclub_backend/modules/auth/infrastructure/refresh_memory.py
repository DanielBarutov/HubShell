import asyncio
import datetime

from gameclub_backend.modules.auth.domain import Principal, RefreshTokenRecord


class InMemoryRefreshTokenRepository:
    def __init__(self) -> None:
        self._items: dict[str, RefreshTokenRecord] = {}
        self._lock = asyncio.Lock()

    async def save(
        self,
        token_hash: str,
        principal: Principal,
        expires_at: datetime.datetime,
    ) -> None:
        async with self._lock:
            self._items[token_hash] = RefreshTokenRecord(principal, expires_at)

    async def consume(
        self,
        token_hash: str,
        now: datetime.datetime,
    ) -> RefreshTokenRecord | None:
        async with self._lock:
            record = self._items.pop(token_hash, None)
            if record is None or record.expires_at <= now:
                return None
            return record

    async def revoke(self, token_hash: str) -> None:
        async with self._lock:
            self._items.pop(token_hash, None)
