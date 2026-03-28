import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from phantomclaw_bundle import BUNDLE_SCHEMA_VERSION, build_run_bundle, build_run_bundle_from_path
from trustoutreach_linkedin.models import RunReport


class PhantomClawBundleTests(unittest.TestCase):
    def test_build_run_bundle_normalizes_legacy_name(self) -> None:
        report = RunReport(
            run_id="run-1",
            started_at="2026-03-28T09:00:00+00:00",
            status="ok",
            actor_verified=True,
            search_shape_ok=True,
            posts_scanned=5,
            posts_liked=2,
            posts_reposted=1,
            comments_liked=1,
            agencies_followed=1,
        )
        bundle = build_run_bundle(automation_name="trustoutreach-linkedin", report=report)
        self.assertEqual(bundle["schema_version"], BUNDLE_SCHEMA_VERSION)
        self.assertEqual(bundle["automation"]["name"], "linkedin-company-profile-engagement")
        self.assertEqual(bundle["automation"]["platform"], "linkedin")
        self.assertEqual(bundle["automation"]["surface"], "core")
        self.assertEqual(bundle["metrics"]["actions_total"], 5)

    def test_build_run_bundle_from_path_reads_report_json(self) -> None:
        with TemporaryDirectory() as tmpdir:
            report_path = Path(tmpdir) / "run.json"
            report_path.write_text(
                json.dumps(
                    {
                        "run_id": "run-2",
                        "started_at": "2026-03-28T09:00:00+00:00",
                        "status": "ok",
                        "page_shape_ok": True,
                        "items_scanned": 4,
                        "items_considered": 2,
                        "items_liked": 1,
                    }
                )
            )
            bundle = build_run_bundle_from_path(
                automation_name="linkedin-sales-community-engagement",
                report_path=report_path,
            )
            self.assertEqual(bundle["automation"]["surface"], "sales-community")
            self.assertEqual(bundle["run"]["run_id"], "run-2")
            self.assertEqual(bundle["source"]["artifact_path"], str(report_path))


if __name__ == "__main__":
    unittest.main()

