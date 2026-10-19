"""CD must keep every target in the report and defer all admission decisions to the API."""

import copy
import datetime
import tempfile
import unittest
import urllib.error
from pathlib import Path

from client_update_cd import advance, report, save_report

NOW = datetime.datetime(2026, 10, 19, tzinfo=datetime.UTC)


def deployment():
    return {
        "id": "deployment",
        "operation_id": "operation",
        "round_id": "round",
        "release_id": "v-new",
        "executable_sha256": "a" * 64,
        "phase": "polling",
        "server_ready": False,
        "targets": {"pc-1": "workstation-1", "pc-2": "workstation-2"},
        "reports": {
            device: {
                "round_id": "round",
                "received_at": NOW.isoformat(),
                "stage": "ready",
                "ready": True,
                "active_session": False,
                "pending_facts": 0,
                "installed_sha256": None,
                "error_code": None,
                "running_release_id": "v-old",
            }
            for device in ("pc-1", "pc-2")
        },
        "gui_confirmations": {},
        "old_releases": {"pc-1": "v-old", "pc-2": "v-old"},
    }


class ClientUpdateCdTests(unittest.TestCase):
    def test_active_missing_stale_or_pending_pc_prevents_preparation_and_server_restart(self):
        variants = []
        for changes in (
            {"active_session": True},
            {"pending_facts": 1},
            {"ready": False},
            {"received_at": (NOW - datetime.timedelta(seconds=31)).isoformat()},
            {"round_id": "old-round"},
        ):
            value = deployment()
            value["reports"]["pc-2"].update(changes)
            variants.append(value)
        missing = deployment()
        del missing["reports"]["pc-2"]
        variants.append(missing)
        for value in variants:
            for phase in ("polling", "preparing"):
                with self.subTest(value=value, phase=phase):
                    value["phase"] = phase
                    self.assertEqual(advance(value, self.unexpected, self.unexpected, NOW), value)
                    self.assertEqual(report(value, NOW)["total"], 2)

    def unexpected(self, argument):
        self.fail(f"Unexpected mutation: {argument}")

    def test_server_stage_precedes_server_ready_and_authorization(self):
        value = deployment()
        value["phase"] = "preparing"
        actions = []

        def post(action):
            actions.append(action)
            return value

        def update_server(current):
            self.assertEqual(current["phase"], "preparing")
            actions.append("backup-migrate-deploy-smoke")

        advance(value, post, update_server, NOW)
        self.assertEqual(actions, ["backup-migrate-deploy-smoke", "server-ready"])
        value["server_ready"] = True
        actions.clear()
        advance(value, post, self.unexpected, NOW)
        self.assertEqual(actions, ["authorize"])

    def test_failed_server_stage_does_not_authorize_clients(self):
        value = deployment()
        value["phase"] = "preparing"

        def fail(current):
            raise RuntimeError("migration failed")

        with self.assertRaises(RuntimeError):
            advance(value, self.unexpected, fail, NOW)
        self.assertEqual(value["phase"], "preparing")
        self.assertFalse(value["server_ready"])

    def test_authorization_conflict_waits_without_unblocking(self):
        value = deployment()

        def conflict(action):
            raise urllib.error.HTTPError("http://localhost", 409, "wait", {}, None)

        self.assertEqual(advance(value, conflict, self.unexpected, NOW), value)

    def test_only_all_double_confirmations_can_finish_and_completed_is_required_for_success(self):
        value = deployment()
        value["phase"] = "authorized"
        for device in value["targets"]:
            value["reports"][device].update(stage="installed", installed_sha256="a" * 64)
        value["gui_confirmations"]["pc-1"] = "v-new"
        advance(value, self.unexpected, self.unexpected, NOW)
        value["gui_confirmations"]["pc-2"] = "v-new"
        self.assertFalse(report(value, NOW)["success"])
        actions = []
        advance(value, lambda action: actions.append(action) or value, self.unexpected, NOW)
        self.assertEqual(actions, ["finish"])
        value["phase"] = "completed"
        with tempfile.TemporaryDirectory() as temporary:
            summary = save_report(Path(temporary), value, NOW)
            self.assertTrue(summary["success"])
            self.assertIn("2/2", (Path(temporary) / "report.txt").read_text())
            self.assertEqual(summary["devices"][0]["old_release_id"], "v-old")

    def test_rollback_failed_and_empty_fleet_never_report_success(self):
        value = deployment()
        value["phase"] = "failed"
        value["reports"]["pc-2"].update(stage="rolled_back", error_code="install_failed")
        advance(value, self.unexpected, self.unexpected, NOW)
        summary = report(value, NOW)
        self.assertFalse(summary["success"])
        self.assertTrue(summary["devices"][1]["rollback"])
        empty = copy.deepcopy(value)
        empty.update(phase="completed", targets={})
        self.assertFalse(report(empty, NOW)["success"])

    def test_unready_report_is_not_labelled_ready(self):
        value = deployment()
        value["reports"]["pc-2"]["ready"] = False
        self.assertEqual(report(value, NOW)["devices"][1]["status"], "not_ready")


if __name__ == "__main__":
    unittest.main()
