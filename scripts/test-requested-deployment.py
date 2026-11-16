"""Exercise the GitHub request handoff without touching production."""

import runpy
import unittest
from pathlib import Path
from unittest.mock import Mock

from server_deployment import MaintenanceBlocked

run_latest = runpy.run_path(str(Path(__file__).with_name("run-requested-deployment.py")))[
    "run_latest"
]


class RequestedDeploymentTests(unittest.TestCase):
    def setUp(self):
        self.sha = "a" * 40
        self.deploy = Mock()
        self.statuses = []

    def request(self, path, body=None):
        if path.startswith("?"):
            return [{"id": 42, "sha": self.sha}]
        if body is None:
            return [{"state": self.state}]
        self.assertEqual(path, "/42/statuses")
        self.statuses.append(body["state"])

    def test_only_queued_requests_run_and_publish_success(self):
        self.state = "queued"
        self.assertTrue(run_latest(self.request, self.deploy))
        self.deploy.assert_called_once_with(f"commit-{self.sha}")
        self.assertEqual(self.statuses, ["in_progress", "success"])

    def test_previous_result_does_not_start_deployment_again(self):
        self.state = "success"
        self.assertTrue(run_latest(self.request, self.deploy))
        self.deploy.assert_not_called()
        self.assertEqual(self.statuses, [])

    def test_active_game_refusal_does_not_report_success(self):
        self.state = "queued"
        self.deploy.side_effect = MaintenanceBlocked("Active session")
        self.assertFalse(run_latest(self.request, self.deploy))
        self.assertEqual(self.statuses, ["in_progress", "failure"])

    def test_unexpected_failure_marks_request_and_propagates(self):
        self.state = "queued"
        self.deploy.side_effect = RuntimeError("Deployment failed")
        with self.assertRaises(RuntimeError):
            run_latest(self.request, self.deploy)
        self.assertEqual(self.statuses, ["in_progress", "failure"])


if __name__ == "__main__":
    unittest.main()
