from __future__ import annotations

import json
import random
import traceback
import uuid
from pathlib import Path

from automation_catalog import LINKEDIN_COMPANY_PROFILE_ENGAGEMENT, LINKEDIN_CORE_SURFACE, LINKEDIN_PLATFORM
from run_lock import RunLockError, acquire_run_lock

if __package__ in {None, ""}:
    import sys

    PACKAGE_ROOT = Path(__file__).resolve().parents[2]
    if str(PACKAGE_ROOT) not in sys.path:
        sys.path.insert(0, str(PACKAGE_ROOT))

    from automation_analytics import linkedin_company_profile_engagement_metrics, upsert_automation_run
    from linkedin.company_profile_engagement.browser_use_client import BrowserUseClient
    from linkedin.company_profile_engagement.config import RunnerConfig, parse_config
    from linkedin.company_profile_engagement.models import AgencyFeedSnapshot, AgencySnapshot, FeedSnapshot, PostSnapshot, RunReport, utc_now
    from linkedin.company_profile_engagement.parser import parse_browser_payload, parse_feed_html
    from linkedin.company_profile_engagement.state import StateStore
else:
    from automation_analytics import linkedin_company_profile_engagement_metrics, upsert_automation_run
    from .browser_use_client import BrowserUseClient
    from .config import RunnerConfig, parse_config
    from .models import AgencyFeedSnapshot, AgencySnapshot, FeedSnapshot, PostSnapshot, RunReport, utc_now
    from .parser import parse_browser_payload, parse_feed_html
    from .state import StateStore

MAX_STALLED_SCROLLS = 2
SCROLL_AMOUNT = 1400
MAX_STALLED_FOLLOW_SCROLLS = 2
FOLLOW_SCROLL_AMOUNT = 900


def add_event(report: RunReport, event_type: str, **fields: object) -> None:
    report.events.append(
        {
            "ts": utc_now().isoformat(),
            "type": event_type,
            **fields,
        }
    )


def build_browser_session_name(base_session_name: str, run_id: str) -> str:
    return f"{base_session_name}-{run_id[:8]}"


def main(argv: list[str] | None = None) -> int:
    config = parse_config(argv)
    config.artifact_dir.mkdir(parents=True, exist_ok=True)
    try:
        run_lock = acquire_run_lock(config.artifact_dir / ".run.lock")
    except RunLockError as exc:
        print(str(exc))
        return 0
    store = StateStore(config.db_path, database_url=config.database_url)
    run_id = uuid.uuid4().hex
    browser_session_name = build_browser_session_name(config.session_name, run_id)
    started_at = utc_now().isoformat()
    store.close_incomplete_runs()
    report = RunReport(run_id=run_id, started_at=started_at)
    store.start_run(run_id, started_at)
    add_event(report, "browser_session_allocated", session_name=browser_session_name)
    browser: BrowserUseClient | None = None

    try:
        browser = None if config.dry_run else BrowserUseClient(
            session_name=browser_session_name,
            chrome_profile=config.chrome_profile,
        )
        snapshot = load_snapshot(config, browser)
        if stop_for_invalid_snapshot(report, snapshot):
            return finalize(store, report, config.artifact_dir, search_url=config.search_url, analytics_database_url=config.analytics_database_url)

        process_feed(snapshot, store, report, browser, config)
        if report.status == "stopped":
            return finalize(store, report, config.artifact_dir, search_url=config.search_url, analytics_database_url=config.analytics_database_url)
        if browser is not None:
            process_agency_follows(store, report, browser, config)
        if report.status == "stopped":
            return finalize(store, report, config.artifact_dir, search_url=config.search_url, analytics_database_url=config.analytics_database_url)
        report.status = "ok"
        add_event(
            report,
            "run_completed",
            posts_scanned=report.posts_scanned,
            posts_liked=report.posts_liked,
            posts_reposted=report.posts_reposted,
            comments_liked=report.comments_liked,
            agencies_scanned=report.agencies_scanned,
            agencies_followed=report.agencies_followed,
        )
        return finalize(store, report, config.artifact_dir, search_url=config.search_url, analytics_database_url=config.analytics_database_url)
    except Exception as exc:
        report.status = "failed"
        report.stop_reason = type(exc).__name__
        report.skips.append({"reason": "exception", "message": str(exc)})
        add_event(report, "run_failed", error=type(exc).__name__, message=str(exc))
        if not config.dry_run:
            try:
                browser = browser or BrowserUseClient(
                    session_name=browser_session_name,
                    chrome_profile=config.chrome_profile,
                )
                screenshot_path = config.artifact_dir / f"{run_id}-failure.png"
                browser.screenshot(screenshot_path)
                report.screenshot_path = str(screenshot_path)
            except Exception:
                report.skips.append({"reason": "screenshot_failed", "trace": traceback.format_exc(limit=1)})
        return finalize(store, report, config.artifact_dir, search_url=config.search_url, analytics_database_url=config.analytics_database_url)
    finally:
        if browser is not None:
            browser.close()
        run_lock.release()


