import datetime
import json
import typing
import uuid

import redis.asyncio as redis_asyncio

from gameclub_backend.modules.workstations.domain import Workstation, WorkstationStatus

RedisProvider = typing.Callable[[], redis_asyncio.Redis | None]


class RedisWorkstationSnapshotCache:
    _key = "gameclub:workstations:snapshot:v1"

    def __init__(self, redis_provider: RedisProvider) -> None:
        self._redis_provider = redis_provider

    async def get(self) -> list[Workstation] | None:
        client = self._redis_provider()
        if client is None:
            return None
        try:
            raw = await client.get(self._key)
            if raw is None:
                return None
            payload = json.loads(raw)
            if not isinstance(payload, list):
                return None
            return [self._from_payload(item) for item in payload]
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            return None
        except Exception:
            # Redis is an optimization for the operator map, never its source
            # of truth. A Redis outage falls back to PostgreSQL on this request.
            return None

    async def set(self, workstations: list[Workstation], ttl_seconds: int) -> None:
        client = self._redis_provider()
        if client is None:
            return
        payload = json.dumps(
            [self._to_payload(workstation) for workstation in workstations],
            separators=(",", ":"),
        )
        try:
            await client.set(self._key, payload, ex=ttl_seconds)
        except Exception:
            return

    async def invalidate(self) -> None:
        client = self._redis_provider()
        if client is None:
            return
        try:
            await client.delete(self._key)
        except Exception:
            return

    @staticmethod
    def _to_payload(workstation: Workstation) -> dict[str, typing.Any]:
        return {
            "id": str(workstation.id),
            "device_id": workstation.device_id,
            "name": workstation.name,
            "group_id": workstation.group_id,
            "position": workstation.position,
            "status": workstation.status.value,
            "last_seen_at": (
                workstation.last_seen_at.isoformat() if workstation.last_seen_at else None
            ),
            "client_version": workstation.client_version,
            "disabled_reason": workstation.disabled_reason,
            "capabilities": list(workstation.capabilities),
            "theme": workstation.theme,
            "archived_at": workstation.archived_at.isoformat() if workstation.archived_at else None,
        }

    @staticmethod
    def _from_payload(payload: typing.Any) -> Workstation:
        if not isinstance(payload, dict):
            raise ValueError("Invalid workstation cache item")

        def parse_datetime(value: typing.Any) -> datetime.datetime | None:
            return datetime.datetime.fromisoformat(value) if value is not None else None

        capabilities = payload.get("capabilities", [])
        if not isinstance(capabilities, list) or any(
            not isinstance(item, str) for item in capabilities
        ):
            raise ValueError("Invalid workstation capabilities")
        return Workstation(
            id=uuid.UUID(str(payload["id"])),
            device_id=str(payload["device_id"]),
            name=str(payload["name"]),
            group_id=payload.get("group_id"),
            position=payload.get("position"),
            status=WorkstationStatus(str(payload["status"])),
            last_seen_at=parse_datetime(payload.get("last_seen_at")),
            client_version=payload.get("client_version"),
            disabled_reason=payload.get("disabled_reason"),
            capabilities=tuple(capabilities),
            theme=str(payload.get("theme", "standard")),
            archived_at=parse_datetime(payload.get("archived_at")),
        )
