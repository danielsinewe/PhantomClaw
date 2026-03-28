from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from linkedin.sales_community_engagement.models import CommunityItem, CommunitySnapshot, CommunityRunReport
from linkedin.sales_community_engagement.runner import resolve_state_index
from linkedin.sales_community_engagement.state import StateStore


FIXTURES = Path("tests/fixtures")


class LinkedInSalesCommunityTests(unittest.TestCase):
    def test_resolve_state_index_matches_label(self) -> None:
        state = "[28]<a />\n\tExplore Onboarding\n[29]<a />\n\tVisit the Sales Assistant Hub"
        self.assertEqual(resolve_state_index(state, "Explore Onboarding"), 28)
        self.assertEqual(resolve_state_index(state, "Visit the Sales Assistant Hub"), 29)

    def test_fixture_models_store_state(self) -> None:
        html = (FIXTURES / "linkedin_sales_community.html").read_text()
        self.assertIn("LinkedIn Sales Community", html)

        snapshot = CommunitySnapshot(
            page_title="LinkedIn Sales Community",
            logged_in=True,
            page_shape_ok=True,
            challenge_signals=[],
            items=[
                CommunityItem(
            item_id="item-1",
            title="Top member this week",
            subtitle=None,
            detail="Leaderboard spotlight",
            action_label="Like",
            action_selector='button[aria-label="Like"]',
            high_signal=True,
                )
            ],
        )

        with TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "state.sqlite3"
            store = StateStore(db_path)
            report = CommunityRunReport(run_id="run-1", started_at="2026-03-26T09:31:53+00:00")
            store.start_run(report.run_id, report.started_at)
            store.record_snapshot(report.run_id, 0, snapshot)
            report.status = "ok"
            report.page_shape_ok = True
            report.items_scanned = 1
            report.items_considered = 1
            report.items_liked = 1
            store.finish_run(
                report.run_id,
                finished_at="2026-03-26T09:32:03+00:00",
                status=report.status,
                page_shape_ok=report.page_shape_ok,
                items_scanned=report.items_scanned,
                items_considered=report.items_considered,
                items_liked=report.items_liked,
                stop_reason=None,
            )
            row = store.conn.execute("SELECT status, items_liked FROM runs WHERE run_id = ?", (report.run_id,)).fetchone()
            self.assertEqual(row["status"], "ok")
            self.assertEqual(row["items_liked"], 1)
            store.close()


if __name__ == "__main__":
    unittest.main()
