import datetime
import json
import typing

import redis.asyncio as redis_asyncio

from gameclub_backend.modules.auth.domain import Principal, RefreshTokenRecord, SubjectType


class RedisRefreshTokenRepository:
    def __init__(self, client_provider: typing.Callable[[], redis_asyncio.Redis | None]) -> None:
        self._client_provider = client_provider

    async def save(
        self,
        token_hash: str,
        principal: Principal,
        expires_at: datetime.datetime,
    ) -> None:
        client = self._require_client()
        ttl = max(1, int((expires_at - datetime.datetime.now(datetime.UTC)).total_seconds()))
        payload = {
            "subject_id": principal.subject_id,
            "subject_type": principal.subject_type.value,
            "roles": sorted(principal.roles),
            "permissions": sorted(principal.permissions),
            "expires_at": expires_at.isoformat(),
        }
        await client.set(f"gameclub:auth:refresh:{token_hash}", json.dumps(payload), ex=ttl)

    async def consume(
        self,
        token_hash: str,
        now: datetime.datetime,
    ) -> RefreshTokenRecord | None:
        client = self._require_client()
        raw = await client.getdel(f"gameclub:auth:refresh:{token_hash}")
        if raw is None:
            return None
        payload = json.loads(raw)
        expires_at = datetime.datetime.fromisoformat(payload["expires_at"])
        if expires_at <= now:
            return None
        return RefreshTokenRecord(
            principal=Principal(
                subject_id=payload["subject_id"],
                subject_type=SubjectType(payload["subject_type"]),
                roles=frozenset(payload["roles"]),
                permissions=frozenset(payload["permissions"]),
            ),
            expires_at=expires_at,
        )

    async def revoke(self, token_hash: str) -> None:
        client = self._require_client()
        await client.delete(f"gameclub:auth:refresh:{token_hash}")

    def _require_client(self) -> redis_asyncio.Redis:
        client = self._client_provider()
        if client is None:
            raise RuntimeError("Redis refresh-token repository is not configured")
        return client
