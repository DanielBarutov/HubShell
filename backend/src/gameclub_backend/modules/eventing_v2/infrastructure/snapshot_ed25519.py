"""Ed25519-подпись V2 snapshot с приватным ключом только на сервере."""

from __future__ import annotations

import base64
import binascii

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from gameclub_backend.config import Settings


class V2Ed25519SnapshotSigner:
    """Подписывает raw 32-byte Ed25519 seed из защищённой server configuration."""

    def __init__(self, private_key_b64: str) -> None:
        try:
            private_key_bytes = base64.b64decode(private_key_b64, validate=True)
        except (binascii.Error, ValueError) as error:
            raise ValueError("V2 snapshot private key must be base64") from error
        if len(private_key_bytes) != 32:
            raise ValueError("V2 snapshot Ed25519 private key must contain 32 bytes")
        self._private_key = Ed25519PrivateKey.from_private_bytes(private_key_bytes)

    def sign(self, payload: bytes) -> bytes:
        return self._private_key.sign(payload)


def create_v2_snapshot_signer(settings: Settings) -> tuple[str, V2Ed25519SnapshotSigner]:
    """Загрузить signer только из server secret, никогда не из JWT/client config."""
    signing_key_id = (settings.v2_snapshot_signing_key_id or "").strip()
    private_key_b64 = settings.v2_snapshot_signing_private_key_b64 or ""
    if not signing_key_id or not private_key_b64:
        raise RuntimeError("V2 snapshot signing key id and private key must be configured")
    return signing_key_id, V2Ed25519SnapshotSigner(private_key_b64)
