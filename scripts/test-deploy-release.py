"""Resumable CD job checks with fake backend/process boundaries and real state/report files."""

import copy
import datetime
import json
import runpy
import subprocess
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

runner = runpy.run_path(str(Path(__file__).with_name("deploy-release.py")))
run_delivery = runner["run_delivery"]
select_release = runner["select_release"]
checkout_release = runner["checkout_release"]


class FakeBackend:
    def __init__(self):
        self.value = None
        self.creations = []
        self.actions = []
        self.lose_create = False

    def request(self, method, path, body=None):
        if path == "/health/ready":
            return {"status": "ready"}
        if method == "POST" and path == "/api/v1/client-updates":
            self.creations.append(copy.deepcopy(body))
            if self.value is None:
                self.value = {
                    **body,
                    "id": str(uuid.uuid4()),
                    "round_id": str(uuid.uuid4()),
                    "phase": "polling",
                    "server_ready": False,
                    "targets": {"pc-1": str(uuid.uuid4())},
                    "reports": {},
                    "gui_confirmations": {},
                    "old_releases": {"pc-1": "v-old"},
                }
            if self.lose_create:
                self.lose_create = False
                raise ConnectionResetError("Lost creation response")
            return copy.deepcopy(self.value)
        if method == "POST":
            action = path.rsplit("/", 1)[1]
            self.actions.append(action)
            if action == "prepare":
                self.value.update(phase="preparing", round_id=str(uuid.uuid4()))
            elif action == "server-ready":
                self.value["server_ready"] = True
            elif action == "authorize":
                self.value["phase"] = "authorized"
            elif action == "finish":
                self.value["phase"] = "completed"
            else:
                raise AssertionError(action)
        installed = self.value["phase"] in {"authorized", "completed"}
        self.value["reports"] = {
            "pc-1": {
                "round_id": self.value["round_id"],
                "stage": "installed" if installed else "ready",
                "ready": True,
                "active_session": False,
                "pending_facts": 0,
                "received_at": datetime.datetime.now(datetime.UTC).isoformat(),
                "installed_sha256": "a" * 64 if installed else None,
                "error_code": None,
                "running_release_id": "v-new" if installed else "v-old",
            }
        }
        if installed:
            self.value["gui_confirmations"] = {"pc-1": "v-new"}
        return copy.deepcopy(self.value)


class FakeServer:
    def __init__(self):
        self.calls = 0
        self.fail = False

    def update(self, value, smoke):
        self.calls += 1
        assert value["phase"] == "preparing"
        if self.fail:
            raise RuntimeError("backup failed")
        smoke()


class FakeDockhand:
    def __init__(self):
        self.variables = []

    def request(self, method, path, body=None):
        if method == "PUT":
            self.variables = body["variables"]
        return {"variables": self.variables}