def load_snapshot(config: RunnerConfig, browser: BrowserUseClient | None) -> FeedSnapshot:
    if config.dry_run:
        assert config.fixture_path is not None
        return parse_feed_html(config.fixture_path.read_text(), config.actor_name)
    assert browser is not None
    last_snapshot: FeedSnapshot | None = None
    last_actor_selected = False
    for _ in range(3):
        browser.open(config.search_url)
        browser.sleep(1.2)
        actor_selected = browser.ensure_actor(config.actor_name)
        browser.sleep(0.8)
        snapshot = capture_current_snapshot(browser, config.actor_name)
        snapshot.actor_verified = actor_selected
        snapshot.actor_name = config.actor_name if actor_selected else snapshot.actor_name
        last_snapshot = snapshot
        last_actor_selected = actor_selected
        if snapshot.search_shape_ok and snapshot.posts:
            return snapshot
        browser.sleep(1.2)
    assert last_snapshot is not None
    last_snapshot.actor_verified = last_actor_selected
    last_snapshot.actor_name = config.actor_name if last_actor_selected else last_snapshot.actor_name
    return last_snapshot


def capture_current_snapshot(browser: BrowserUseClient, actor_name: str) -> FeedSnapshot:
    payload = browser.collect_payload()
    html = browser.get_html()
    return parse_browser_payload(payload, actor_name, html)


def reconfirm_feed_actor(
    browser: BrowserUseClient,
    config: RunnerConfig,
    report: RunReport,
    snapshot: FeedSnapshot,
    *,
    context: str,
) -> FeedSnapshot:
    if snapshot.actor_verified:
        return snapshot
    add_event(report, "actor_recheck_attempt", context=context)
    actor_selected = browser.ensure_actor(config.actor_name)
    browser.sleep(0.8)
    if not actor_selected:
        add_event(report, "actor_recheck_completed", context=context, recovered=False)
        return snapshot
    refreshed = capture_current_snapshot(browser, config.actor_name)
    refreshed.actor_verified = True
    refreshed.actor_name = config.actor_name
    add_event(report, "actor_recheck_completed", context=context, recovered=True)
    return refreshed


def capture_agency_snapshot(browser: BrowserUseClient) -> AgencyFeedSnapshot:
    raw = browser.collect_follow_payload()
    payload = json.loads(raw)
    agencies = [
        AgencySnapshot(
            company_id=str(item["company_id"]),
            company_url=str(item["company_url"]),
            name=str(item["name"]),
            subtitle=item.get("subtitle"),
            followers_text=item.get("followers_text"),
            already_following=bool(item.get("already_following")),
            follow_selector=item.get("follow_selector"),
        )
        for item in payload.get("agencies", [])
    ]
    following_count = payload.get("following_count")
    return AgencyFeedSnapshot(
        page_shape_ok=bool(payload.get("page_shape_ok")),
        challenge_signals=list(payload.get("challenge_signals", [])),
        following_count=int(following_count) if following_count is not None else None,
        active_tab=payload.get("active_tab"),
        agencies=agencies,
    )


def stop_for_invalid_snapshot(report: RunReport, snapshot: FeedSnapshot) -> bool:
    report.actor_verified = snapshot.actor_verified
    report.search_shape_ok = snapshot.search_shape_ok
    if snapshot.challenge_signals:
        report.status = "stopped"
        report.stop_reason = "anti_automation_challenge"
        report.skips.append({"reason": "challenge_signals", "signals": snapshot.challenge_signals})
        add_event(report, "run_stopped", reason="anti_automation_challenge", signals=snapshot.challenge_signals)
        return True
    if not snapshot.search_shape_ok:
        report.status = "stopped"
        report.stop_reason = "search_shape_changed"
        report.skips.append({"reason": "search_shape_changed", "markers": snapshot.search_markers})
        add_event(report, "run_stopped", reason="search_shape_changed", markers=snapshot.search_markers)
        return True
    if not snapshot.actor_verified:
        report.status = "stopped"
        report.stop_reason = "actor_mismatch"
        report.skips.append({"reason": "actor_mismatch", "actor": snapshot.actor_name})
        add_event(report, "run_stopped", reason="actor_mismatch", actor=snapshot.actor_name)
        return True
    return False


