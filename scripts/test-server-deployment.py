"""Server stage ordering and failure isolation without modifying a running stack."""

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from client_release import COMPONENTS, IMAGE_ROOT
from server_deployment import ComposeServer


class ServerDeploymentTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        images = {
            f"HUBSHELL_{component}_IMAGE": f"{IMAGE_ROOT}/{name}@sha256:{'a' * 64}"
            for component, name in COMPONENTS.items()
        }
        self.server = ComposeServer(self.root, self.root / "secrets.env", self.root, images)
        self.actions = []
        self.config = {
            "name": "hubshell",
            "services": {
                name: {"image": images[key]}
                for name, key in {
                    "backend-http": "HUBSHELL_BACKEND_IMAGE",
                    "backend-grpc": "HUBSHELL_BACKEND_IMAGE",
                    "backend-migrate": "HUBSHELL_BACKEND_IMAGE",
                    "worker": "HUBSHELL_BACKEND_IMAGE",
                    "frontend": "HUBSHELL_FRONTEND_IMAGE",
                    "steam-guest-server": "HUBSHELL_STEAM_GUEST_IMAGE",
                }.items()
            },
        }
        self.config["services"]["postgres"] = {"image": "postgres:16"}
        self.config["services"]["redis"] = {"image": "redis:7"}
        self.server.run = self.compose_run
        self.server.backup = self.backup
        self.value = {"id": "deployment", "round_id": "round", "phase": "preparing"}

    def tearDown(self):
        self.temporary.cleanup()

    def compose_run(self, *args, **kwargs):
        self.actions.append(args)
        return subprocess.CompletedProcess(args, 0, stdout=json.dumps(self.config).encode())

    def backup(self, *args):
        self.actions.append(("backup", *args))

    def smoke(self):
        self.actions.append(("smoke",))

    def test_application_stop_backup_migration_and_smoke_are_ordered_without_infra_restart(self):
        self.server.update(self.value, self.smoke)
        names = [action[0] for action in self.actions]
        self.assertEqual(
            names,
            ["config", "pull", "stop", "backup", "backup", "run", "up", "exec", "exec", "smoke"],
        )
        stop = next(action for action in self.actions if action[0] == "stop")
        self.assertIn("worker", stop)
        self.assertNotIn("postgres", stop)
        self.assertNotIn("redis", stop)
        up = next(action for action in self.actions if action[0] == "up")
        self.assertIn("--no-deps", up)
        self.assertNotIn("down", names)
        self.assertTrue(json.loads((self.root / "server-stage.json").read_bytes())["ready"])

    def test_backup_failure_prevents_migration_and_deployment(self):
        def fail(*args):
            raise RuntimeError("restore verification failed")

        self.server.backup = fail
        with self.assertRaises(RuntimeError):
            self.server.update(self.value, self.smoke)
        self.assertFalse(any(action[0] in {"run", "up", "smoke"} for action in self.actions))
        self.assertFalse((self.root / "server-stage.json").exists())

    def test_wrong_project_mutable_image_or_build_prevents_any_change(self):
        for variant in ("project", "image", "build"):
            with self.subTest(variant=variant):
                original = json.loads(json.dumps(self.config))
                if variant == "project":
                    self.config["name"] = "production"
                elif variant == "image":
                    self.config["services"]["backend-http"]["image"] = "backend:latest"
                else:
                    self.config["services"]["backend-http"]["build"] = "."
                self.actions.clear()
                with self.assertRaises(ValueError):
                    self.server.update(self.value, self.smoke)
                self.assertEqual([action[0] for action in self.actions], ["config"])
                self.config = original

    def configure_idle_checks(self, counts):
        counts = iter(counts)

        def run(*args, **kwargs):
            response = self.compose_run(*args, **kwargs)
            if args[0] == "ps":
                response.stdout = b"backend-http\nbackend-grpc\nfrontend\nworker\n"
            elif args[:3] == ("exec", "-T", "postgres"):
                response.stdout = next(counts)
            return response

        self.server.run = run

    def test_active_games_prevent_stopping_the_server(self):
        self.configure_idle_checks([b"1\n"])
        with self.assertRaisesRegex(ValueError, "активные сессии"):
            self.server.update_idle(self.smoke)
        self.assertNotIn("stop", [action[0] for action in self.actions])

    def test_session_racing_shutdown_restores_previous_services(self):
        self.configure_idle_checks([b"0\n", b"1\n"])
        with self.assertRaisesRegex(ValueError, "активные сессии"):
            self.server.update_idle(self.smoke)
        self.assertEqual(
            self.actions[-1], ("start", "backend-grpc", "backend-http", "frontend", "worker")
        )
        self.assertNotIn("run", [action[0] for action in self.actions])
        self.assertFalse((self.root / "migration-started.json").exists())

    def test_idle_deploy_records_migration_and_readiness(self):
        self.configure_idle_checks([b"0\n", b"0\n"])
        self.server.update_idle(self.smoke)
        self.assertTrue((self.root / "migration-started.json").exists())
        self.assertTrue(json.loads((self.root / "server-stage.json").read_bytes())["ready"])

    def test_failed_migration_does_not_restart_old_services(self):
        self.configure_idle_checks([b"0\n", b"0\n"])
        run = self.server.run

        def fail_migration(*args, **kwargs):
            if args[0] == "run":
                raise RuntimeError("migration failed")
            return run(*args, **kwargs)

        self.server.run = fail_migration
        with self.assertRaisesRegex(RuntimeError, "migration failed"):
            self.server.update_idle(self.smoke)
        self.assertTrue((self.root / "migration-started.json").exists())
        self.assertNotIn("start", [action[0] for action in self.actions])
        self.assertFalse((self.root / "server-stage.json").exists())

    def test_without_barrier_no_compose_command_runs(self):
        self.value["phase"] = "polling"
        with self.assertRaises(ValueError):
            self.server.update(self.value, self.smoke)
        self.assertEqual(self.actions, [])


if __name__ == "__main__":
    unittest.main()
