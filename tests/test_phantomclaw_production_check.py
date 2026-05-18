from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.phantomclaw_production_check import (
    check_worker_health,
    cli_summary,
    paused_native_automation_status,
    paused_native_summary,
    registry_source_path_status,
    source_path_summary,
)


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

    def test_registry_source_path_status_reports_missing_sources(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            existing = Path(tmpdir) / "automation.toml"
            existing.write_text("status = \"ACTIVE\"\n")
            registry = {
                "automations": [
                    {
                        "id": "active-one",
                        "name": "Active One",
                        "status": "ACTIVE",
                        "source_status": "ACTIVE",
                        "runner": {"status": "native"},
                        "source": {"path": str(existing)},
                    },
                    {
                        "id": "stale-one",
                        "name": "Stale One",
                        "status": "PAUSED",
                        "source_status": "ACTIVE",
                        "runner": {"status": "native_candidate"},
                        "source": {
                            "path": str(Path(tmpdir) / "missing.toml"),
                        },
                    },
                    {
                        "id": "deleted-one",
                        "name": "Deleted One",
                        "status": "PAUSED",
                        "source_status": "PAUSED",
                        "runner": {"status": "native_candidate"},
                        "source": {
                            "path": str(Path(tmpdir) / "deleted.toml"),
                            "deleted_from_codex_at": "2026-05-18T08:00:00+00:00",
                        },
                    },
                    {
                        "id": "generated-one",
                        "name": "Generated One",
                        "source": {"path": "OpenClaw generated runner"},
                    },
                ]
            }

            status = registry_source_path_status(registry)

        self.assertFalse(status["ok"])
        self.assertEqual(status["existing_count"], 1)
        self.assertEqual(status["missing_count"], 1)
        self.assertEqual(status["deleted_missing_count"], 1)
        self.assertEqual(status["skipped_count"], 1)
        self.assertEqual(status["missing_sources"][0]["id"], "stale-one")
        self.assertEqual(status["missing_sources"][0]["deleted_from_codex_at"], None)
        self.assertEqual(status["deleted_missing_sources"][0]["id"], "deleted-one")

    def test_source_path_summary_can_hide_details(self) -> None:
        source_paths = {
            "ok": False,
            "missing_count": 1,
            "deleted_missing_count": 1,
            "missing_sources": [{"id": "stale-one"}],
            "deleted_missing_sources": [{"id": "deleted-one"}],
        }

        summary = source_path_summary(source_paths, include_details=False)

        self.assertEqual(summary["ok"], False)
        self.assertEqual(summary["missing_count"], 1)
        self.assertNotIn("missing_sources", summary)
        self.assertNotIn("deleted_missing_sources", summary)

    def test_paused_native_automation_status_reports_paused_runners(self) -> None:
        registry = {
            "automations": [
                {
                    "id": "active-one",
                    "name": "Active One",
                    "status": "ACTIVE",
                    "source_status": "ACTIVE",
                    "runner": {"status": "native", "dispatch": "phantomclaw_native"},
                },
                {
                    "id": "paused-one",
                    "name": "Paused One",
                    "status": "PAUSED",
                    "source_status": "PAUSED",
                    "runner": {"status": "native", "dispatch": "phantomclaw_native"},
                    "parameters": {
                        "live_enabled": False,
                        "pause_reason": "auth_required",
                    },
                },
                {
                    "id": "blocked-non-native",
                    "name": "Blocked Non Native",
                    "status": "PAUSED",
                    "runner": {"status": "missing"},
                },
            ]
        }

        status = paused_native_automation_status(registry)

        self.assertFalse(status["ok"])
        self.assertEqual(status["paused_count"], 1)
        self.assertEqual(status["paused_automations"][0]["id"], "paused-one")
        self.assertEqual(status["paused_automations"][0]["pause_reason"], "auth_required")
        self.assertEqual(status["paused_automations"][0]["live_enabled"], False)

    def test_paused_native_summary_can_hide_details(self) -> None:
        paused_native = {
            "ok": False,
            "paused_count": 1,
            "paused_automations": [{"id": "paused-one"}],
        }

        summary = paused_native_summary(paused_native, include_details=False)

        self.assertEqual(summary["ok"], False)
        self.assertEqual(summary["paused_count"], 1)
        self.assertNotIn("paused_automations", summary)


if __name__ == "__main__":
    unittest.main()
