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
            companies_followed=1,
        )
        bundle = build_run_bundle(automation_name="linkedin-company-profile-engagement", report=report)
        self.assertEqual(bundle["schema_version"], BUNDLE_SCHEMA_VERSION)
        self.assertEqual(bundle["automation"]["name"], "linkedin-company-profile-engagement")
        self.assertEqual(bundle["automation"]["platform"], "linkedin")
        self.assertEqual(bundle["automation"]["surface"], "core")
        self.assertEqual(bundle["metrics"]["actions_total"], 5)
        self.assertEqual(bundle["report"]["companies_followed"], 1)

    def test_build_run_bundle_surfaces_profile_and_action_events(self) -> None:
        report = RunReport(
            run_id="run-action-events",
            started_at="2026-03-28T09:00:00+00:00",
            status="ok",
            profile_name="TrustOutreach",
            actor_verified=True,
            search_shape_ok=True,
            posts_scanned=5,
        )
        report.events.extend(
            [
                {"ts": "2026-03-28T09:00:01+00:00", "type": "snapshot_loaded", "pass_index": 0},
                {
                    "ts": "2026-03-28T09:00:02+00:00",
                    "type": "post_liked",
                    "post_id": "urn:li:activity:1001",
                    "post_url": "https://www.linkedin.com/feed/update/urn:li:activity:1001",
                    "selector": "selector:like",
                },
                {
                    "ts": "2026-03-28T09:00:03+00:00",
                    "type": "company_followed",
                    "company_id": "49127922",
                    "company_url": "https://www.linkedin.com/company/49127922/",
                    "name": "Senseven Health",
                    "selector": "company:0:follow",
                },
            ]
        )

        bundle = build_run_bundle(automation_name="linkedin-company-profile-engagement", report=report)

        self.assertEqual(bundle["run"]["profile_name"], "TrustOutreach")
        self.assertEqual([event["type"] for event in bundle["run"]["action_events"]], ["post_liked", "company_followed"])
        self.assertEqual([event["type"] for event in bundle["report"]["events"] if event.get("type") in {"post_liked", "company_followed"}], ["post_liked", "company_followed"])

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

    def test_export_script_supports_sales_community_fixture(self) -> None:
        with TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "sales-community.bundle.json"
            fixture_path = Path("tests/fixtures/sales_community_report.json")

            exit_code = export_run_bundle_main(
                [
                    "--automation-name",
                    "linkedin-sales-community-engagement",
                    "--report-path",
                    str(fixture_path),
                    "--output",
                    str(output_path),
                ]
            )

            self.assertEqual(exit_code, 0)
            payload = json.loads(output_path.read_text())
            self.assertEqual(payload["automation"]["name"], "linkedin-sales-community-engagement")
            self.assertEqual(payload["automation"]["surface"], "sales-community")
            self.assertEqual(payload["metrics"]["actions_total"], 1)

    def test_build_run_bundle_supports_peerlist_scroll_engagement(self) -> None:
        report = {
            "run_id": "peerlist-scroll-1",
            "started_at": "2026-04-20T10:00:00+00:00",
            "finished_at": "2026-04-20T10:01:00+00:00",
            "status": "ok",
            "profile_name": "Daniel",
            "actor_verified": True,
            "has_challenge": False,
            "items_scanned": 6,
            "items_considered": 6,
            "upvotes_count": 1,
            "comments_count": 0,
            "follows_count": 0,
            "actions": [{"type": "upvote", "target": "visible_upvote_2", "verified": True}],
            "events": [
                {
                    "ts": "2026-04-20T10:00:30+00:00",
                    "type": "peerlist_post_upvoted",
                    "target_name": "Peerlist visible upvote 2",
                    "selector": "visible_upvote_2",
                    "verified": True,
                }
            ],
        }

        bundle = build_run_bundle(automation_name="peerlist-scroll-engagement", report=report)

        self.assertEqual(bundle["automation"]["platform"], "peerlist")
        self.assertEqual(bundle["automation"]["surface"], "scroll")
        self.assertEqual(bundle["run"]["profile_name"], "Daniel")
        self.assertEqual(bundle["metrics"]["actions_total"], 1)
        self.assertEqual(bundle["metrics"]["likes_count"], 1)
        self.assertEqual(bundle["run"]["action_events"][0]["type"], "peerlist_post_upvoted")

    def test_build_run_bundle_supports_peerlist_follow_workflow(self) -> None:
        report = {
            "run_id": "peerlist-follow-1",
            "started_at": "2026-04-20T11:00:00+00:00",
            "finished_at": "2026-04-20T11:02:00+00:00",
            "status": "ok",
            "profile_name": "Daniel",
            "actor_verified": True,
            "workflow_type": "follow",
            "workflow_parameters": {
                "type": "follow",
                "follows_per_day": 20,
                "unfollows_per_day": 1000,
                "unfollow_after_days": 14,
                "do_not_unfollow_peers": True,
            },
            "peerlist_profile_followers_before": 473,
            "peerlist_profile_followers_after": 474,
            "profiles_scanned": 12,
            "profiles_considered": 3,
            "follows_count": 1,
            "unfollows_count": 0,
            "actions": [
                {
                    "type": "follow",
                    "target_name": "Ada Builder",
                    "target_url": "https://peerlist.io/adabuilder",
                    "verified": True,
                }
            ],
            "events": [
                {
                    "ts": "2026-04-20T11:01:00+00:00",
                    "type": "peerlist_profile_followed",
                    "target_name": "Ada Builder",
                    "target_url": "https://peerlist.io/adabuilder",
                    "verified": True,
                }
            ],
        }

        bundle = build_run_bundle(automation_name="peerlist-follow-workflow", report=report)

        self.assertEqual(bundle["automation"]["platform"], "peerlist")
        self.assertEqual(bundle["automation"]["surface"], "network")
        self.assertEqual(bundle["automation"]["kind"], "workflow")
        self.assertEqual(bundle["automation"]["north_star_metric"], "peerlist_profile_followers")
        self.assertEqual(bundle["automation"]["parameters"]["do_not_unfollow_peers"], True)
        self.assertEqual(bundle["metrics"]["actions_total"], 1)
        self.assertEqual(bundle["metrics"]["follows_count"], 1)
        self.assertEqual(bundle["metrics"]["metrics_json"]["north_star_metric"], "peerlist_profile_followers")
        self.assertEqual(bundle["metrics"]["metrics_json"]["peerlist_profile_followers_delta"], 1)
        self.assertEqual(bundle["metrics"]["metrics_json"]["workflow_parameters"]["unfollow_after_days"], 14)
        self.assertEqual(bundle["run"]["action_events"][0]["type"], "peerlist_profile_followed")


if __name__ == "__main__":
    unittest.main()
