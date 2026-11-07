"""Resumable policy publication and Docker image matching; Docker/HTTP boundaries are simulated."""

import copy
import json
import runpy
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

from client_release import COMPONENTS, IMAGE_ROOT

module = runpy.run_path(str(Path(__file__).with_name("sync-client-release.py")))
publish = module["publish_assignment"]
require_bundle = module["require_running_bundle"]


class Backend:
    def __init__(self):
        self.policy = None
        self.posts = []
        self.lost = False
        self.ready = True
        self.concurrent = False

    def request(self, method, path, body=None):
        if path == "/health/ready":
            return {"status": "ready" if self.ready else "unavailable"}
        if method == "POST":
            self.posts.append(copy.deepcopy(body))
            self.policy = {
                **body,
                "executable_sha256": "a" * 64,
                "accepted_release_ids": sorted(
                    set([body["release_id"], *body["accepted_release_ids"]])
                ),
            }
            result = copy.deepcopy(self.policy)
            if self.concurrent:
                self.policy["operation_id"] = str(uuid.uuid4())
            if self.lost:
                self.lost = False
                raise ConnectionResetError("response lost")
            return result
        return {"policy": copy.deepcopy(self.policy)}


class ClientSyncTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.backend = Backend()
        self.bundle = {
            "client": {"releaseId": "v-new", "executableSha256": "a" * 64},
            "server": {
                "images": {
                    f"HUBSHELL_{key}_IMAGE": f"{IMAGE_ROOT}/{name}@sha256:{'a' * 64}"
                    for key, name in COMPONENTS.items()
                }
            },
        }

    def tearDown(self):
        self.temporary.cleanup()

    def test_publication_is_idempotent_and_records_compatibility(self):
        """Повтор не создаёт новую policy, совместимость и подтверждённый journal сохраняются."""
        first = publish(self.backend, self.bundle, self.root, ["v-old"])
        self.assertEqual(publish(self.backend, self.bundle, self.root, ["v-old"]), first)
        self.assertEqual(len(self.backend.posts), 1)
        self.assertEqual(first["accepted_release_ids"], ["v-new", "v-old"])
        self.assertTrue(json.loads((self.root / "assignment.json").read_bytes())["published"])

    def test_lost_response_resumes_without_duplicate_policy(self):
        """Потеря ответа не приводит к другому назначению при повторном запуске."""
        self.backend.lost = True
        with self.assertRaises(ConnectionResetError):
            publish(self.backend, self.bundle, self.root, [])
        saved = json.loads((self.root / "assignment.json").read_bytes())
        self.assertFalse(saved["published"])
        result = publish(self.backend, self.bundle, self.root, [])
        self.assertEqual(result["operation_id"], saved["operation_id"])
        self.assertEqual(len(self.backend.posts), 1)

    def test_unhealthy_backend_never_publishes(self):
        """Неготовый backend не получает назначение и не создаёт journal успешной доставки."""
        self.backend.ready = False
        with self.assertRaises(ValueError):
            publish(self.backend, self.bundle, self.root, [])
        self.assertEqual(self.backend.posts, [])
        self.assertFalse((self.root / "assignment.json").exists())

    def test_pending_assignment_cannot_change_compatibility(self):
        """Неподтверждённый journal нельзя подменить другим списком совместимости."""
        self.backend.lost = True
        with self.assertRaises(ConnectionResetError):
            publish(self.backend, self.bundle, self.root, [])
        self.backend.policy = None
        with self.assertRaises(ValueError, msg="Pending compatibility cannot be replaced"):
            publish(self.backend, self.bundle, self.root, ["v-old"])

    def test_concurrent_policy_change_is_not_marked_published(self):
        """Конкурентная смена policy не записывается как успешная публикация."""
        self.backend.concurrent = True
        with self.assertRaises(ValueError):
            publish(self.backend, self.bundle, self.root, [])
        self.assertFalse(json.loads((self.root / "assignment.json").read_bytes())["published"])

    def containers(self):
        services = {
            "backend-http": "BACKEND",
            "backend-grpc": "BACKEND",
            "frontend": "FRONTEND",
            "steam-guest-server": "STEAM_GUEST",
        }
        return [
            {
                "Config": {
                    "Image": self.bundle["server"]["images"][f"HUBSHELL_{component}_IMAGE"],
                    "Labels": {"com.docker.compose.service": name},
                },
                "Image": component,
                "State": {"Running": True, "Health": {"Status": "healthy"}},
            }
            for name, component in services.items()
        ]

    def image(self, *args):
        return [
            {
                "RepoDigests": [self.bundle["server"]["images"][f"HUBSHELL_{args[-1]}_IMAGE"]],
                "Config": {"Labels": {"io.hubshell.release-id": "v-new"}},
            }
        ]

    def test_only_running_images_from_signed_release_are_accepted(self):
        """Смешанные, нездоровые и неполные стеки не разрешают раздачу клиентского выпуска."""
        containers = self.containers()
        with patch.dict(require_bundle.__globals__, docker_json=self.image):
            require_bundle(containers, self.bundle)
            for problem in ("unhealthy", "wrong_component", "missing", "unsigned"):
                changed = copy.deepcopy(containers)
                if problem == "unhealthy":
                    changed[0]["State"]["Health"]["Status"] = "unhealthy"
                elif problem == "wrong_component":
                    changed[0]["Config"]["Image"] = changed[-1]["Config"]["Image"]
                elif problem == "missing":
                    changed.pop()
                else:
                    changed[0]["Config"]["Image"] = "backend:latest"
                with self.subTest(problem=problem), self.assertRaises(ValueError):
                    require_bundle(changed, self.bundle)

    def test_historical_migration_and_oneoff_containers_do_not_block_current_stack(self):
        """Завершённая миграция и прежний oneoff не подменяют образ действующего приложения."""
        containers = self.containers()
        for labels in (
            {"com.docker.compose.service": "backend-migrate"},
            {"com.docker.compose.service": "worker", "com.docker.compose.oneoff": "True"},
        ):
            containers.append(
                {
                    "Config": {
                        "Image": f"{IMAGE_ROOT}/backend@sha256:{'b' * 64}",
                        "Labels": labels,
                    },
                    "Image": "historical",
                    "State": {"Running": False},
                }
            )
        with patch.dict(require_bundle.__globals__, docker_json=self.image):
            require_bundle(containers, self.bundle)

    def test_changed_image_digest_or_release_label_is_rejected(self):
        """Фактический image ID должен совпадать с digest и меткой выпуска."""
        for image in (
            {"RepoDigests": [], "Config": {"Labels": {"io.hubshell.release-id": "v-new"}}},
            {
                "RepoDigests": list(self.bundle["server"]["images"].values()),
                "Config": {"Labels": {"io.hubshell.release-id": "v-other"}},
            },
        ):
            with patch.dict(
                require_bundle.__globals__, docker_json=lambda *args, result=image: [result]
            ):
                with self.assertRaises(ValueError):
                    require_bundle(self.containers(), self.bundle)

    def test_running_server_uses_image_label_and_actual_mirror_mount(self):
        """Версия берётся из image label, зеркало — из фактического mount backend."""
        import subprocess

        containers = self.containers()
        containers[0]["Mounts"] = [
            {"Destination": "/var/lib/hubshell/client-releases", "Source": str(self.root)}
        ]
        images = self.image("BACKEND")
        calls = []

        def inspect(*args):
            calls.append(args)
            return containers if args[0] == "inspect" else images

        discover = module["running_server"]
        with (
            patch("subprocess.run", return_value=subprocess.CompletedProcess([], 0, stdout="a b")),
            patch.dict(discover.__globals__, docker_json=inspect),
        ):
            version, mirror, values = discover()
        self.assertEqual((version, mirror), ("v-new", self.root))
        self.assertEqual(values, containers)
        self.assertEqual(calls[0], ("inspect", "a", "b"))

    def test_server_change_during_download_prevents_publication(self):
        """Смена запущенного сервера во время скачивания не публикует старый target."""
        main = module["main"]
        observations = iter([("v-new", self.root, []), ("v-another", self.root, [])])
        checked = []
        with (
            patch(
                "sys.argv",
                [
                    "sync",
                    "--public-key",
                    str(self.root / "key.pem"),
                    "--job-root",
                    str(self.root / "jobs"),
                    "--token-file",
                    str(self.root / "token.json"),
                ],
            ),
            patch.dict(
                main.__globals__,
                running_server=lambda: next(observations),
                download_release=lambda *args: self.bundle,
                require_running_bundle=lambda *args: checked.append("checked"),
            ),
        ):
            with self.assertRaises(ValueError):
                main()
        self.assertEqual(checked, [])
        self.assertFalse((self.root / "jobs/v-new/assignment.json").exists())


if __name__ == "__main__":
    unittest.main()