def stop_for_invalid_detail_snapshot(report: RunReport, snapshot: FeedSnapshot) -> bool:
    if snapshot.challenge_signals:
        report.status = "stopped"
        report.stop_reason = "anti_automation_challenge"
        report.skips.append({"reason": "challenge_signals", "signals": snapshot.challenge_signals})
        add_event(report, "run_stopped", reason="anti_automation_challenge", signals=snapshot.challenge_signals)
        return True
    return False


def stop_for_invalid_agency_snapshot(report: RunReport, snapshot: AgencyFeedSnapshot) -> bool:
    if snapshot.challenge_signals:
        report.status = "stopped"
        report.stop_reason = "anti_automation_challenge"
        report.skips.append({"reason": "agency_follow_challenge_signals", "signals": snapshot.challenge_signals})
        add_event(report, "run_stopped", reason="anti_automation_challenge", signals=snapshot.challenge_signals)
        return True
    if not snapshot.page_shape_ok:
        report.status = "stopped"
        report.stop_reason = "agency_follow_page_shape_changed"
        report.skips.append({"reason": "agency_follow_page_shape_changed", "active_tab": snapshot.active_tab})
        add_event(report, "run_stopped", reason="agency_follow_page_shape_changed", active_tab=snapshot.active_tab)
        return True
    return False


def process_feed(
    snapshot: FeedSnapshot,
    store: StateStore,
    report: RunReport,
    browser: BrowserUseClient | None,
    config: RunnerConfig,
) -> None:
    seen_post_ids: set[str] = set()
    detail_candidates: dict[str, PostSnapshot] = {}
    posts_remaining = config.post_cap
    reposts_remaining = config.repost_cap
    comments_remaining = config.comment_cap
    stalled_scrolls = 0
    pass_index = 0

    while True:
        fresh_posts = [post for post in snapshot.posts if post.post_id not in seen_post_ids]
        seen_post_ids.update(post.post_id for post in fresh_posts)
        report.posts_scanned = len(seen_post_ids)
        add_event(
            report,
            "snapshot_loaded",
            pass_index=pass_index,
            actor_verified=snapshot.actor_verified,
            search_shape_ok=snapshot.search_shape_ok,
            markers=snapshot.search_markers,
            posts=len(snapshot.posts),
            new_posts=len(fresh_posts),
        )
        store.record_snapshot(report.run_id, pass_index, snapshot)

        if fresh_posts:
            stalled_scrolls = 0
        else:
            stalled_scrolls += 1
            add_event(report, "snapshot_stalled", pass_index=pass_index, reason="no_new_posts")

        posts_remaining, reposts_remaining, comments_remaining = process_visible_posts(
            fresh_posts,
            store,
            report,
            browser,
            config,
            detail_candidates,
            posts_remaining,
            reposts_remaining,
            comments_remaining,
        )
        if report.status == "stopped":
            return
        if browser is None or (posts_remaining <= 0 and reposts_remaining <= 0) or pass_index >= config.max_passes or stalled_scrolls >= MAX_STALLED_SCROLLS:
            if browser is not None and comments_remaining > 0 and detail_candidates:
                process_detail_comment_candidates(
                    list(detail_candidates.values()),
                    store,
                    report,
                    browser,
                    config,
                    comments_remaining,
                    pass_index + 1,
                )
            if browser is not None and pass_index >= config.max_passes:
                add_event(report, "scan_completed", reason="scroll_limit_reached", passes=pass_index + 1)
            if browser is not None and stalled_scrolls >= MAX_STALLED_SCROLLS:
                add_event(report, "scan_completed", reason="no_new_posts_after_scroll", passes=pass_index + 1)
            return

        used_load_more = browser.load_more_results()
        if used_load_more:
            add_event(report, "results_advanced", mode="load_more", pass_index=pass_index)
            jitter_sleep(browser, 1.2, 2.0)
        else:
            browser.scroll_results(SCROLL_AMOUNT)
            add_event(report, "results_advanced", mode="scroll", pass_index=pass_index, amount=SCROLL_AMOUNT)
            jitter_sleep(browser, 0.9, 1.6)
        snapshot = capture_current_snapshot(browser, config.actor_name)
        snapshot = reconfirm_feed_actor(browser, config, report, snapshot, context="search_pagination")
        if stop_for_invalid_snapshot(report, snapshot):
            return
        pass_index += 1


