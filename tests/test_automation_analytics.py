import unittest

from automation_analytics import linkedin_company_profile_engagement_metrics, linkedin_sales_community_metrics
from linkedin_sales_community.models import CommunityRunReport
from linkedin.company_profile_engagement.models import RunReport


class AutomationAnalyticsTests(unittest.TestCase):
    def test_company_profile_metrics_normalize_actions(self) -> None:
        report = RunReport(
            run_id="run-1",
            started_at="2026-03-28T08:00:00+00:00",
            status="ok",
            actor_verified=True,
            search_shape_ok=True,
            posts_scanned=19,
            posts_liked=3,
            posts_reposted=1,
            comments_liked=2,
            agencies_scanned=4,
            agencies_followed=1,
        )
        metrics = linkedin_company_profile_engagement_metrics(report)
        self.assertEqual(metrics["items_scanned"], 19)
        self.assertEqual(metrics["actions_total"], 7)
        self.assertEqual(metrics["likes_count"], 3)
        self.assertEqual(metrics["reposts_count"], 1)
        self.assertEqual(metrics["comments_liked_count"], 2)
        self.assertEqual(metrics["follows_count"], 1)
        self.assertIn("posts_scanned", metrics["metrics_json"])

    def test_linkedin_sales_community_metrics_normalize_actions(self) -> None:
        report = CommunityRunReport(
            run_id="run-2",
            started_at="2026-03-28T08:00:00+00:00",
            status="ok",
            page_shape_ok=True,
            items_scanned=10,
            items_considered=4,
            items_liked=1,
        )
        metrics = linkedin_sales_community_metrics(report)
        self.assertEqual(metrics["items_scanned"], 10)
        self.assertEqual(metrics["items_considered"], 4)
        self.assertEqual(metrics["actions_total"], 1)
        self.assertEqual(metrics["likes_count"], 1)
        self.assertEqual(metrics["reposts_count"], 0)
        self.assertEqual(metrics["comments_liked_count"], 0)
        self.assertEqual(metrics["follows_count"], 0)


if __name__ == "__main__":
    unittest.main()
