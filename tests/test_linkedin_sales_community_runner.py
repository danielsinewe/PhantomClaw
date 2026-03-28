import unittest

from linkedin_sales_community.runner import parse_args


class LinkedInSalesCommunityRunnerTests(unittest.TestCase):
    def test_parse_args_requires_profile_for_live_runs(self) -> None:
        with self.assertRaisesRegex(SystemExit, "LINKEDIN_SALES_COMMUNITY_PROFILE"):
            parse_args([])

    def test_parse_args_allows_dry_run_without_profile(self) -> None:
        args = parse_args(["--dry-run"])
        self.assertTrue(args.dry_run)
        self.assertIsNone(args.chrome_profile)


if __name__ == "__main__":
    unittest.main()
