from contextlib import redirect_stdout
from io import StringIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from phantomclaw_bundle import (
    BUNDLE_SCHEMA_VERSION,
    build_run_bundle,
    build_run_bundle_from_path,
    run_bundle_schema,
    validate_run_bundle,
)
from linkedin.company_profile_engagement.models import RunReport
from scripts.export_run_bundle import main as export_run_bundle_main


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
        bundle = build_run_bundle(automation_name="linkedin-company-profile-engagement", report=report)
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

    def test_bundle_schema_matches_version(self) -> None:
        schema = run_bundle_schema()
        self.assertEqual(schema["properties"]["schema_version"]["const"], BUNDLE_SCHEMA_VERSION)

    def test_validate_run_bundle_rejects_mismatched_run_ids(self) -> None:
        report = RunReport(
            run_id="run-3",
            started_at="2026-03-28T09:00:00+00:00",
            status="ok",
            actor_verified=True,
            search_shape_ok=True,
            posts_scanned=1,
        )
        bundle = build_run_bundle(automation_name="linkedin-company-profile-engagement", report=report)
        bundle["report"]["run_id"] = "wrong-run-id"
        with self.assertRaisesRegex(ValueError, "Run id mismatch"):
            validate_run_bundle(bundle)

    def test_validate_run_bundle_accepts_finished_at_when_iso_formatted(self) -> None:
        report = RunReport(
            run_id="run-4",
            started_at="2026-03-28T09:00:00+00:00",
            finished_at="2026-03-28T09:05:00+00:00",
            status="ok",
            actor_verified=True,
            search_shape_ok=True,
            posts_scanned=1,
        )
        bundle = build_run_bundle(automation_name="linkedin-company-profile-engagement", report=report)
        validate_run_bundle(bundle)

    def test_export_script_can_print_schema_without_report_inputs(self) -> None:
        with TemporaryDirectory():
            stdout = StringIO()
            with redirect_stdout(stdout):
                exit_code = export_run_bundle_main(["--print-schema"])

        self.assertEqual(exit_code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["properties"]["schema_version"]["const"], BUNDLE_SCHEMA_VERSION)


if __name__ == "__main__":
    unittest.main()