def process_visible_posts(
    posts: list[PostSnapshot],
    store: StateStore,
    report: RunReport,
    browser: BrowserUseClient | None,
    config: RunnerConfig,
    detail_candidates: dict[str, PostSnapshot],
    posts_remaining: int,
    reposts_remaining: int,
    comments_remaining: int,
) -> tuple[int, int, int]:
    now = utc_now().isoformat()
    for position_index, post in enumerate(posts):
        add_event(report, "post_seen", post_id=post.post_id, sponsored=post.sponsored, already_liked=post.already_liked)
        if post.sponsored:
            report.skips.append({"post_id": post.post_id, "reason": "sponsored"})
            add_event(report, "post_skipped", post_id=post.post_id, reason="sponsored")
            continue
        if not post.interactable:
            report.skips.append({"post_id": post.post_id, "reason": "not_interactable"})
            add_event(report, "post_skipped", post_id=post.post_id, reason="not_interactable")
            continue

        post_processed = store.post_processed(post.post_id)
        post_reposted = store.post_reposted(post.post_id)
        should_review_detail_comments = (
            browser is not None
            and comments_remaining > 0
            and bool(post.post_url)
            and (not post.comments_expanded or not post.comments or any(not store.comment_processed(comment.comment_id) for comment in post.comments))
        )
        if should_review_detail_comments:
            detail_candidates.setdefault(post.post_id, post)

        if post_processed and not should_review_detail_comments and all(store.comment_processed(comment.comment_id) for comment in post.comments):
            report.skips.append({"post_id": post.post_id, "reason": "already_processed"})
            add_event(report, "post_skipped", post_id=post.post_id, reason="already_processed")
            continue

        if not post.already_liked and not post_processed:
            if posts_remaining <= 0:
                report.skips.append({"post_id": post.post_id, "reason": "post_cap_reached"})
                add_event(report, "post_skipped", post_id=post.post_id, reason="post_cap_reached")
                store.upsert_post(
                    post.post_id,
                    now,
                    post_url=post.post_url,
                    liked=post.already_liked,
                    liked_by_actor=post_processed,
                    reposted=post.already_reposted,
                    reposted_by_actor=post_reposted,
                )
            elif browser is not None and post.like_selector:
                add_event(report, "post_like_attempt", post_id=post.post_id, selector=post.like_selector)
                browser.click_selector(post.like_selector)
                jitter_sleep(browser, 0.8, 1.6)
                report.posts_liked += 1
                store.upsert_post(
                    post.post_id,
                    now,
                    post_url=post.post_url,
                    liked=True,
                    liked_by_actor=True,
                    reposted=post.already_reposted,
                    reposted_by_actor=post_reposted,
                )
                posts_remaining -= 1
                add_event(report, "post_liked", post_id=post.post_id)
            else:
                report.skips.append({"post_id": post.post_id, "reason": "missing_like_selector"})
                add_event(report, "post_skipped", post_id=post.post_id, reason="missing_like_selector")
                store.upsert_post(
                    post.post_id,
                    now,
                    post_url=post.post_url,
                    liked=post.already_liked,
                    liked_by_actor=post_processed,
                    reposted=post.already_reposted,
                    reposted_by_actor=post_reposted,
                )
        else:
            store.upsert_post(
                post.post_id,
                now,
                post_url=post.post_url,
                liked=post.already_liked,
                liked_by_actor=post.already_liked or post_processed,
                reposted=post.already_reposted,
                reposted_by_actor=post.already_reposted or post_reposted,
            )
            add_event(report, "post_retained", post_id=post.post_id, already_liked=post.already_liked, processed=post_processed)

        if reposts_remaining > 0 and not post.already_reposted and not post_reposted:
            if browser is not None and post.repost_selector:
                add_event(report, "post_repost_attempt", post_id=post.post_id, selector=post.repost_selector)
                try:
                    browser.click_selector(post.repost_selector)
                    jitter_sleep(browser, 0.8, 1.6)
                    report.posts_reposted += 1
                    reposts_remaining -= 1
                    store.upsert_post(
                        post.post_id,
                        now,
                        post_url=post.post_url,
                        liked=post.already_liked or post_processed,
                        liked_by_actor=post.already_liked or post_processed,
                        reposted=True,
                        reposted_by_actor=True,
                    )
                    add_event(report, "post_reposted", post_id=post.post_id)
                except Exception as exc:
                    report.skips.append({"post_id": post.post_id, "reason": "repost_failed", "message": str(exc)})
                    add_event(report, "post_skipped", post_id=post.post_id, reason="repost_failed", message=str(exc))
            else:
                report.skips.append({"post_id": post.post_id, "reason": "missing_repost_selector"})
                add_event(report, "post_skipped", post_id=post.post_id, reason="missing_repost_selector")

        if comments_remaining <= 0:
            continue

        if not post.comments_expanded and post.comment_toggle_selector and browser is not None:
            add_event(report, "comment_thread_expand_attempt", post_id=post.post_id, selector=post.comment_toggle_selector)
            browser.click_selector(post.comment_toggle_selector)
            jitter_sleep(browser, 0.7, 1.4)
            refreshed = capture_current_snapshot(browser, config.actor_name)
            refreshed = reconfirm_feed_actor(browser, config, report, refreshed, context="comment_thread_expand")
            if stop_for_invalid_snapshot(report, refreshed):
                return posts_remaining, reposts_remaining, comments_remaining
            refreshed_post = next((item for item in refreshed.posts if item.post_id == post.post_id), None)
            if refreshed_post is not None:
                post = refreshed_post
                add_event(report, "comment_thread_expanded", post_id=post.post_id, comments=len(post.comments))

        if browser is not None and not post.comments and browser.load_more_comments(position_index):
            add_event(report, "comment_load_more_attempt", post_id=post.post_id, position_index=position_index)
            jitter_sleep(browser, 0.7, 1.4)
            refreshed = capture_current_snapshot(browser, config.actor_name)
            refreshed = reconfirm_feed_actor(browser, config, report, refreshed, context="comment_load_more")
            if stop_for_invalid_snapshot(report, refreshed):
                return posts_remaining, reposts_remaining, comments_remaining
            refreshed_post = next((item for item in refreshed.posts if item.post_id == post.post_id), None)
            if refreshed_post is not None:
                post = refreshed_post
                add_event(report, "comment_load_more_completed", post_id=post.post_id, comments=len(post.comments))

        for reply_selector in post.reply_toggle_selectors:
            if browser is None:
                break
            browser.click_selector(reply_selector)
            jitter_sleep(browser, 0.3, 0.8)

        for comment in post.comments:
            add_event(report, "comment_seen", post_id=post.post_id, comment_id=comment.comment_id, liked=comment.liked)
            if comments_remaining <= 0:
                report.skips.append({"post_id": post.post_id, "reason": "comment_cap_reached"})
                add_event(report, "comment_skipped", post_id=post.post_id, reason="comment_cap_reached")
                break
            if store.comment_processed(comment.comment_id):
                add_event(report, "comment_skipped", post_id=post.post_id, comment_id=comment.comment_id, reason="already_processed")
                continue
            if comment.liked:
                store.upsert_comment(comment.comment_id, post.post_id, comment.parent_comment_id, now, liked=True)
                add_event(report, "comment_retained", post_id=post.post_id, comment_id=comment.comment_id, reason="already_liked")
                continue
            if browser is not None and comment.like_selector:
                add_event(report, "comment_like_attempt", post_id=post.post_id, comment_id=comment.comment_id, selector=comment.like_selector)
                browser.click_selector(comment.like_selector)
                jitter_sleep(browser, 0.5, 1.2)
                report.comments_liked += 1
                comments_remaining -= 1
                store.upsert_comment(comment.comment_id, post.post_id, comment.parent_comment_id, now, liked=True)
                add_event(report, "comment_liked", post_id=post.post_id, comment_id=comment.comment_id)
            else:
                report.skips.append(
                    {"post_id": post.post_id, "comment_id": comment.comment_id, "reason": "missing_like_selector"}
                )
                add_event(
                    report,
                    "comment_skipped",
                    post_id=post.post_id,
                    comment_id=comment.comment_id,
                    reason="missing_like_selector",
                )
    return posts_remaining, reposts_remaining, comments_remaining


