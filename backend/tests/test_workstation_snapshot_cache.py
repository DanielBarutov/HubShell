import json
import uuid
from pathlib import Path

from gameclub_backend.modules.sessions.infrastructure.postgres import SessionModel
from gameclub_backend.modules.workstations.domain import (
    Workstation,
    WorkstationSessionMode,
)
from gameclub_backend.modules.workstations.infrastructure.cache_redis import (
    RedisWorkstationSnapshotCache,
)


def test_redis_workstation_snapshot_preserves_v2_session_mode() -> None:
    """Проверяет, что Redis-снимок сохраняет режим сессии рабочего места."""
    workstation = Workstation(
        id=uuid.uuid4(),
        device_id="device-v2",
        name="V2 PC",
        session_mode=WorkstationSessionMode.LOCAL_LEDGER,
    )

    restored = RedisWorkstationSnapshotCache._from_payload(
        RedisWorkstationSnapshotCache._to_payload(workstation)
    )

    assert restored.session_mode is WorkstationSessionMode.LOCAL_LEDGER
    assert RedisWorkstationSnapshotCache._key.endswith(":v2")


async def test_redis_workstation_snapshot_misses_when_session_mode_is_missing() -> None:
    """Проверяет, что старый формат кэша не подменяет режим сессии."""
    workstation = Workstation(
        id=uuid.uuid4(),
        device_id="device-v2",
        name="V2 PC",
        session_mode=WorkstationSessionMode.LOCAL_LEDGER,
    )
    payload = RedisWorkstationSnapshotCache._to_payload(workstation)
    del payload["session_mode"]

    class RedisClient:
        async def get(self, key: str) -> str:
            assert key.endswith(":v2")
            return json.dumps([payload])

    cache = RedisWorkstationSnapshotCache(lambda: RedisClient())

    assert await cache.get() is None


def test_workstation_v2_cutover_migration_uses_the_session_table_name() -> None:
    """Проверяет, что миграция блокирует реальную таблицу сессий."""
    migration_path = (
        Path(__file__).resolve().parents[1]
        / "alembic"
        / "versions"
        / "20261002_0071_workstation_v2_cutover.py"
    )
    migration = migration_path.read_text()
    session_table = SessionModel.__tablename__

    assert session_table == "gaming_sessions"
    assert f"LOCK TABLE workstations, {session_table}" in migration
    assert f"FROM {session_table}" in migration
