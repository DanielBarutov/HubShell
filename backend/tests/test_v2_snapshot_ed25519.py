import base64

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from gameclub_backend.config import Settings
from gameclub_backend.modules.eventing_v2.infrastructure.snapshot_ed25519 import (
    V2Ed25519SnapshotSigner,
    create_v2_snapshot_signer,
)


def test_v2_ed25519_snapshot_signer_matches_standard_test_vector() -> None:
    """Проверяет заявленное поведение backend."""
    signer = V2Ed25519SnapshotSigner("nWGxne/9WmC6hEr0kuwsxERJxWl7MmkZcDusAxyuf2A=")

    signature = signer.sign(b"")

    assert signature.hex() == (
        "e5564300c360ac729086e2cc806e828a84877f1eb8e5d974d873e06522490155"
        "5fb8821590a33bacc61e39701cf9b46bd25bf5f0595bbe24655141438e7a100b"
    )
    public_key = Ed25519PublicKey.from_public_bytes(
        bytes.fromhex("d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a")
    )
    public_key.verify(signature, b"")


def test_v2_snapshot_signer_loads_only_configured_private_key() -> None:
    """Проверяет заявленное поведение backend."""
    signing_key_id, signer = create_v2_snapshot_signer(
        Settings(
            v2_snapshot_signing_key_id="club-key-2026-01",
            v2_snapshot_signing_private_key_b64=base64.b64encode(bytes(range(32))).decode(),
        )
    )

    assert signing_key_id == "club-key-2026-01"
    assert len(signer.sign(b"snapshot")) == 64


@pytest.mark.parametrize("private_key", ["not-base64", base64.b64encode(b"short").decode()])
def test_v2_snapshot_signer_rejects_invalid_private_key(private_key: str) -> None:
    """Проверяет заявленное поведение backend."""
    with pytest.raises(ValueError, match="V2 snapshot"):
        V2Ed25519SnapshotSigner(private_key)