class DeployReleaseTests(unittest.TestCase):
    def setUp(self):
        from client_release import COMPONENTS, IMAGE_ROOT

        self.temporary = tempfile.TemporaryDirectory()
        self.job = Path(self.temporary.name)
        self.backend, self.server, self.dockhand = FakeBackend(), FakeServer(), FakeDockhand()
        self.bundle = {
            "client": {"releaseId": "v-new", "executableSha256": "a" * 64},
            "server": {
                "images": {
                    f"HUBSHELL_{component}_IMAGE": f"{IMAGE_ROOT}/{name}@sha256:{'a' * 64}"
                    for component, name in COMPONENTS.items()
                }
            },
        }

    def tearDown(self):
        self.temporary.cleanup()

    def run_job(self, timeout=10):
        return run_delivery(
            self.backend, self.server, self.dockhand, self.bundle, self.job, timeout
        )

    def test_complete_delivery_persists_job_and_full_report(self):
        result = self.run_job()
        self.assertTrue(result["success"])
        self.assertEqual(result["confirmed"], 1)
        self.assertEqual(self.backend.actions, ["prepare", "server-ready", "authorize", "finish"])
        self.assertEqual(self.server.calls, 1)
        self.assertEqual(len(self.dockhand.variables), 3)
        self.assertTrue((self.job / "report.json").exists())
        self.run_job()
        self.assertEqual(len(self.backend.creations), 1)
        self.assertEqual(self.server.calls, 1)

    def test_lost_create_response_reuses_operation_id(self):
        self.backend.lose_create = True
        with self.assertRaises(ConnectionResetError):
            self.run_job()
        self.assertIsNone(json.loads((self.job / "job.json").read_bytes())["deployment_id"])
        self.assertTrue(self.run_job()["success"])
        self.assertEqual(self.backend.creations[0], self.backend.creations[1])

    def test_server_failure_keeps_barrier_and_resume_keeps_same_deployment(self):
        self.server.fail = True
        with self.assertRaises(RuntimeError):
            self.run_job()
        self.assertEqual(self.backend.value["phase"], "preparing")
        saved_id = self.backend.value["id"]
        self.assertFalse(json.loads((self.job / "report.json").read_bytes())["success"])
        self.assertNotIn("authorize", self.backend.actions)
        self.server.fail = False
        self.assertTrue(self.run_job()["success"])
        self.assertEqual(self.backend.value["id"], saved_id)
        self.assertEqual(len(self.backend.creations), 1)

    def test_timeout_reports_incomplete_without_clearing_backend_state(self):
        with self.assertRaises(TimeoutError):
            self.run_job(timeout=0)
        saved = json.loads((self.job / "report.json").read_bytes())
        self.assertEqual(saved["error"], "TimeoutError")
        self.assertFalse(saved["success"])
        self.assertEqual(self.backend.value["phase"], "polling")
        self.assertEqual(self.backend.actions, [])

    def test_automatic_selection_resumes_unfinished_release_without_consulting_latest(self):
        (self.job / "active-release.json").write_text(json.dumps({"release_id": "v-pending"}))

        def unexpected():
            self.fail("A new release must not displace the unfinished job")

        with patch.dict(select_release.__globals__, latest_release=unexpected):
            self.assertEqual(select_release(self.job, None), "v-pending")
        with self.assertRaises(ValueError):
            select_release(self.job, "v-other")

    def test_completed_job_allows_selection_of_latest_release(self):
        (self.job / "active-release.json").write_text(json.dumps({"release_id": "v-done"}))
        (self.job / "v-done").mkdir()
        (self.job / "v-done" / "report.json").write_text(
            json.dumps({"phase": "completed", "success": True})
        )
        with patch.dict(select_release.__globals__, latest_release=lambda: "v-next"):
            self.assertEqual(select_release(self.job, None), "v-next")
        self.assertEqual(
            json.loads((self.job / "active-release.json").read_bytes())["release_id"], "v-next"
        )

    def test_checkout_fetches_only_signed_commit_from_approved_origin(self):
        calls = []
        head = "b" * 40

        def git(command, **kwargs):
            nonlocal head
            calls.append(command)
            result = ""
            if command[1] == "rev-parse":
                result = head
            elif command[1] == "remote":
                result = "https://github.com/DanielBarutov/HubShell.git"
            elif command[1] == "checkout":
                head = command[-1]
            return subprocess.CompletedProcess(command, 0, stdout=result)

        with patch("subprocess.run", side_effect=git):
            checkout_release(self.job, "a" * 40)
        self.assertIn(["git", "fetch", "--no-tags", "origin", "a" * 40], calls)
        self.assertIn(["git", "checkout", "--detach", "a" * 40], calls)
        self.assertFalse(any("pull" in call or "--force" in call for call in calls))

    def test_checkout_refuses_dirty_tree_before_fetch_or_replacement(self):
        with patch(
            "subprocess.run", return_value=subprocess.CompletedProcess([], 0, stdout=" M file")
        ) as git:
            with self.assertRaises(ValueError):
                checkout_release(self.job, "a" * 40)
        self.assertEqual(git.call_count, 1)


if __name__ == "__main__":
    unittest.main()
