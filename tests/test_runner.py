from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from linkedin.company_profile_engagement.config import RunnerConfig
from linkedin.company_profile_engagement.models import CompanyFeedSnapshot, CompanySnapshot, CommentSnapshot, FeedSnapshot, PostSnapshot, RunReport
from linkedin.company_profile_engagement.runner import build_browser_session_name, process_agency_follows, process_feed
from linkedin.company_profile_engagement.state import StateStore


def make_post(post_id: str) -> PostSnapshot:
    return PostSnapshot(
        post_id=post_id,
        post_url=f"https://www.linkedin.com/feed/update/{post_id}",
        text=f"Post {post_id}",
        sponsored=False,
        already_liked=False,
        already_reposted=False,
        interactable=True,
        like_selector=f"selector:{post_id}",
        repost_selector=f"selector:{post_id}:repost",
        comments_expanded=False,
        comment_toggle_selector=None,
        reply_toggle_selectors=[],
        comments=[],
    )


def make_snapshot(*post_ids: str, search_shape_ok: bool = True) -> FeedSnapshot:
    return FeedSnapshot(
        actor_name="Example Company",
        actor_verified=True,
        search_shape_ok=search_shape_ok,
        search_markers=["keyword:opportunities", "content-view", "latest-sort", "photo-filter", "org-filter"]
        if search_shape_ok
        else ["keyword:opportunities"],
        challenge_signals=[],
        posts=[make_post(post_id) for post_id in post_ids],
    )


class FakeBrowser:
    def __init__(self) -> None:
        self.clicks: list[str] = []
        self.actor_requests: list[str] = []
        self.scrolls: list[int] = []
        self.follow_scrolls: list[int] = []
        self.follow_tabs: list[str] = []
        self.sleeps: list[float] = []
        self.opens: list[str] = []
        self.load_more_calls = 0
        self.load_more_result = False
        self.comment_load_more_calls: list[int] = []
        self.comment_load_more_result = False
        self.ensure_actor_result = True
        self.page_state = {
            "url": "https://www.linkedin.com/feed/",
            "title": "LinkedIn",
            "has_actor_selector": True,
            "logged_out": False,
        }

    def open(self, url: str) -> None:
        self.opens.append(url)

    def ensure_actor(self, actor_name: str) -> bool:
        self.actor_requests.append(actor_name)
        return self.ensure_actor_result and actor_name == "Example Company"

    def get_page_state(self) -> dict[str, object]:
        return dict(self.page_state)

    def click_selector(self, selector: str) -> None:
        self.clicks.append(selector)

    def scroll_down(self, amount: int) -> None:
        self.scrolls.append(amount)

    def scroll_results(self, amount: int) -> None:
        self.scrolls.append(amount)

    def load_more_results(self) -> bool:
        self.load_more_calls += 1
        return self.load_more_result

    def load_more_comments(self, card_index: int) -> bool:
        self.comment_load_more_calls.append(card_index)
        return self.comment_load_more_result

    def scroll_follow_modal(self, amount: int) -> bool:
        self.follow_scrolls.append(amount)
        return True

    def select_follow_tab(self, label: str) -> bool:
        self.follow_tabs.append(label)
        return True

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)


