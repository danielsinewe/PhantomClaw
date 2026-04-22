import unittest

from automation_analytics import (
    ANALYTICS_POSTGRES_ACTION_EVENTS_VIEW_SCHEMA,
    ANALYTICS_POSTGRES_VIEW_SCHEMA,
    NORTH_STAR_DAILY_METRICS_TABLE_SCHEMA,
    NORTH_STAR_DAILY_METRICS_VIEW_SCHEMA,
    action_events_from_report,
    extract_post_excerpt,
    extract_post_target_name,
    linkedin_company_profile_engagement_metrics,
    linkedin_sales_community_metrics,
    normalize_report_payload,
    peerlist_follow_workflow_metrics,
)
from linkedin.company_profile_engagement.models import RunReport
from linkedin.sales_community_engagement.models import CommunityRunReport


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
            companies_scanned=4,
            companies_followed=1,
        )
        metrics = linkedin_company_profile_engagement_metrics(report)
        self.assertEqual(metrics["items_scanned"], 19)
        self.assertEqual(metrics["actions_total"], 7)
        self.assertEqual(metrics["likes_count"], 3)
        self.assertEqual(metrics["reposts_count"], 1)
        self.assertEqual(metrics["comments_liked_count"], 2)
        self.assertEqual(metrics["follows_count"], 1)
        self.assertEqual(metrics["companies_scanned"], 4)
        self.assertEqual(metrics["companies_followed"], 1)
        self.assertIn("posts_scanned", metrics["metrics_json"])

    def test_action_events_from_report_extracts_successful_actions(self) -> None:
        report = RunReport(
            run_id="run-action-events",
            started_at="2026-03-28T08:00:00+00:00",
            status="ok",
            profile_name="TrustOutreach",
        )
        report.events.extend(
            [
                {"ts": "2026-03-28T08:00:01+00:00", "type": "snapshot_loaded"},
                {"ts": "2026-03-28T08:00:02+00:00", "type": "post_liked", "post_id": "urn:li:activity:1001"},
                {"ts": "2026-03-28T08:00:03+00:00", "type": "company_followed", "company_id": "49127922"},
                {"ts": "2026-03-28T08:00:04+00:00", "type": "item_action_taken", "item_id": "item-1"},
            ]
        )

        action_events = action_events_from_report(report)

        self.assertEqual([event["type"] for event in action_events], ["post_liked", "company_followed", "item_action_taken"])

    def test_normalize_report_payload_renames_legacy_company_terms(self) -> None:
        report = {
            "run_id": "run-normalize",
            "started_at": "2026-03-28T08:00:00+00:00",
            "status": "ok",
            "stop_reason": "company_follow_page_shape_changed",
            "agencies_scanned": 0,
            "agencies_followed": 0,
            "events": [
                {
                    "ts": "2026-03-28T08:00:01+00:00",
                    "type": "company_followed",
                    "reason": "company_follow_page_shape_changed",
                },
                {
                    "ts": "2026-03-28T08:00:02+00:00",
                    "type": "company_skipped",
                    "reason": "company_follow_challenge_signals",
                },
            ],
            "skips": [
                {"reason": "company_follow_page_shape_changed"},
            ],
        }

        normalized = normalize_report_payload(report)

        self.assertEqual(normalized["stop_reason"], "company_follow_page_shape_changed")
        self.assertEqual(normalized["companies_scanned"], 0)
        self.assertEqual(normalized["companies_followed"], 0)
        self.assertEqual(normalized["events"][0]["type"], "company_followed")
        self.assertEqual(normalized["events"][0]["reason"], "company_follow_page_shape_changed")
        self.assertEqual(normalized["events"][1]["type"], "company_skipped")
        self.assertEqual(normalized["events"][1]["reason"], "company_follow_challenge_signals")
        self.assertEqual(normalized["skips"][0]["reason"], "company_follow_page_shape_changed")

    def test_action_events_view_schema_exposes_drilldown_rows(self) -> None:
        self.assertIn("automation_action_events_v1", ANALYTICS_POSTGRES_ACTION_EVENTS_VIEW_SCHEMA)
        self.assertIn("action_label", ANALYTICS_POSTGRES_ACTION_EVENTS_VIEW_SCHEMA)
        self.assertIn("target_url", ANALYTICS_POSTGRES_ACTION_EVENTS_VIEW_SCHEMA)
        self.assertIn("target_locator", ANALYTICS_POSTGRES_ACTION_EVENTS_VIEW_SCHEMA)
        self.assertIn("target_summary", ANALYTICS_POSTGRES_ACTION_EVENTS_VIEW_SCHEMA)
        self.assertIn("target_excerpt", ANALYTICS_POSTGRES_ACTION_EVENTS_VIEW_SCHEMA)
        self.assertIn("profile_name", ANALYTICS_POSTGRES_ACTION_EVENTS_VIEW_SCHEMA)
        self.assertIn("actor_name", ANALYTICS_POSTGRES_ACTION_EVENTS_VIEW_SCHEMA)

    def test_post_target_extraction_uses_feed_text(self) -> None:
        text = (
            "Feed post\n\n"
            "⚡George Trajkovski\n\n"
            " \n • 1st\n\n"
            "Team Lead @ Instantly.ai | Account Management | Cold Email Expert\n\n"
            "11h • Edited •\n\n"
            "Most people only see the win."
        )
        self.assertEqual(extract_post_target_name(text), "George Trajkovski")
        self.assertEqual(extract_post_excerpt(text), "George Trajkovski 1st Team Lead @ Instantly.ai | Account Management | Cold Email Expert 11h Edited Most people only see the win.")

    def test_summary_view_schema_exposes_profile_name(self) -> None:
        self.assertIn("automation_kpi_runs_v1", ANALYTICS_POSTGRES_VIEW_SCHEMA)
        self.assertIn("profile_name", ANALYTICS_POSTGRES_VIEW_SCHEMA)
        self.assertIn("workspace_slug", ANALYTICS_POSTGRES_VIEW_SCHEMA)
        self.assertIn("companies_followed", ANALYTICS_POSTGRES_VIEW_SCHEMA)
        self.assertIn("reposted_post_url", ANALYTICS_POSTGRES_VIEW_SCHEMA)
        self.assertIn("north_star_metric", ANALYTICS_POSTGRES_VIEW_SCHEMA)
        self.assertIn("workflow_type", ANALYTICS_POSTGRES_VIEW_SCHEMA)
        self.assertIn("peerlist_profile_followers_delta", ANALYTICS_POSTGRES_VIEW_SCHEMA)
        self.assertIn("unfollows_count", ANALYTICS_POSTGRES_VIEW_SCHEMA)
        self.assertIn("peers_preserved_count", ANALYTICS_POSTGRES_VIEW_SCHEMA)
        self.assertIn("skipped_count", ANALYTICS_POSTGRES_VIEW_SCHEMA)
        self.assertIn("blockers_count", ANALYTICS_POSTGRES_VIEW_SCHEMA)

    def test_daily_metrics_schema_tracks_north_star_snapshots(self) -> None:
        self.assertIn("automation_daily_metrics", NORTH_STAR_DAILY_METRICS_TABLE_SCHEMA)
        self.assertIn("snapshot_id BIGSERIAL", NORTH_STAR_DAILY_METRICS_TABLE_SCHEMA)
        self.assertIn("metric_date DATE NOT NULL", NORTH_STAR_DAILY_METRICS_TABLE_SCHEMA)
        self.assertIn("metric_value NUMERIC NOT NULL", NORTH_STAR_DAILY_METRICS_TABLE_SCHEMA)
        self.assertNotIn("PRIMARY KEY", NORTH_STAR_DAILY_METRICS_TABLE_SCHEMA)
        self.assertIn("DROP CONSTRAINT IF EXISTS automation_daily_metrics_pkey", NORTH_STAR_DAILY_METRICS_TABLE_SCHEMA)
        self.assertIn("automation_daily_metrics_v1", NORTH_STAR_DAILY_METRICS_VIEW_SCHEMA)
        self.assertIn("automation_daily_metric_daily_latest_v1", NORTH_STAR_DAILY_METRICS_VIEW_SCHEMA)
        self.assertIn("captured_at_ts", NORTH_STAR_DAILY_METRICS_VIEW_SCHEMA)
        self.assertIn("snapshot_delta", NORTH_STAR_DAILY_METRICS_VIEW_SCHEMA)
        self.assertIn("daily_delta", NORTH_STAR_DAILY_METRICS_VIEW_SCHEMA)

    def test_action_events_view_schema_exposes_verified(self) -> None:
        self.assertIn("verified", ANALYTICS_POSTGRES_ACTION_EVENTS_VIEW_SCHEMA)
        self.assertIn("action_event->>'verified'", ANALYTICS_POSTGRES_ACTION_EVENTS_VIEW_SCHEMA)

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

    def test_peerlist_follow_workflow_metrics_exposes_dashboard_fields(self) -> None:
        metrics = peerlist_follow_workflow_metrics(
            {
                "actor_verified": True,
                "workflow_type": "follow",
                "workflow_parameters": {
                    "type": "follow",
                    "follows_per_day": 20,
                    "unfollows_per_day": 10,
                    "unfollow_after_days": 14,
                    "do_not_unfollow_peers": True,
                },
                "peerlist_profile_followers_before": 473,
                "peerlist_profile_followers_after": 474,
                "profiles_scanned": 12,
                "profiles_considered": 3,
                "follows_count": 1,
                "unfollows_count": 0,
                "skipped": [{"reason": "peer_preserved"}],
                "blockers": [],
            }
        )

        self.assertEqual(metrics["metrics_json"]["north_star_metric"], "peerlist_profile_followers")
        self.assertEqual(metrics["metrics_json"]["peerlist_profile_followers_delta"], 1)
        self.assertEqual(metrics["metrics_json"]["unfollows_count"], 0)
        self.assertEqual(metrics["metrics_json"]["peers_preserved_count"], 1)


if __name__ == "__main__":
    unittest.main()