def process_detail_comment_candidates(
    posts: list[PostSnapshot],
    store: StateStore,
    report: RunReport,
    browser: BrowserUseClient,
    config: RunnerConfig,
    comments_remaining: int,
    pass_index_start: int,
) -> None:
    for offset, candidate in enumerate(posts):
        if comments_remaining <= 0 or not candidate.post_url:
            break
        add_event(report, "detail_page_open", post_id=candidate.post_id, post_url=candidate.post_url)
        browser.open(candidate.post_url)
        browser.sleep(1.2)
        page_state = browser.get_page_state()
        if page_state["logged_out"]:
            report.status = "stopped"
            report.stop_reason = "detail_page_logged_out"
            report.skips.append(
                {
                    "post_id": candidate.post_id,
                    "post_url": candidate.post_url,
                    "reason": "detail_page_logged_out",
                    "url": page_state["url"],
                    "title": page_state["title"],
                }
            )
            add_event(
                report,
                "run_stopped",
                reason="detail_page_logged_out",
                post_id=candidate.post_id,
                post_url=candidate.post_url,
                url=page_state["url"],
                title=page_state["title"],
            )
            return

        actor_selected = False
        if page_state["has_actor_selector"]:
            actor_selected = browser.ensure_actor(config.actor_name)
            browser.sleep(0.8)
        detail_snapshot = capture_current_snapshot(browser, config.actor_name)
        inherited_actor = report.actor_verified and not page_state["has_actor_selector"]
        detail_snapshot.actor_verified = actor_selected or inherited_actor
        detail_snapshot.actor_name = config.actor_name if detail_snapshot.actor_verified else detail_snapshot.actor_name
        store.record_snapshot(report.run_id, pass_index_start + offset, detail_snapshot)
        if stop_for_invalid_detail_snapshot(report, detail_snapshot):
            return
        if not detail_snapshot.actor_verified:
            report.skips.append(
                {
                    "post_id": candidate.post_id,
                    "post_url": candidate.post_url,
                    "reason": "detail_actor_mismatch",
                    "actor": detail_snapshot.actor_name,
                }
            )
            add_event(
                report,
                "detail_page_skipped",
                post_id=candidate.post_id,
                post_url=candidate.post_url,
                reason="actor_mismatch",
                actor=detail_snapshot.actor_name,
            )
            continue
        if inherited_actor:
            add_event(
                report,
                "detail_actor_inherited",
                post_id=candidate.post_id,
                post_url=candidate.post_url,
                reason="no_actor_selector_on_detail_page",
            )
        detail_post = next((item for item in detail_snapshot.posts if item.post_id == candidate.post_id), None)
        if detail_post is None and detail_snapshot.posts:
            detail_post = detail_snapshot.posts[0]
        if detail_post is None:
            add_event(report, "detail_page_missing_post", post_id=candidate.post_id, post_url=candidate.post_url)
            continue
        _, _, comments_remaining = process_visible_posts(
            [detail_post],
            store,
            report,
            browser,
            config,
            {},
            0,
            0,
            comments_remaining,
        )
        if report.status == "stopped":
            return


