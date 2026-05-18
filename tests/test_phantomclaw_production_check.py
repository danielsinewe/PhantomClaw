from __future__ import annotations

import unittest
from unittest.mock import patch

from scripts.phantomclaw_production_check import check_worker_health, cli_summary


class PhantomClawProductionCheckTests(unittest.TestCase):
    def test_cli_summary_keeps_success_minimal(self) -> None:
        self.assertEqual(
            cli_summary(
                {
                    "ok": True,
                    "exit_code": 0,
                    "phase": "whoami",
                    "stdout": "hello@danielsinewe.com",
                    "stderr": "",
                }
            ),
            {
                "ok": True,
                "exit_code": 0,
                "phase": "whoami",
            },
        )

    def test_cli_summary_includes_bounded_failure_details(self) -> None:
        summary = cli_summary(
            {
                "ok": False,
                "exit_code": 1,
                "phase": "login",
                "stdout": "",
                "stderr": "x" * 700,
            }
        )

        self.assertEqual(summary["ok"], False)
        self.assertEqual(summary["exit_code"], 1)
        self.assertEqual(summary["phase"], "login")
        self.assertEqual(summary["stderr"], "x" * 500)

    def test_check_worker_health_can_be_required(self) -> None:
        self.assertEqual(
            check_worker_health(
                database_url=None,
                workspace_slug="daniel-sinewe",
                lookback_hours=3,
                require_worker=True,
                fail_on_recent_failures=False,
            ),
            {
                "checked": False,
                "ok": False,
                "reason": "database_url_not_configured",
            },
        )

    def test_check_worker_health_summarizes_worker_status(self) -> None:
        with patch(
            "scripts.phantomclaw_production_check.worker_status",
            return_value={
                "ok": True,
                "active_count": 3,
                "recent_dispatch_count": 5,
                "missing_occurrence_count": 0,
                "stale_claimed_count": 0,
                "recent_dispatches": [
                    {"automation_id": str(i), "status": "ok"}
                    for i in range(10)
                ],
            },
        ):
            summary = check_worker_health(
                database_url="postgresql://example",
                workspace_slug="daniel-sinewe",
                lookback_hours=3,
                require_worker=True,
                fail_on_recent_failures=True,
            )

        self.assertTrue(summary["checked"])
        self.assertTrue(summary["ok"])
        self.assertEqual(summary["active_count"], 3)
        self.assertEqual(summary["recent_failed_dispatch_count"], 0)
        self.assertEqual(len(summary["recent_dispatches"]), 5)

    def test_check_worker_health_can_fail_on_recent_failed_dispatches(self) -> None:
        with patch(
            "scripts.phantomclaw_production_check.worker_status",
            return_value={
                "ok": True,
                "active_count": 3,
                "recent_dispatch_count": 2,
                "missing_occurrence_count": 0,
                "stale_claimed_count": 0,
                "recent_dispatches": [
                    {"automation_id": "trustoutreach-linkedin", "status": "failed"},
                    {"automation_id": "peerlist-follow-workflow", "status": "ok"},
                ],
            },
        ):
            summary = check_worker_health(
                database_url="postgresql://example",
                workspace_slug="daniel-sinewe",
                lookback_hours=3,
                require_worker=True,
                fail_on_recent_failures=True,
            )

        self.assertTrue(summary["checked"])
        self.assertFalse(summary["ok"])
        self.assertEqual(summary["recent_failed_dispatch_count"], 1)


if __name__ == "__main__":
    unittest.main()
