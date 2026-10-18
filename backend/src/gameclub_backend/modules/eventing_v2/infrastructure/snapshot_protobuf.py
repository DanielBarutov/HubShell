from __future__ import annotations

import typing

from gameclub.v2 import offline_session_snapshot_pb2


class V2OfflineSnapshotSigner(typing.Protocol):
    """Изолированный доступ к приватному ключу подписи server snapshot."""

    def sign(self, payload: bytes) -> bytes:
        """Вернуть подпись bytes детерминированного payload."""


def serialize_snapshot_payload(
    payload: offline_session_snapshot_pb2.OfflineSessionSnapshotPayload,
) -> bytes:
    """Получить единственные bytes, которые подписывает сервер и проверяет C#."""
    return payload.SerializeToString(deterministic=True)


def sign_offline_session_snapshot(
    payload: offline_session_snapshot_pb2.OfflineSessionSnapshotPayload,
    signing_key_id: str,
    signer: V2OfflineSnapshotSigner,
) -> offline_session_snapshot_pb2.SignedOfflineSessionSnapshot:
    """Создать transport wrapper, не передавая приватный ключ в код V2 use case."""
    if not signing_key_id.strip():
        raise ValueError("V2 snapshot signing key id is required")
    return offline_session_snapshot_pb2.SignedOfflineSessionSnapshot(
        payload=payload,
        signing_key_id=signing_key_id,
        signature=signer.sign(serialize_snapshot_payload(payload)),
    )