class RunnerTests(unittest.TestCase):
    def test_build_browser_session_name_uses_run_id_prefix(self) -> None:
        self.assertEqual(
            build_browser_session_name("linkedin-company-profile-engagement", "149f04017fc14d62afddacb8c800c921"),
            "linkedin-company-profile-engagement-149f0401",
        )

    def make_config(self, artifact_dir: Path) -> RunnerConfig:
        return RunnerConfig(
            search_url="https://www.linkedin.com/search/results/content/",
            chrome_profile="work-profile",
            actor_name="Example Company",
            session_name="test-session",
            post_cap=3,
            repost_cap=1,
            comment_cap=0,
            max_passes=6,
            follow_admin_url="https://www.linkedin.com/company/109821516/admin/dashboard/?manageFollowing=true",
            follow_cap=25,
            dry_run=False,
            fixture_path=None,
            database_url=None,
            analytics_database_url=None,
            db_path=artifact_dir / "state.sqlite3",
            artifact_dir=artifact_dir,
            success_screenshot=False,
        )

    def test_process_feed_scrolls_for_additional_posts(self) -> None:
        with TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir)
            store = StateStore(artifact_dir / "state.sqlite3")
            timestamp = "2026-03-24T19:00:00+00:00"
            for post_id in ("p1", "p2", "p3"):
                store.upsert_post(post_id, timestamp, liked=False, liked_by_actor=True)

            browser = FakeBrowser()
            report = RunReport(run_id="run-1", started_at=timestamp)
            first = make_snapshot("p1", "p2", "p3")
            second = make_snapshot("p3", "p4", "p5")

            with patch("linkedin.company_profile_engagement.runner.capture_current_snapshot", return_value=second):
                process_feed(first, store, report, browser, self.make_config(artifact_dir))

            self.assertEqual(report.status, "started")
            self.assertEqual(report.posts_scanned, 5)
            self.assertEqual(report.posts_liked, 2)
            self.assertEqual(browser.clicks, ["selector:p4", "selector:p4:repost", "selector:p5"])
            self.assertEqual(browser.load_more_calls, 3)
            self.assertEqual(browser.scrolls, [1400, 1400, 1400])
            store.close()

    def test_process_agency_follows_confirms_follow_and_persists_agency(self) -> None:
        with TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir)
            store = StateStore(artifact_dir / "state.sqlite3")
            browser = FakeBrowser()
            report = RunReport(run_id="run-follow", started_at="2026-03-26T08:00:00+00:00")
            config = self.make_config(artifact_dir)
            config.post_cap = 0
            config.repost_cap = 0
            config.comment_cap = 0
            config.follow_cap = 2
            first = CompanyFeedSnapshot(
                page_shape_ok=True,
                challenge_signals=[],
                following_count=0,
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
            confirmed = CompanyFeedSnapshot(
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
                        already_following=True,
                        follow_selector=None,
                    )
                ],
            )

            with patch("linkedin.company_profile_engagement.runner.capture_agency_snapshot", side_effect=[first, confirmed, confirmed, confirmed]):
                process_agency_follows(store, report, browser, config)

            self.assertEqual(report.companies_scanned, 1)
            self.assertEqual(report.companies_followed, 1)
            self.assertIn("company:0:follow", browser.clicks)
            agency_row = store.conn.execute("SELECT followed FROM agencies WHERE company_id = ?", ("49127922",)).fetchone()
            observation_row = store.conn.execute(
                "SELECT action_taken FROM agency_observations WHERE run_id = ? AND company_id = ?",
                ("run-follow", "49127922"),
            ).fetchone()
            self.assertEqual(agency_row["followed"], 1)
            self.assertEqual(observation_row["action_taken"], "followed")
            store.close()

    def test_process_agency_follows_confirms_by_following_count_increase(self) -> None:
        with TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir)
            store = StateStore(artifact_dir / "state.sqlite3")
            browser = FakeBrowser()
            report = RunReport(run_id="run-follow-count", started_at="2026-03-26T08:00:00+00:00")
            config = self.make_config(artifact_dir)
            first = CompanyFeedSnapshot(
                page_shape_ok=True,
                challenge_signals=[],
                following_count=0,
                active_tab="Recommended",
                companies=[
                    CompanySnapshot(
                        company_id="104602195",
                        company_url="https://www.linkedin.com/company/104602195/",
                        name="Tabula",
                        subtitle="Software Development • Berlin",
                        followers_text="2,392 followers",
                        already_following=False,
                        follow_selector="company:0:follow",
                    )
                ],
            )
            switched = CompanyFeedSnapshot(
                page_shape_ok=True,
                challenge_signals=[],
                following_count=1,
                active_tab="Following (1)",
                companies=[],
            )

            with patch("linkedin.company_profile_engagement.runner.capture_agency_snapshot", side_effect=[first, switched, switched, switched]):
                process_agency_follows(store, report, browser, config)

            self.assertEqual(report.companies_followed, 1)
            agency_row = store.conn.execute("SELECT followed FROM agencies WHERE company_id = ?", ("104602195",)).fetchone()
            self.assertEqual(agency_row["followed"], 1)
            store.close()

    def test_process_agency_follows_stops_on_shape_drift(self) -> None:
        with TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir)
            store = StateStore(artifact_dir / "state.sqlite3")
            browser = FakeBrowser()
            report = RunReport(run_id="run-follow-drift", started_at="2026-03-26T08:00:00+00:00")
            config = self.make_config(artifact_dir)
            invalid = CompanyFeedSnapshot(
                page_shape_ok=False,
                challenge_signals=[],
                following_count=None,
                active_tab=None,
                companies=[],
            )

            with patch("linkedin.company_profile_engagement.runner.capture_agency_snapshot", return_value=invalid):
                process_agency_follows(store, report, browser, config)

            self.assertEqual(report.status, "stopped")
            self.assertEqual(report.stop_reason, "company_follow_page_shape_changed")
            self.assertEqual(report.companies_followed, 0)
            store.close()

    def test_process_feed_prefers_load_more_before_scroll(self) -> None:
        with TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir)
            store = StateStore(artifact_dir / "state.sqlite3")
            timestamp = "2026-03-24T19:00:00+00:00"
            for post_id in ("p1", "p2", "p3"):
                store.upsert_post(post_id, timestamp, liked=False, liked_by_actor=True)

            browser = FakeBrowser()
            browser.load_more_result = True
            report = RunReport(run_id="run-load-more", started_at=timestamp)
            first = make_snapshot("p1", "p2", "p3")
            second = make_snapshot("p3", "p4")

            with patch("linkedin.company_profile_engagement.runner.capture_current_snapshot", return_value=second):
                process_feed(first, store, report, browser, self.make_config(artifact_dir))

            self.assertEqual(report.posts_scanned, 4)
            self.assertEqual(report.posts_liked, 1)
            self.assertEqual(browser.load_more_calls, 3)
            self.assertEqual(browser.scrolls, [])
            self.assertTrue(any(event.get("type") == "results_advanced" and event.get("mode") == "load_more" for event in report.events))
            store.close()

    def test_process_feed_stops_on_scrolled_search_drift(self) -> None:
        with TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir)
            store = StateStore(artifact_dir / "state.sqlite3")
            timestamp = "2026-03-24T19:00:00+00:00"
            store.upsert_post("p1", timestamp, liked=False, liked_by_actor=True)

            browser = FakeBrowser()
            report = RunReport(run_id="run-2", started_at=timestamp)
            first = make_snapshot("p1")
            drifted = make_snapshot("p2", search_shape_ok=False)

            with patch("linkedin.company_profile_engagement.runner.capture_current_snapshot", return_value=drifted):
                process_feed(first, store, report, browser, self.make_config(artifact_dir))

            self.assertEqual(report.status, "stopped")
            self.assertEqual(report.stop_reason, "search_shape_changed")
            self.assertEqual(report.posts_liked, 0)
            self.assertEqual(browser.scrolls, [1400])
            store.close()

    def test_process_feed_reposts_once_up_to_cap(self) -> None:
        with TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir)
            store = StateStore(artifact_dir / "state.sqlite3")
            timestamp = "2026-03-24T19:00:00+00:00"
            browser = FakeBrowser()
            report = RunReport(run_id="run-repost", started_at=timestamp)
            first = make_snapshot("p1", "p2")
            config = self.make_config(artifact_dir)
            config.post_cap = 0
            config.repost_cap = 1
            config.max_passes = 0

            with patch("linkedin.company_profile_engagement.runner.capture_current_snapshot", return_value=first):
                process_feed(first, store, report, browser, config)

            self.assertEqual(report.posts_liked, 0)
            self.assertEqual(report.posts_reposted, 1)
            self.assertEqual(browser.clicks, ["selector:p1:repost"])
            self.assertEqual(browser.actor_requests, ["Example Company"])
            self.assertTrue(store.post_reposted("p1"))
            self.assertFalse(store.post_reposted("p2"))
            store.close()

    def test_process_feed_stops_when_repost_actor_cannot_be_verified(self) -> None:
        with TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir)
            store = StateStore(artifact_dir / "state.sqlite3")
            timestamp = "2026-03-30T15:00:00+00:00"
            browser = FakeBrowser()
            report = RunReport(run_id="run-repost-actor-mismatch", started_at=timestamp)
            first = make_snapshot("p1")
            config = self.make_config(artifact_dir)
            config.post_cap = 0
            config.repost_cap = 1
            config.max_passes = 0

            bad_refresh = FeedSnapshot(
                actor_name="Daniel Sinewe",
                actor_verified=False,
                search_shape_ok=True,
                search_markers=["keyword:opportunities", "content-view", "latest-sort", "photo-filter", "org-filter"],
                challenge_signals=[],
                posts=[make_post("p1")],
            )

            with patch("linkedin.company_profile_engagement.runner.capture_current_snapshot", return_value=bad_refresh):
                process_feed(first, store, report, browser, config)

            self.assertEqual(report.status, "stopped")
            self.assertEqual(report.stop_reason, "actor_mismatch")
            self.assertEqual(report.posts_reposted, 0)
            self.assertEqual(browser.clicks, [])
            self.assertEqual(browser.actor_requests, ["Example Company"])
            self.assertFalse(store.post_reposted("p1"))
            store.close()

    def test_process_feed_visits_post_url_for_unprocessed_comments(self) -> None:
        with TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir)
            store = StateStore(artifact_dir / "state.sqlite3")
            timestamp = "2026-03-24T19:00:00+00:00"
            store.upsert_post(
                "p1",
                timestamp,
                post_url="https://www.linkedin.com/feed/update/p1",
                liked=True,
                liked_by_actor=True,
            )

            browser = FakeBrowser()
            report = RunReport(run_id="run-3", started_at=timestamp)
            first = make_snapshot("p1")
            config = self.make_config(artifact_dir)
            config.comment_cap = 12
            config.repost_cap = 0
            config.max_passes = 0
            detail = FeedSnapshot(
                actor_name="Example Company",
                actor_verified=True,
                search_shape_ok=False,
                search_markers=[],
                challenge_signals=[],
                posts=[
                    PostSnapshot(
                        post_id="p1",
                        post_url=None,
                        text="Post p1",
                        sponsored=False,
                        already_liked=True,
                        already_reposted=False,
                        interactable=True,
                        like_selector="selector:p1",
                        repost_selector="selector:p1:repost",
                        comments_expanded=True,
                        comment_toggle_selector=None,
                        reply_toggle_selectors=[],
                        comments=[
                            CommentSnapshot(
                                comment_id="comment-1",
                                parent_post_id="p1",
                                parent_comment_id=None,
                                text="Need to like",
                                liked=False,
                                like_selector="card:0:comment:0:like",
                            )
                        ],
                    )
                ],
            )

            with patch("linkedin.company_profile_engagement.runner.capture_current_snapshot", side_effect=[detail]):
                process_feed(first, store, report, browser, config)

            self.assertEqual(report.comments_liked, 1)
            self.assertEqual(browser.opens, ["https://www.linkedin.com/feed/update/p1"])
            self.assertIn("card:0:comment:0:like", browser.clicks)
            store.close()

    def test_process_feed_skips_detail_page_when_actor_cannot_be_verified(self) -> None:
        with TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir)
            store = StateStore(artifact_dir / "state.sqlite3")
            timestamp = "2026-03-25T16:00:00+00:00"
            store.upsert_post(
                "p1",
                timestamp,
                post_url="https://www.linkedin.com/feed/update/p1",
                liked=True,
                liked_by_actor=True,
            )

            browser = FakeBrowser()
            browser.ensure_actor_result = False
            report = RunReport(run_id="run-detail-skip", started_at=timestamp)
            first = make_snapshot("p1")
            config = self.make_config(artifact_dir)
            config.comment_cap = 12
            config.repost_cap = 0
            config.max_passes = 0
            detail = FeedSnapshot(
                actor_name=None,
                actor_verified=False,
                search_shape_ok=False,
                search_markers=[],
                challenge_signals=[],
                posts=[],
            )

            with patch("linkedin.company_profile_engagement.runner.capture_current_snapshot", side_effect=[detail]):
                process_feed(first, store, report, browser, config)

            self.assertEqual(report.status, "started")
            self.assertIsNone(report.stop_reason)
            self.assertEqual(report.comments_liked, 0)
            self.assertEqual(browser.opens, ["https://www.linkedin.com/feed/update/p1"])
            self.assertTrue(any(skip.get("reason") == "detail_actor_mismatch" for skip in report.skips))
            self.assertTrue(
                any(
                    event.get("type") == "detail_page_skipped" and event.get("reason") == "actor_mismatch"
                    for event in report.events
                )
            )
            store.close()

    def test_process_feed_uses_inherited_actor_on_detail_page_without_selector(self) -> None:
        with TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir)
            store = StateStore(artifact_dir / "state.sqlite3")
            timestamp = "2026-03-27T10:00:00+00:00"
            store.upsert_post(
                "p1",
                timestamp,
                post_url="https://www.linkedin.com/feed/update/p1",
                liked=True,
                liked_by_actor=True,
            )

            browser = FakeBrowser()
            browser.page_state["has_actor_selector"] = False
            report = RunReport(run_id="run-detail-inherit", started_at=timestamp, actor_verified=True)
            first = make_snapshot("p1")
            config = self.make_config(artifact_dir)
            config.comment_cap = 12
            config.repost_cap = 0
            config.max_passes = 0
            detail = FeedSnapshot(
                actor_name=None,
                actor_verified=False,
                search_shape_ok=False,
                search_markers=[],
                challenge_signals=[],
                posts=[
                    PostSnapshot(
                        post_id="p1",
                        post_url=None,
                        text="Post p1",
                        sponsored=False,
                        already_liked=True,
                        already_reposted=False,
                        interactable=True,
                        like_selector="selector:p1",
                        repost_selector="selector:p1:repost",
                        comments_expanded=True,
                        comment_toggle_selector=None,
                        reply_toggle_selectors=[],
                        comments=[
                            CommentSnapshot(
                                comment_id="comment-1",
                                parent_post_id="p1",
                                parent_comment_id=None,
                                text="Need to like",
                                liked=False,
                                like_selector="card:0:comment:0:like",
                            )
                        ],
                    )
                ],
            )

            with patch("linkedin.company_profile_engagement.runner.capture_current_snapshot", side_effect=[detail]):
                process_feed(first, store, report, browser, config)

            self.assertEqual(report.status, "started")
            self.assertEqual(report.comments_liked, 1)
            self.assertEqual(browser.opens, ["https://www.linkedin.com/feed/update/p1"])
            self.assertIn("card:0:comment:0:like", browser.clicks)
            self.assertTrue(any(event.get("type") == "detail_actor_inherited" for event in report.events))
            store.close()

    def test_process_feed_stops_when_detail_page_redirects_to_login(self) -> None:
        with TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir)
            store = StateStore(artifact_dir / "state.sqlite3")
            timestamp = "2026-03-27T10:00:00+00:00"
            store.upsert_post(
                "p1",
                timestamp,
                post_url="https://www.linkedin.com/feed/update/p1",
                liked=True,
                liked_by_actor=True,
            )

            browser = FakeBrowser()
            browser.page_state = {
                "url": "https://www.linkedin.com/uas/login?session_redirect=detail",
                "title": "LinkedIn Login, Sign in | LinkedIn",
                "has_actor_selector": False,
                "logged_out": True,
            }
            report = RunReport(run_id="run-detail-login", started_at=timestamp, actor_verified=True)
            first = make_snapshot("p1")
            config = self.make_config(artifact_dir)
            config.comment_cap = 12
            config.repost_cap = 0
            config.max_passes = 0

            process_feed(first, store, report, browser, config)

            self.assertEqual(report.status, "stopped")
            self.assertEqual(report.stop_reason, "detail_page_logged_out")
            self.assertTrue(any(skip.get("reason") == "detail_page_logged_out" for skip in report.skips))
            store.close()

    def test_process_feed_tries_load_more_comments_when_thread_is_empty(self) -> None:
        with TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir)
            store = StateStore(artifact_dir / "state.sqlite3")
            timestamp = "2026-03-27T10:00:00+00:00"
            browser = FakeBrowser()
            browser.comment_load_more_result = True
            report = RunReport(run_id="run-comment-more", started_at=timestamp)
            first = make_snapshot("p1")
            config = self.make_config(artifact_dir)
            config.comment_cap = 12
            config.repost_cap = 0
            config.max_passes = 0
            expanded = make_snapshot("p1")
            loaded = FeedSnapshot(
                actor_name="Example Company",
                actor_verified=True,
                search_shape_ok=True,
                search_markers=["keyword:opportunities", "content-view", "latest-sort", "photo-filter", "org-filter"],
                challenge_signals=[],
                posts=[
                    PostSnapshot(
                        post_id="p1",
                        post_url=None,
                        text="Post p1",
                        sponsored=False,
                        already_liked=False,
                        already_reposted=False,
                        interactable=True,
                        like_selector="selector:p1",
                        repost_selector="selector:p1:repost",
                        comments_expanded=True,
                        comment_toggle_selector="card:0:comment-toggle",
                        reply_toggle_selectors=[],
                        comments=[
                            CommentSnapshot(
                                comment_id="comment-1",
                                parent_post_id="p1",
                                parent_comment_id=None,
                                text="Need to like",
                                liked=False,
                                like_selector="card:0:comment:0:like",
                            )
                        ],
                    )
                ],
            )

            with patch("linkedin.company_profile_engagement.runner.capture_current_snapshot", side_effect=[expanded, loaded]):
                process_feed(first, store, report, browser, config)

            self.assertEqual(report.comments_liked, 1)
            self.assertEqual(browser.comment_load_more_calls, [0])
            self.assertIn("card:0:comment:0:like", browser.clicks)
            store.close()

    def test_process_feed_rechecks_actor_after_comment_expand_false_negative(self) -> None:
        with TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir)
            store = StateStore(artifact_dir / "state.sqlite3")
            timestamp = "2026-03-28T10:00:00+00:00"
            browser = FakeBrowser()
            report = RunReport(run_id="run-actor-recheck", started_at=timestamp)
            config = self.make_config(artifact_dir)
            config.comment_cap = 12
            config.repost_cap = 0
            config.max_passes = 0
            first = FeedSnapshot(
                actor_name="Example Company",
                actor_verified=True,
                search_shape_ok=True,
                search_markers=["keyword:opportunities", "content-view", "latest-sort", "photo-filter", "org-filter"],
                challenge_signals=[],
                posts=[
                    PostSnapshot(
                        post_id="p1",
                        post_url=None,
                        text="Post p1",
                        sponsored=False,
                        already_liked=False,
                        already_reposted=False,
                        interactable=True,
                        like_selector="selector:p1",
                        repost_selector="selector:p1:repost",
                        comments_expanded=False,
                        comment_toggle_selector="card:0:comment-toggle",
                        reply_toggle_selectors=[],
                        comments=[],
                    )
                ],
            )
            bad_refresh = FeedSnapshot(
                actor_name=None,
                actor_verified=False,
                search_shape_ok=True,
                search_markers=["keyword:opportunities", "content-view", "latest-sort", "photo-filter", "org-filter"],
                challenge_signals=[],
                posts=[
                    PostSnapshot(
                        post_id="p1",
                        post_url=None,
                        text="Post p1",
                        sponsored=False,
                        already_liked=True,
                        already_reposted=False,
                        interactable=True,
                        like_selector="selector:p1",
                        repost_selector="selector:p1:repost",
                        comments_expanded=True,
                        comment_toggle_selector="card:0:comment-toggle",
                        reply_toggle_selectors=[],
                        comments=[],
                    )
                ],
            )
            recovered_refresh = FeedSnapshot(
                actor_name=None,
                actor_verified=False,
                search_shape_ok=True,
                search_markers=["keyword:opportunities", "content-view", "latest-sort", "photo-filter", "org-filter"],
                challenge_signals=[],
                posts=[
                    PostSnapshot(
                        post_id="p1",
                        post_url=None,
                        text="Post p1",
                        sponsored=False,
                        already_liked=True,
                        already_reposted=False,
                        interactable=True,
                        like_selector="selector:p1",
                        repost_selector="selector:p1:repost",
                        comments_expanded=True,
                        comment_toggle_selector="card:0:comment-toggle",
                        reply_toggle_selectors=[],
                        comments=[
                            CommentSnapshot(
                                comment_id="comment-1",
                                parent_post_id="p1",
                                parent_comment_id=None,
                                text="Need to like",
                                liked=False,
                                like_selector="card:0:comment:0:like",
                            )
                        ],
                    )
                ],
            )

            with patch("linkedin.company_profile_engagement.runner.capture_current_snapshot", side_effect=[bad_refresh, recovered_refresh]):
                process_feed(first, store, report, browser, config)

            self.assertEqual(report.status, "started")
            self.assertEqual(report.comments_liked, 1)
            self.assertTrue(
                any(event.get("type") == "actor_recheck_completed" and event.get("recovered") for event in report.events)
            )
            self.assertIn("card:0:comment:0:like", browser.clicks)
            store.close()


if __name__ == "__main__":
    unittest.main()
