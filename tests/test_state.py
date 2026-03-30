from pathlib import Path
import tempfile
import unittest

from linkedin.company_profile_engagement.models import CompanyFeedSnapshot, CompanySnapshot, CommentSnapshot, FeedSnapshot, PostSnapshot, RunReport
from linkedin.company_profile_engagement.state import StateStore


class StateStoreTests(unittest.TestCase):
    def test_close_incomplete_runs_marks_stale_started_rows_failed(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = StateStore(Path(temp_dir) / "state.sqlite3")
            store.start_run("run-stale", "2026-03-24T10:00:00+00:00")
            updated = store.close_incomplete_runs()

            row = store.conn.execute(
                "SELECT finished_at, status, stop_reason FROM runs WHERE run_id = ?",
                ("run-stale",),
            ).fetchone()

            self.assertEqual(updated, 1)
            self.assertEqual(row["finished_at"], "2026-03-24T10:00:00+00:00")
            self.assertEqual(row["status"], "failed")
            self.assertEqual(row["stop_reason"], "abandoned_started_row_cleanup")
            store.close()

    def test_state_store_tracks_processed_items(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = StateStore(Path(temp_dir) / "state.sqlite3")
            store.start_run("run-1", "2026-03-24T10:00:00+00:00")
            store.upsert_post(
                "post-1",
                "2026-03-24T10:00:01+00:00",
                post_url="https://www.linkedin.com/feed/update/post-1",
                liked=True,
                liked_by_actor=True,
            )
            store.upsert_comment("comment-1", "post-1", None, "2026-03-24T10:00:02+00:00", liked=True)
            self.assertTrue(store.post_processed("post-1"))
            self.assertTrue(store.comment_processed("comment-1"))
            store.finish_run(
                "run-1",
                finished_at="2026-03-24T10:01:00+00:00",
                status="ok",
                actor_verified=True,
                posts_scanned=1,
                posts_liked=1,
                posts_reposted=0,
                comments_liked=1,
                companies_scanned=0,
                companies_followed=0,
                stop_reason=None,
            )
            store.close()

    def test_state_store_records_snapshot_and_report_payloads(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = StateStore(Path(temp_dir) / "state.sqlite3")
            snapshot = FeedSnapshot(
                actor_name="Example Company",
                actor_verified=True,
                search_shape_ok=True,
                search_markers=["keyword:opportunities"],
                challenge_signals=[],
                posts=[
                    PostSnapshot(
                        post_id="post-1",
                        post_url="https://www.linkedin.com/feed/update/post-1",
                        text="A post body",
                        sponsored=False,
                        already_liked=False,
                        already_reposted=False,
                        interactable=True,
                        like_selector="card:0:like",
                        repost_selector="card:0:repost",
                        comments_expanded=True,
                        comment_toggle_selector="card:0:comment-toggle",
                        reply_toggle_selectors=["card:0:reply"],
                        comments=[
                            CommentSnapshot(
                                comment_id="comment-1",
                                parent_post_id="post-1",
                                parent_comment_id=None,
                                text="Comment body",
                                liked=False,
                                like_selector="card:0:comment:0:like",
                            )
                        ],
                    )
                ],
            )
            report = RunReport(run_id="run-2", started_at="2026-03-24T10:00:00+00:00", status="ok")
            store.upsert_post(
                "post-1",
                "2026-03-24T10:00:03+00:00",
                post_url="https://www.linkedin.com/feed/update/post-1",
                liked=False,
                liked_by_actor=False,
            )
            store.record_snapshot("run-2", 0, snapshot)
            store.record_run_report("run-2", "https://www.linkedin.com/search/results/content/", "/tmp/run-2.json", report)

            feed_row = store.conn.execute("SELECT posts_count FROM feed_snapshots WHERE run_id = ? AND pass_index = 0", ("run-2",)).fetchone()
            post_row = store.conn.execute(
                "SELECT post_url, text, repost_selector, already_reposted FROM post_observations WHERE run_id = ? AND pass_index = 0 AND post_id = ?",
                ("run-2", "post-1"),
            ).fetchone()
            comment_row = store.conn.execute("SELECT text FROM comment_observations WHERE run_id = ? AND pass_index = 0 AND comment_id = ?", ("run-2", "comment-1")).fetchone()
            posts_row = store.conn.execute("SELECT post_url FROM posts WHERE post_id = ?", ("post-1",)).fetchone()
            report_row = store.conn.execute("SELECT artifact_path FROM run_reports WHERE run_id = ?", ("run-2",)).fetchone()

            self.assertEqual(feed_row["posts_count"], 1)
            self.assertEqual(posts_row["post_url"], "https://www.linkedin.com/feed/update/post-1")
            self.assertEqual(post_row["post_url"], "https://www.linkedin.com/feed/update/post-1")
            self.assertEqual(post_row["text"], "A post body")
            self.assertEqual(post_row["repost_selector"], "card:0:repost")
            self.assertEqual(post_row["already_reposted"], 0)
            self.assertEqual(comment_row["text"], "Comment body")
            self.assertEqual(report_row["artifact_path"], "/tmp/run-2.json")
            store.close()

    def test_state_store_records_company_snapshots_and_observations(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = StateStore(Path(temp_dir) / "state.sqlite3")
            snapshot = CompanyFeedSnapshot(
                page_shape_ok=True,
                challenge_signals=[],
                following_count=1,
                active_tab="Recommended",
                companies=[
                    CompanySnapshot(
                        company_id="49127922",
                        company_url="https://www.linkedin.com/company/49127922/",
                        name="Senseven Health",
                        subtitle="Mental Health Care • Berlin",
                        followers_text="626 followers",
                        already_following=False,
                        follow_selector="company:0:follow",
                    )
                ],
            )
            store.upsert_company(
                "49127922",
                "2026-03-26T08:00:00+00:00",
                company_url="https://www.linkedin.com/company/49127922/",
                name="Senseven Health",
                subtitle="Mental Health Care • Berlin",
                followers_text="626 followers",
                followed=True,
                followed_at="2026-03-26T08:00:05+00:00",
            )
            store.record_company_snapshot("run-3", 0, snapshot)
            store.record_company_observation("run-3", 0, 0, snapshot.companies[0], action_taken="followed")

            snapshot_row = store.conn.execute(
                "SELECT agencies_count, following_count FROM agency_snapshots WHERE run_id = ? AND pass_index = ?",
                ("run-3", 0),
            ).fetchone()
            observation_row = store.conn.execute(
                "SELECT company_url, action_taken FROM agency_observations WHERE run_id = ? AND pass_index = ? AND company_id = ?",
                ("run-3", 0, "49127922"),
            ).fetchone()
            agency_row = store.conn.execute(
                "SELECT followed, followed_at FROM agencies WHERE company_id = ?",
                ("49127922",),
            ).fetchone()

            self.assertEqual(snapshot_row["agencies_count"], 1)
            self.assertEqual(snapshot_row["following_count"], 1)
            self.assertEqual(observation_row["company_url"], "https://www.linkedin.com/company/49127922/")
            self.assertEqual(observation_row["action_taken"], "followed")
            self.assertEqual(agency_row["followed"], 1)
            self.assertEqual(agency_row["followed_at"], "2026-03-26T08:00:05+00:00")
            store.close()


if __name__ == "__main__":
    unittest.main()
