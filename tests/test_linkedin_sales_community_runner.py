import unittest
from pathlib import Path

from linkedin.sales_community_engagement.runner import fixture_payload, parse_args


class LinkedInSalesCommunityRunnerTests(unittest.TestCase):
    def test_parse_args_requires_profile_for_live_runs(self) -> None:
        with self.assertRaisesRegex(SystemExit, "LINKEDIN_SALES_COMMUNITY_ENGAGEMENT_PROFILE"):
            parse_args([])

    def test_parse_args_allows_dry_run_without_profile(self) -> None:
        args = parse_args(["--dry-run"])
        self.assertTrue(args.dry_run)
        self.assertIsNone(args.chrome_profile)

    def test_parse_args_requires_dry_run_for_fixture(self) -> None:
        with self.assertRaisesRegex(SystemExit, "--fixture requires --dry-run"):
            parse_args(["--fixture", "tests/fixtures/linkedin_sales_community.html"])

    def test_fixture_payload_extracts_sales_community_items(self) -> None:
        payload = fixture_payload(Path("tests/fixtures/linkedin_sales_community.html"))

        self.assertEqual(payload["page_title"], "LinkedIn Sales Community")
        self.assertTrue(payload["logged_in"])
        self.assertTrue(payload["page_shape_ok"])
        self.assertEqual(len(payload["items"]), 2)
        self.assertEqual(payload["items"][0]["action_label"], "Like")
        self.assertTrue(payload["items"][0]["high_signal"])


if __name__ == "__main__":
    unittest.main()
