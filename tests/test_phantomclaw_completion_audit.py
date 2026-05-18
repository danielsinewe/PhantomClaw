from __future__ import annotations

import unittest

from scripts.phantomclaw_completion_audit import build_completion_audit, checklist_status


class PhantomClawCompletionAuditTests(unittest.TestCase):
    def test_checklist_status_identifies_sales_community_auth_blocker(self) -> None:
        checks = {
            "active_health": {"ok": True},
            "no_paused_native_automations": {
                "ok": False,
                "paused_automations": [
                    {
                        "id": "linkedin-sales-community",
                        "pause_reason": "sales_community_auth_required",
                    }
                ],
            },
        }

        self.assertEqual(checklist_status(checks), "blocked_sales_community_auth")

    def test_checklist_status_identifies_complete_state(self) -> None:
        self.assertEqual(
            checklist_status(
                {
                    "active_health": {"ok": True},
                    "no_paused_native_automations": {"ok": True, "paused_automations": []},
                }
            ),
            "complete",
        )

    def test_build_completion_audit_maps_registry_to_evidence_checklist(self) -> None:
        registry = {
            "schema_version": "phantomclaw.automation-registry.v1",
            "policy": {
                "processing_system": "phantomclaw",
                "codex_processing_enabled": False,
            },
            "automations": [
                {
                    "id": "peerlist-follow-workflow",
                    "name": "Peerlist Follow Workflow",
                    "status": "ACTIVE",
                    "source_status": "ACTIVE",
                    "processing_system": "phantomclaw",
                    "codex_processing_enabled": False,
                    "runner": {
                        "status": "native",
                        "dispatch": "openclaw_railway_host_command",
                        "command": ["/usr/local/bin/run-peerlist-follow-workflow.sh"],
                        "codex_fallback_allowed": False,
                    },
                    "source": {"system": "phantomclaw", "path": "generated"},
                },
                {
                    "id": "linkedin-sales-community",
                    "name": "LinkedIn Sales Community Engagement",
                    "status": "PAUSED",
                    "source_status": "PAUSED",
                    "processing_system": "phantomclaw",
                    "codex_processing_enabled": False,
                    "parameters": {
                        "live_enabled": False,
                        "pause_reason": "sales_community_auth_required",
                    },
                    "runner": {
                        "status": "native",
                        "dispatch": "phantomclaw_native",
                        "command": ["python3", "-m", "linkedin.sales_community_engagement.runner"],
                        "codex_fallback_allowed": False,
                    },
                    "source": {"system": "phantomclaw", "path": "generated"},
                },
            ],
        }

        audit = build_completion_audit(
            registry=registry,
            codex_active=[],
            gateway={"ok": True, "status": 200},
            phantomclaw_cli={"ok": True, "exit_code": 0},
            worker={
                "ok": True,
                "checked": True,
                "missing_occurrence_count": 0,
                "stale_claimed_count": 0,
                "recent_failed_dispatch_count": 0,
            },
        )

        self.assertFalse(audit["ok"])
        self.assertEqual(audit["status"], "blocked_sales_community_auth")
        self.assertEqual(audit["checks"]["registry_active_runners"]["active"], 1)
        self.assertEqual(audit["checks"]["no_paused_native_automations"]["paused_count"], 1)


if __name__ == "__main__":
    unittest.main()