def process_agency_follows(
    store: StateStore,
    report: RunReport,
    browser: BrowserUseClient,
    config: RunnerConfig,
) -> None:
    if config.follow_cap <= 0 or not config.follow_admin_url:
        return

    browser.open(config.follow_admin_url)
    browser.sleep(1.2)
    snapshot = capture_agency_snapshot(browser)
    if stop_for_invalid_agency_snapshot(report, snapshot):
        return
    if (snapshot.active_tab or "").lower().startswith("following") and browser.select_follow_tab("Recommended"):
        jitter_sleep(browser, 0.6, 1.2)
        snapshot = capture_agency_snapshot(browser)
        if stop_for_invalid_agency_snapshot(report, snapshot):
            return

    seen_company_ids: set[str] = set()
    follows_remaining = config.follow_cap
    stalled_scrolls = 0
    pass_index = 0

    while True:
        fresh_agencies = [agency for agency in snapshot.agencies if agency.company_id not in seen_company_ids]
        seen_company_ids.update(agency.company_id for agency in fresh_agencies)
        report.agencies_scanned = len(seen_company_ids)
        add_event(
            report,
            "agency_snapshot_loaded",
            pass_index=pass_index,
            active_tab=snapshot.active_tab,
            following_count=snapshot.following_count,
            agencies=len(snapshot.agencies),
            new_agencies=len(fresh_agencies),
        )
        store.record_agency_snapshot(report.run_id, pass_index, snapshot)

        if fresh_agencies:
            stalled_scrolls = 0
        else:
            stalled_scrolls += 1
            add_event(report, "agency_snapshot_stalled", pass_index=pass_index, reason="no_new_agencies")

        follows_remaining, refresh_requested = process_visible_agencies(
            fresh_agencies,
            store,
            report,
            browser,
            follows_remaining,
            pass_index,
            snapshot.following_count,
        )
        if report.status == "stopped":
            return
        if refresh_requested:
            if follows_remaining > 0:
                browser.select_follow_tab("Recommended")
                jitter_sleep(browser, 0.6, 1.2)
            snapshot = capture_agency_snapshot(browser)
            if stop_for_invalid_agency_snapshot(report, snapshot):
                return
            pass_index += 1
            continue
        if follows_remaining <= 0 or pass_index >= config.max_passes or stalled_scrolls >= MAX_STALLED_FOLLOW_SCROLLS:
            add_event(
                report,
                "agency_follow_scan_completed",
                reason="follow_cap_reached" if follows_remaining <= 0 else "no_new_agencies_after_scroll" if stalled_scrolls >= MAX_STALLED_FOLLOW_SCROLLS else "scroll_limit_reached",
                passes=pass_index + 1,
            )
            return

        if not browser.scroll_follow_modal(FOLLOW_SCROLL_AMOUNT):
            stalled_scrolls += 1
            add_event(report, "agency_results_advanced", mode="scroll", pass_index=pass_index, moved=False)
        else:
            add_event(report, "agency_results_advanced", mode="scroll", pass_index=pass_index, moved=True, amount=FOLLOW_SCROLL_AMOUNT)
            jitter_sleep(browser, 0.8, 1.4)

        snapshot = capture_agency_snapshot(browser)
        if stop_for_invalid_agency_snapshot(report, snapshot):
            return
        pass_index += 1


