import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from peerlist.follow_workflow.browser_use_agent import (
    DEFAULT_PROXY_COUNTRY_CODE,
    build_peerlist_follow_task,
    build_parser,
    main,
    report_from_browser_use_output,
)


class PeerlistBrowserUseAgentTests(unittest.TestCase):
    def test_task_defaults_to_dry_run_without_mutations(self) -> None:
        task = build_peerlist_follow_task(
            parameters={
                "type": "follow",
                "follows_per_day": 20,
                "unfollows_per_day": 10,
                "unfollow_after_days": 14,
                "do_not_unfollow_peers": True,
            },
            live=False,
        )

        self.assertIn("DRY RUN MODE", task)
        self.assertIn("Do not click follow or unfollow", task)
        self.assertIn('"peerlist_profile_followed"', task)
        self.assertIn('"peerlist_profile_unfollowed"', task)
        self.assertIn('"do_not_unfollow_peers": true', task)

    def test_report_from_browser_use_output_parses_json_and_fills_defaults(self) -> None:
        parameters = {
            "type": "follow",
            "follows_per_day": 20,
            "unfollows_per_day": 10,
            "unfollow_after_days": 14,
            "do_not_unfollow_peers": True,
        }
        raw = json.dumps(
            {
                "run_id": "peerlist-follow-agent-1",
                "started_at": "2026-04-20T12:00:00+00:00",
                "finished_at": "2026-04-20T12:01:00+00:00",
                "status": "no_action",
                "profile_name": "Daniel",
                "actor_verified": True,
                "profiles_scanned": 4,
            }
        )

        report = report_from_browser_use_output(raw, parameters=parameters)

        self.assertEqual(report["workflow_type"], "follow")
        self.assertEqual(report["workflow_parameters"]["unfollow_after_days"], 14)
        self.assertEqual(report["profiles_scanned"], 4)
        self.assertEqual(report["follows_count"], 0)
        self.assertEqual(report["events"], [])

    def test_task_only_does_not_require_api_key(self) -> None:
        with TemporaryDirectory() as tmpdir:
            exit_code = main(
                [
                    "--profile-id",
                    "test-profile",
                    "--task-output",
                    str(Path(tmpdir) / "task.txt"),
                    "--task-only",
                ]
            )

        self.assertEqual(exit_code, 0)

    def test_defaults_match_remote_peerlist_profile_context(self) -> None:
        args = build_parser().parse_args(["--profile-id", "test-profile", "--task-only"])

        self.assertEqual(DEFAULT_PROXY_COUNTRY_CODE, "de")
        self.assertEqual(args.proxy_country_code, "de")
        self.assertIsNone(args.op_vault_id)
        self.assertIsNone(args.allowed_domains)


if __name__ == "__main__":
    unittest.main()
