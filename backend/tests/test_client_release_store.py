"""Pinned signing key and immutable archive verification before release assignment."""

import hashlib
import json
import zipfile

import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from gameclub_backend.application.errors import ApplicationError
from gameclub_backend.modules.client_updates.infrastructure.releases import LocalClientReleaseStore


def signed_release(root, release_id="signed-v1", **overrides):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_key = root / "trusted.pem"
    public_key.write_bytes(
        key.public_key().public_bytes(
            serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
        )
    )
    directory = root / release_id
    directory.mkdir()
    executable = b"test executable"
    archive = directory / "HubShell.zip"
    with zipfile.ZipFile(archive, "w") as output:
        output.writestr("HubShell.exe", executable)
    value = {
        "schemaVersion": 1,
        "releaseId": release_id,
        "runtime": "win-x64",
        "executableName": "HubShell.exe",
        "executableBytes": len(executable),
        "executableSha256": hashlib.sha256(executable).hexdigest(),
        "archiveBytes": archive.stat().st_size,
        "archiveSha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
        "minBackendProtocol": 1,
        "maxBackendProtocol": 1,
        "minUpdaterProtocol": 1,
        "maxUpdaterProtocol": 1,
        **overrides,
    }
    manifest = json.dumps(value).encode()
    (directory / "release.json").write_bytes(manifest)
    (directory / "release.json.sig").write_bytes(
        key.sign(manifest, padding.PKCS1v15(), hashes.SHA256())
    )
    return value, LocalClientReleaseStore(str(root), str(public_key))


async def test_release_store_verifies_signature_and_archive(tmp_path):
    """Полный пакет с закреплённой подписью возвращает хеш EXE из проверенного архива."""
    metadata, store = signed_release(tmp_path)
    assert await store.executable_hash("signed-v1") == metadata["executableSha256"]


@pytest.mark.parametrize("name", ["release.json", "release.json.sig", "HubShell.zip"])
async def test_release_store_rejects_tampered_files(tmp_path, name):
    """Подмена описания, подписи или архива запрещает назначение выпуска."""
    _, store = signed_release(tmp_path)
    path = tmp_path / "signed-v1" / name
    path.write_bytes(path.read_bytes() + b"tampered")
    with pytest.raises(ApplicationError, match="verification failed"):
        await store.executable_hash("signed-v1")


@pytest.mark.parametrize(
    "changes",
    [
        {"minBackendProtocol": 2},
        {"maxUpdaterProtocol": 0},
        {"executableSha256": "a" * 64},
        {"archiveBytes": 1},
        {"releaseId": "another-release"},
        {"runtime": "linux-x64"},
    ],
)
async def test_release_store_rejects_signed_but_invalid_package(tmp_path, changes):
    """Даже подписанный пакет нельзя назначить при несовместимости или неверных метаданных."""
    _, store = signed_release(tmp_path, **changes)
    with pytest.raises(ApplicationError, match="verification failed"):
        await store.executable_hash("signed-v1")


async def test_release_store_rejects_links_and_unconfigured_key(tmp_path):
    """Ссылка на архив и отсутствие закреплённого ключа не разрешают назначение."""
    _, store = signed_release(tmp_path)
    archive = tmp_path / "signed-v1" / "HubShell.zip"
    original = tmp_path / "original.zip"
    archive.rename(original)
    archive.symlink_to(original)
    with pytest.raises(ApplicationError, match="verification failed"):
        await store.executable_hash("signed-v1")
    with pytest.raises(ApplicationError, match="not configured"):
        await LocalClientReleaseStore(str(tmp_path), None).executable_hash("signed-v1")


async def test_release_store_rejects_client_from_another_running_server(tmp_path):
    """Даже доверенный пакет другого server release не становится целевым выпуском ПК."""
    _, _ = signed_release(tmp_path)
    store = LocalClientReleaseStore(str(tmp_path), str(tmp_path / "trusted.pem"), "another-server")
    with pytest.raises(ApplicationError, match="differs from the running server"):
        await store.executable_hash("signed-v1")