def process_visible_agencies(
    agencies: list[AgencySnapshot],
    store: StateStore,
    report: RunReport,
    browser: BrowserUseClient,
    follows_remaining: int,
    pass_index: int,
    following_count_before: int | None,
) -> tuple[int, bool]:
    now = utc_now().isoformat()
    for position_index, agency in enumerate(agencies):
        followed_in_store = store.agency_followed(agency.company_id)
        add_event(
            report,
            "agency_seen",
            company_id=agency.company_id,
            name=agency.name,
            already_following=agency.already_following,
        )
        if agency.already_following or followed_in_store:
            store.upsert_agency(
                agency.company_id,
                now,
                company_url=agency.company_url,
                name=agency.name,
                subtitle=agency.subtitle,
                followers_text=agency.followers_text,
                followed=True,
                followed_at=now if agency.already_following else None,
            )
            store.record_agency_observation(report.run_id, pass_index, position_index, agency, action_taken="already_following")
            report.skips.append({"company_id": agency.company_id, "reason": "already_following"})
            add_event(report, "agency_skipped", company_id=agency.company_id, reason="already_following")
            continue
        if follows_remaining <= 0:
            store.upsert_agency(
                agency.company_id,
                now,
                company_url=agency.company_url,
                name=agency.name,
                subtitle=agency.subtitle,
                followers_text=agency.followers_text,
                followed=False,
            )
            store.record_agency_observation(report.run_id, pass_index, position_index, agency, action_taken="follow_cap_reached")
            report.skips.append({"company_id": agency.company_id, "reason": "follow_cap_reached"})
            add_event(report, "agency_skipped", company_id=agency.company_id, reason="follow_cap_reached")
            continue
        if not agency.follow_selector:
            store.upsert_agency(
                agency.company_id,
                now,
                company_url=agency.company_url,
                name=agency.name,
                subtitle=agency.subtitle,
                followers_text=agency.followers_text,
                followed=False,
            )
            store.record_agency_observation(report.run_id, pass_index, position_index, agency, action_taken="missing_follow_selector")
            report.skips.append({"company_id": agency.company_id, "reason": "missing_follow_selector"})
            add_event(report, "agency_skipped", company_id=agency.company_id, reason="missing_follow_selector")
            continue

        add_event(report, "agency_follow_attempt", company_id=agency.company_id, selector=agency.follow_selector)
        try:
            browser.click_selector(agency.follow_selector)
            jitter_sleep(browser, 0.8, 1.6)
            refreshed = capture_agency_snapshot(browser)
            if stop_for_invalid_agency_snapshot(report, refreshed):
                return follows_remaining, False
            refreshed_agency = next((item for item in refreshed.agencies if item.company_id == agency.company_id), None)
            count_increased = (
                following_count_before is not None
                and refreshed.following_count is not None
                and refreshed.following_count > following_count_before
            )
            confirmed = (
                (refreshed_agency is not None and (refreshed_agency.already_following or refreshed_agency.follow_selector is None))
                or count_increased
            )
            if confirmed:
                report.agencies_followed += 1
                follows_remaining -= 1
                store.upsert_agency(
                    agency.company_id,
                    now,
                    company_url=agency.company_url,
                    name=agency.name,
                    subtitle=agency.subtitle,
                    followers_text=agency.followers_text,
                    followed=True,
                    followed_at=now,
                )
                store.record_agency_observation(report.run_id, pass_index, position_index, agency, action_taken="followed")
                add_event(report, "agency_followed", company_id=agency.company_id, name=agency.name)
            else:
                store.upsert_agency(
                    agency.company_id,
                    now,
                    company_url=agency.company_url,
                    name=agency.name,
                    subtitle=agency.subtitle,
                    followers_text=agency.followers_text,
                    followed=False,
                )
                store.record_agency_observation(report.run_id, pass_index, position_index, agency, action_taken="follow_unconfirmed")
                report.skips.append({"company_id": agency.company_id, "reason": "follow_unconfirmed"})
                add_event(report, "agency_skipped", company_id=agency.company_id, reason="follow_unconfirmed")
            return follows_remaining, True
        except Exception as exc:
            store.upsert_agency(
                agency.company_id,
                now,
                company_url=agency.company_url,
                name=agency.name,
                subtitle=agency.subtitle,
                followers_text=agency.followers_text,
                followed=False,
            )
            store.record_agency_observation(report.run_id, pass_index, position_index, agency, action_taken="follow_failed")
            report.skips.append({"company_id": agency.company_id, "reason": "follow_failed", "message": str(exc)})
            add_event(report, "agency_skipped", company_id=agency.company_id, reason="follow_failed", message=str(exc))
            return follows_remaining, True
    return follows_remaining, False


