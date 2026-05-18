from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts.sales_community_auth_activation import (
    activate_sales_community_in_registry,
    activation_failure_reason,
    report_ready_for_activation,
)


class SalesCommunityAuthActivationTests(unittest.TestCase):
    def test_report_ready_for_activation_requires_ok_shape_and_no_stop_reason(self) -> None:
        self.assertTrue(report_ready_for_activation({"status": "ok", "page_shape_ok": True, "stop_reason": None}))
        self.assertFalse(report_ready_for_activation({"status": "stopped", "page_shape_ok": True, "stop_reason": "auth_required"}))
        self.assertFalse(report_ready_for_activation({"status": "ok", "page_shape_ok": False, "stop_reason": None}))

    def test_activation_failure_reason_prefers_report_stop_reason(self) -> None:
        self.assertEqual(
            activation_failure_reason(
                {
                    "exit_code": 0,
                    "report": {
                        "status": "stopped",
                        "page_shape_ok": True,
                        "stop_reason": "auth_required",
                    },
                }
            ),
            "auth_required",
        )

    def test_activate_sales_community_in_registry_sets_active_live_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            registry_path = Path(tmpdir) / "registry.json"
            registry_path.write_text(
                json.dumps(
                    {
                        "automations": [
                            {
                                "id": "linkedin-sales-community",
                                "status": "PAUSED",
                                "source_status": "PAUSED",
                                "parameters": {
                                    "live_enabled": False,
                                    "pause_reason": "sales_community_auth_required",
                                    "like_cap": 2,
                                },
                            }
                        ]
                    }
                )
            )

            result = activate_sales_community_in_registry(registry_path)
            updated = json.loads(registry_path.read_text())["automations"][0]

        self.assertTrue(result["updated"])
        self.assertEqual(updated["status"], "ACTIVE")
        self.assertEqual(updated["source_status"], "ACTIVE")
        self.assertTrue(updated["parameters"]["live_enabled"])
        self.assertEqual(updated["parameters"]["like_cap"], 2)
        self.assertNotIn("pause_reason", updated["parameters"])


if __name__ == "__main__":
    unittest.main()