def jitter_sleep(browser: BrowserUseClient, minimum: float, maximum: float) -> None:
    browser.sleep(random.uniform(minimum, maximum))


def finalize(
    store: StateStore,
    report: RunReport,
    artifact_dir: Path | None = None,
    *,
    search_url: str = "about:blank",
    analytics_database_url: str | None = None,
) -> int:
    report.finished_at = utc_now().isoformat()
    store.finish_run(
        report.run_id,
        finished_at=report.finished_at,
        status=report.status,
        actor_verified=report.actor_verified,
        posts_scanned=report.posts_scanned,
        posts_liked=report.posts_liked,
        posts_reposted=report.posts_reposted,
        comments_liked=report.comments_liked,
        agencies_scanned=report.agencies_scanned,
        agencies_followed=report.agencies_followed,
        stop_reason=report.stop_reason,
    )
    artifact_dir = artifact_dir or Path("artifacts/linkedin-company-profile-engagement")
    artifact_dir.mkdir(parents=True, exist_ok=True)
    report_path = artifact_dir / f"{report.run_id}.json"
    report_path.write_text(json.dumps(report.to_dict(), indent=2))
    store.record_run_report(report.run_id, search_url, str(report_path), report)
    upsert_automation_run(
        database_url=analytics_database_url,
        automation_name=LINKEDIN_COMPANY_PROFILE_ENGAGEMENT,
        platform=LINKEDIN_PLATFORM,
        surface=LINKEDIN_CORE_SURFACE,
        search_url=search_url,
        artifact_path=str(report_path),
        report=report,
        metrics=linkedin_company_profile_engagement_metrics(report),
    )
    store.close()
    return 0 if report.status in {"ok", "stopped"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
