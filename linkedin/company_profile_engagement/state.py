from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from automation_analytics import normalize_report_payload


SQLITE_SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
  run_id TEXT PRIMARY KEY,
  started_at TEXT NOT NULL,
  finished_at TEXT,
  status TEXT NOT NULL,
  actor_verified INTEGER NOT NULL DEFAULT 0,
  posts_scanned INTEGER NOT NULL DEFAULT 0,
  posts_liked INTEGER NOT NULL DEFAULT 0,
  posts_reposted INTEGER NOT NULL DEFAULT 0,
  companies_scanned INTEGER NOT NULL DEFAULT 0,
  companies_followed INTEGER NOT NULL DEFAULT 0,
  comments_liked INTEGER NOT NULL DEFAULT 0,
  agencies_scanned INTEGER NOT NULL DEFAULT 0,
  agencies_followed INTEGER NOT NULL DEFAULT 0,
  stop_reason TEXT
);

CREATE TABLE IF NOT EXISTS posts (
  post_id TEXT PRIMARY KEY,
  post_url TEXT,
  first_seen_at TEXT NOT NULL,
  last_checked_at TEXT NOT NULL,
  liked INTEGER NOT NULL DEFAULT 0,
  liked_by_actor INTEGER NOT NULL DEFAULT 0,
  reposted INTEGER NOT NULL DEFAULT 0,
  reposted_by_actor INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS comments (
  comment_id TEXT PRIMARY KEY,
  post_id TEXT NOT NULL,
  parent_comment_id TEXT,
  first_seen_at TEXT NOT NULL,
  liked INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS run_reports (
  run_id TEXT PRIMARY KEY,
  search_url TEXT NOT NULL,
  artifact_path TEXT NOT NULL,
  screenshot_path TEXT,
  report_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS feed_snapshots (
  run_id TEXT NOT NULL,
  pass_index INTEGER NOT NULL,
  actor_name TEXT,
  actor_verified INTEGER NOT NULL DEFAULT 0,
  search_shape_ok INTEGER NOT NULL DEFAULT 0,
  search_markers_json TEXT NOT NULL,
  challenge_signals_json TEXT NOT NULL,
  posts_count INTEGER NOT NULL DEFAULT 0,
  snapshot_json TEXT NOT NULL,
  PRIMARY KEY (run_id, pass_index)
);

CREATE TABLE IF NOT EXISTS post_observations (
  run_id TEXT NOT NULL,
  pass_index INTEGER NOT NULL,
  position_index INTEGER NOT NULL,
  post_id TEXT NOT NULL,
  post_url TEXT,
  text TEXT NOT NULL,
  sponsored INTEGER NOT NULL DEFAULT 0,
  already_liked INTEGER NOT NULL DEFAULT 0,
  already_reposted INTEGER NOT NULL DEFAULT 0,
  interactable INTEGER NOT NULL DEFAULT 1,
  like_selector TEXT,
  repost_selector TEXT,
  comments_expanded INTEGER NOT NULL DEFAULT 0,
  comment_toggle_selector TEXT,
  reply_toggle_selectors_json TEXT NOT NULL,
  comments_count INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (run_id, pass_index, post_id)
);

CREATE TABLE IF NOT EXISTS comment_observations (
  run_id TEXT NOT NULL,
  pass_index INTEGER NOT NULL,
  post_id TEXT NOT NULL,
  position_index INTEGER NOT NULL,
  comment_id TEXT NOT NULL,
  parent_comment_id TEXT,
  text TEXT NOT NULL,
  liked INTEGER NOT NULL DEFAULT 0,
  like_selector TEXT,
  PRIMARY KEY (run_id, pass_index, comment_id)
);

CREATE TABLE IF NOT EXISTS agencies (
  company_id TEXT PRIMARY KEY,
  company_url TEXT NOT NULL,
  name TEXT NOT NULL,
  subtitle TEXT,
  followers_text TEXT,
  first_seen_at TEXT NOT NULL,
  last_seen_at TEXT NOT NULL,
  followed INTEGER NOT NULL DEFAULT 0,
  followed_at TEXT
);

CREATE TABLE IF NOT EXISTS agency_snapshots (
  run_id TEXT NOT NULL,
  pass_index INTEGER NOT NULL,
  page_shape_ok INTEGER NOT NULL DEFAULT 0,
  following_count INTEGER,
  active_tab TEXT,
  challenge_signals_json TEXT NOT NULL,
  agencies_count INTEGER NOT NULL DEFAULT 0,
  snapshot_json TEXT NOT NULL,
  PRIMARY KEY (run_id, pass_index)
);

CREATE TABLE IF NOT EXISTS agency_observations (
  run_id TEXT NOT NULL,
  pass_index INTEGER NOT NULL,
  position_index INTEGER NOT NULL,
  company_id TEXT NOT NULL,
  company_url TEXT NOT NULL,
  name TEXT NOT NULL,
  subtitle TEXT,
  followers_text TEXT,
  already_following INTEGER NOT NULL DEFAULT 0,
  follow_selector TEXT,
  action_taken TEXT,
  PRIMARY KEY (run_id, pass_index, company_id)
);
"""


POSTGRES_SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
  run_id TEXT PRIMARY KEY,
  started_at TEXT NOT NULL,
  finished_at TEXT,
  status TEXT NOT NULL,
  actor_verified BOOLEAN NOT NULL DEFAULT FALSE,
  posts_scanned INTEGER NOT NULL DEFAULT 0,
  posts_liked INTEGER NOT NULL DEFAULT 0,
  posts_reposted INTEGER NOT NULL DEFAULT 0,
  companies_scanned INTEGER NOT NULL DEFAULT 0,
  companies_followed INTEGER NOT NULL DEFAULT 0,
  comments_liked INTEGER NOT NULL DEFAULT 0,
  agencies_scanned INTEGER NOT NULL DEFAULT 0,
  agencies_followed INTEGER NOT NULL DEFAULT 0,
  stop_reason TEXT
);

CREATE TABLE IF NOT EXISTS posts (
  post_id TEXT PRIMARY KEY,
  post_url TEXT,
  first_seen_at TEXT NOT NULL,
  last_checked_at TEXT NOT NULL,
  liked BOOLEAN NOT NULL DEFAULT FALSE,
  liked_by_actor BOOLEAN NOT NULL DEFAULT FALSE,
  reposted BOOLEAN NOT NULL DEFAULT FALSE,
  reposted_by_actor BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE TABLE IF NOT EXISTS comments (
  comment_id TEXT PRIMARY KEY,
  post_id TEXT NOT NULL,
  parent_comment_id TEXT,
  first_seen_at TEXT NOT NULL,
  liked BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE TABLE IF NOT EXISTS run_reports (
  run_id TEXT PRIMARY KEY,
  search_url TEXT NOT NULL,
  artifact_path TEXT NOT NULL,
  screenshot_path TEXT,
  report_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS feed_snapshots (
  run_id TEXT NOT NULL,
  pass_index INTEGER NOT NULL,
  actor_name TEXT,
  actor_verified BOOLEAN NOT NULL DEFAULT FALSE,
  search_shape_ok BOOLEAN NOT NULL DEFAULT FALSE,
  search_markers_json TEXT NOT NULL,
  challenge_signals_json TEXT NOT NULL,
  posts_count INTEGER NOT NULL DEFAULT 0,
  snapshot_json TEXT NOT NULL,
  PRIMARY KEY (run_id, pass_index)
);

CREATE TABLE IF NOT EXISTS post_observations (
  run_id TEXT NOT NULL,
  pass_index INTEGER NOT NULL,
  position_index INTEGER NOT NULL,
  post_id TEXT NOT NULL,
  post_url TEXT,
  text TEXT NOT NULL,
  sponsored BOOLEAN NOT NULL DEFAULT FALSE,
  already_liked BOOLEAN NOT NULL DEFAULT FALSE,
  already_reposted BOOLEAN NOT NULL DEFAULT FALSE,
  interactable BOOLEAN NOT NULL DEFAULT TRUE,
  like_selector TEXT,
  repost_selector TEXT,
  comments_expanded BOOLEAN NOT NULL DEFAULT FALSE,
  comment_toggle_selector TEXT,
  reply_toggle_selectors_json TEXT NOT NULL,
  comments_count INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (run_id, pass_index, post_id)
);

CREATE TABLE IF NOT EXISTS comment_observations (
  run_id TEXT NOT NULL,
  pass_index INTEGER NOT NULL,
  post_id TEXT NOT NULL,
  position_index INTEGER NOT NULL,
  comment_id TEXT NOT NULL,
  parent_comment_id TEXT,
  text TEXT NOT NULL,
  liked BOOLEAN NOT NULL DEFAULT FALSE,
  like_selector TEXT,
  PRIMARY KEY (run_id, pass_index, comment_id)
);

CREATE TABLE IF NOT EXISTS agencies (
  company_id TEXT PRIMARY KEY,
  company_url TEXT NOT NULL,
  name TEXT NOT NULL,
  subtitle TEXT,
  followers_text TEXT,
  first_seen_at TEXT NOT NULL,
  last_seen_at TEXT NOT NULL,
  followed BOOLEAN NOT NULL DEFAULT FALSE,
  followed_at TEXT
);

CREATE TABLE IF NOT EXISTS agency_snapshots (
  run_id TEXT NOT NULL,
  pass_index INTEGER NOT NULL,
  page_shape_ok BOOLEAN NOT NULL DEFAULT FALSE,
  following_count INTEGER,
  active_tab TEXT,
  challenge_signals_json TEXT NOT NULL,
  agencies_count INTEGER NOT NULL DEFAULT 0,
  snapshot_json TEXT NOT NULL,
  PRIMARY KEY (run_id, pass_index)
);

CREATE TABLE IF NOT EXISTS agency_observations (
  run_id TEXT NOT NULL,
  pass_index INTEGER NOT NULL,
  position_index INTEGER NOT NULL,
  company_id TEXT NOT NULL,
  company_url TEXT NOT NULL,
  name TEXT NOT NULL,
  subtitle TEXT,
  followers_text TEXT,
  already_following BOOLEAN NOT NULL DEFAULT FALSE,
  follow_selector TEXT,
  action_taken TEXT,
  PRIMARY KEY (run_id, pass_index, company_id)
);
"""


class StateStore:
    def __init__(self, db_path: Path | None = None, *, database_url: str | None = None) -> None:
        self.db_path = db_path
        self.database_url = database_url
        self.param = "%s" if database_url else "?"
        if database_url:
            import psycopg
            from psycopg.rows import dict_row

            self.conn = psycopg.connect(database_url, row_factory=dict_row)
            self.conn.execute(POSTGRES_SCHEMA)
            self.conn.execute("ALTER TABLE runs ADD COLUMN IF NOT EXISTS posts_reposted INTEGER NOT NULL DEFAULT 0")
            self.conn.execute("ALTER TABLE runs ADD COLUMN IF NOT EXISTS companies_scanned INTEGER NOT NULL DEFAULT 0")
            self.conn.execute("ALTER TABLE runs ADD COLUMN IF NOT EXISTS companies_followed INTEGER NOT NULL DEFAULT 0")
            self.conn.execute("ALTER TABLE posts ADD COLUMN IF NOT EXISTS post_url TEXT")
            self.conn.execute("ALTER TABLE posts ADD COLUMN IF NOT EXISTS reposted BOOLEAN NOT NULL DEFAULT FALSE")
            self.conn.execute("ALTER TABLE posts ADD COLUMN IF NOT EXISTS reposted_by_actor BOOLEAN NOT NULL DEFAULT FALSE")
            self.conn.execute("ALTER TABLE post_observations ADD COLUMN IF NOT EXISTS post_url TEXT")
            self.conn.execute("ALTER TABLE post_observations ADD COLUMN IF NOT EXISTS already_reposted BOOLEAN NOT NULL DEFAULT FALSE")
            self.conn.execute("ALTER TABLE post_observations ADD COLUMN IF NOT EXISTS repost_selector TEXT")
            self.conn.execute("ALTER TABLE runs ADD COLUMN IF NOT EXISTS agencies_scanned INTEGER NOT NULL DEFAULT 0")
            self.conn.execute("ALTER TABLE runs ADD COLUMN IF NOT EXISTS agencies_followed INTEGER NOT NULL DEFAULT 0")
            self.conn.commit()
        else:
            assert db_path is not None
            db_path.parent.mkdir(parents=True, exist_ok=True)
            self.conn = sqlite3.connect(db_path)
            self.conn.row_factory = sqlite3.Row
            self.conn.executescript(SQLITE_SCHEMA)
            self._ensure_sqlite_column("runs", "posts_reposted", "INTEGER NOT NULL DEFAULT 0")
            self._ensure_sqlite_column("runs", "companies_scanned", "INTEGER NOT NULL DEFAULT 0")
            self._ensure_sqlite_column("runs", "companies_followed", "INTEGER NOT NULL DEFAULT 0")
            self._ensure_sqlite_column("runs", "agencies_scanned", "INTEGER NOT NULL DEFAULT 0")
            self._ensure_sqlite_column("runs", "agencies_followed", "INTEGER NOT NULL DEFAULT 0")
            self._ensure_sqlite_column("posts", "post_url", "TEXT")
            self._ensure_sqlite_column("posts", "reposted", "INTEGER NOT NULL DEFAULT 0")
            self._ensure_sqlite_column("posts", "reposted_by_actor", "INTEGER NOT NULL DEFAULT 0")
            self._ensure_sqlite_column("post_observations", "post_url", "TEXT")
            self._ensure_sqlite_column("post_observations", "already_reposted", "INTEGER NOT NULL DEFAULT 0")
            self._ensure_sqlite_column("post_observations", "repost_selector", "TEXT")

    def _ensure_sqlite_column(self, table: str, column: str, definition: str) -> None:
        if self.database_url:
            return
        rows = self.conn.execute(f"PRAGMA table_info({table})").fetchall()
        if any(row["name"] == column for row in rows):
            return
        self.conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    def _bool_value(self, value: bool) -> bool | int:
        return value if self.database_url else int(value)

    def start_run(self, run_id: str, started_at: str) -> None:
        self.conn.execute(
            f"INSERT INTO runs (run_id, started_at, status) VALUES ({self.param}, {self.param}, {self.param})",
            (run_id, started_at, "started"),
        )
        self.conn.commit()

    def close_incomplete_runs(
        self,
        *,
        finished_at_strategy: str = "started_at",
        status: str = "failed",
        stop_reason: str = "abandoned_started_row_cleanup",
    ) -> int:
        if finished_at_strategy != "started_at":
            raise ValueError(f"Unsupported finished_at_strategy: {finished_at_strategy!r}")
        cursor = self.conn.execute(
            f"""
            UPDATE runs
            SET finished_at = started_at,
                status = {self.param},
                stop_reason = CASE
                  WHEN stop_reason IS NULL OR stop_reason = '' THEN {self.param}
                  ELSE stop_reason
                END
            WHERE status = 'started' AND finished_at IS NULL
            """,
            (status, stop_reason),
        )
        self.conn.commit()
        return cursor.rowcount or 0

    def finish_run(
        self,
        run_id: str,
        *,
        finished_at: str,
        status: str,
        actor_verified: bool,
        posts_scanned: int,
        posts_liked: int,
        posts_reposted: int,
        comments_liked: int,
        companies_scanned: int | None = None,
        companies_followed: int | None = None,
        agencies_scanned: int | None = None,
        agencies_followed: int | None = None,
        stop_reason: str | None = None,
    ) -> None:
        resolved_companies_scanned = companies_scanned if companies_scanned is not None else agencies_scanned or 0
        resolved_companies_followed = companies_followed if companies_followed is not None else agencies_followed or 0
        self.conn.execute(
            f"""
            UPDATE runs
            SET finished_at = {self.param}, status = {self.param}, actor_verified = {self.param},
                posts_scanned = {self.param}, posts_liked = {self.param}, posts_reposted = {self.param},
                companies_scanned = {self.param}, companies_followed = {self.param},
                comments_liked = {self.param}, agencies_scanned = {self.param}, agencies_followed = {self.param}, stop_reason = {self.param}
            WHERE run_id = {self.param}
            """,
            (
                finished_at,
                status,
                self._bool_value(actor_verified),
                posts_scanned,
                posts_liked,
                posts_reposted,
                resolved_companies_scanned,
                resolved_companies_followed,
                comments_liked,
                resolved_companies_scanned,
                resolved_companies_followed,
                stop_reason,
                run_id,
            ),
        )
        self.conn.commit()

    def upsert_post(
        self,
        post_id: str,
        timestamp: str,
        *,
        post_url: str | None = None,
        liked: bool,
        liked_by_actor: bool,
        reposted: bool = False,
        reposted_by_actor: bool = False,
    ) -> None:
        if self.database_url:
            self.conn.execute(
                f"""
                INSERT INTO posts (post_id, post_url, first_seen_at, last_checked_at, liked, liked_by_actor, reposted, reposted_by_actor)
                VALUES ({self.param}, {self.param}, {self.param}, {self.param}, {self.param}, {self.param}, {self.param}, {self.param})
                ON CONFLICT(post_id) DO UPDATE SET
                  post_url = COALESCE(EXCLUDED.post_url, posts.post_url),
                  last_checked_at = EXCLUDED.last_checked_at,
                  liked = EXCLUDED.liked,
                  liked_by_actor = EXCLUDED.liked_by_actor,
                  reposted = EXCLUDED.reposted,
                  reposted_by_actor = EXCLUDED.reposted_by_actor
                """,
                (post_id, post_url, timestamp, timestamp, liked, liked_by_actor, reposted, reposted_by_actor),
            )
        else:
            self.conn.execute(
                f"""
                INSERT INTO posts (post_id, post_url, first_seen_at, last_checked_at, liked, liked_by_actor, reposted, reposted_by_actor)
                VALUES ({self.param}, {self.param}, {self.param}, {self.param}, {self.param}, {self.param}, {self.param}, {self.param})
                ON CONFLICT(post_id) DO UPDATE SET
                  post_url = COALESCE(excluded.post_url, posts.post_url),
                  last_checked_at = excluded.last_checked_at,
                  liked = excluded.liked,
                  liked_by_actor = excluded.liked_by_actor,
                  reposted = excluded.reposted,
                  reposted_by_actor = excluded.reposted_by_actor
                """,
                (
                    post_id,
                    post_url,
                    timestamp,
                    timestamp,
                    self._bool_value(liked),
                    self._bool_value(liked_by_actor),
                    self._bool_value(reposted),
                    self._bool_value(reposted_by_actor),
                ),
            )
        self.conn.commit()

    def upsert_comment(
        self,
        comment_id: str,
        post_id: str,
        parent_comment_id: str | None,
        timestamp: str,
        *,
        liked: bool,
    ) -> None:
        if self.database_url:
            self.conn.execute(
                f"""
                INSERT INTO comments (comment_id, post_id, parent_comment_id, first_seen_at, liked)
                VALUES ({self.param}, {self.param}, {self.param}, {self.param}, {self.param})
                ON CONFLICT(comment_id) DO UPDATE SET liked = EXCLUDED.liked
                """,
                (comment_id, post_id, parent_comment_id, timestamp, liked),
            )
        else:
            self.conn.execute(
                f"""
                INSERT INTO comments (comment_id, post_id, parent_comment_id, first_seen_at, liked)
                VALUES ({self.param}, {self.param}, {self.param}, {self.param}, {self.param})
                ON CONFLICT(comment_id) DO UPDATE SET liked = excluded.liked
                """,
                (comment_id, post_id, parent_comment_id, timestamp, self._bool_value(liked)),
            )
        self.conn.commit()

    def record_snapshot(self, run_id: str, pass_index: int, snapshot) -> None:
        search_markers_json = json.dumps(snapshot.search_markers, sort_keys=True)
        challenge_signals_json = json.dumps(snapshot.challenge_signals, sort_keys=True)
        snapshot_json = json.dumps(snapshot.to_dict(), sort_keys=True)
        self.conn.execute(
            f"""
            INSERT INTO feed_snapshots (
              run_id, pass_index, actor_name, actor_verified, search_shape_ok,
              search_markers_json, challenge_signals_json, posts_count, snapshot_json
            )
            VALUES ({self.param}, {self.param}, {self.param}, {self.param}, {self.param}, {self.param}, {self.param}, {self.param}, {self.param})
            ON CONFLICT(run_id, pass_index) DO UPDATE SET
              actor_name = excluded.actor_name,
              actor_verified = excluded.actor_verified,
              search_shape_ok = excluded.search_shape_ok,
              search_markers_json = excluded.search_markers_json,
              challenge_signals_json = excluded.challenge_signals_json,
              posts_count = excluded.posts_count,
              snapshot_json = excluded.snapshot_json
            """,
            (
                run_id,
                pass_index,
                snapshot.actor_name,
                self._bool_value(snapshot.actor_verified),
                self._bool_value(snapshot.search_shape_ok),
                search_markers_json,
                challenge_signals_json,
                len(snapshot.posts),
                snapshot_json,
            ),
        )
        for position_index, post in enumerate(snapshot.posts):
            self.conn.execute(
                f"""
                INSERT INTO post_observations (
                  run_id, pass_index, position_index, post_id, post_url, text, sponsored, already_liked,
                  already_reposted, interactable, like_selector, repost_selector, comments_expanded, comment_toggle_selector,
                  reply_toggle_selectors_json, comments_count
                )
                VALUES ({self.param}, {self.param}, {self.param}, {self.param}, {self.param}, {self.param}, {self.param}, {self.param}, {self.param}, {self.param}, {self.param}, {self.param}, {self.param}, {self.param}, {self.param}, {self.param})
                ON CONFLICT(run_id, pass_index, post_id) DO UPDATE SET
                  position_index = excluded.position_index,
                  post_url = COALESCE(excluded.post_url, post_observations.post_url),
                  text = excluded.text,
                  sponsored = excluded.sponsored,
                  already_liked = excluded.already_liked,
                  already_reposted = excluded.already_reposted,
                  interactable = excluded.interactable,
                  like_selector = excluded.like_selector,
                  repost_selector = excluded.repost_selector,
                  comments_expanded = excluded.comments_expanded,
                  comment_toggle_selector = excluded.comment_toggle_selector,
                  reply_toggle_selectors_json = excluded.reply_toggle_selectors_json,
                  comments_count = excluded.comments_count
                """,
                (
                    run_id,
                    pass_index,
                    position_index,
                    post.post_id,
                    post.post_url,
                    post.text,
                    self._bool_value(post.sponsored),
                    self._bool_value(post.already_liked),
                    self._bool_value(post.already_reposted),
                    self._bool_value(post.interactable),
                    post.like_selector,
                    post.repost_selector,
                    self._bool_value(post.comments_expanded),
                    post.comment_toggle_selector,
                    json.dumps(post.reply_toggle_selectors, sort_keys=True),
                    len(post.comments),
                ),
            )
            for comment_position_index, comment in enumerate(post.comments):
                self.conn.execute(
                    f"""
                    INSERT INTO comment_observations (
                      run_id, pass_index, post_id, position_index, comment_id,
                      parent_comment_id, text, liked, like_selector
                    )
                    VALUES ({self.param}, {self.param}, {self.param}, {self.param}, {self.param}, {self.param}, {self.param}, {self.param}, {self.param})
                    ON CONFLICT(run_id, pass_index, comment_id) DO UPDATE SET
                      post_id = excluded.post_id,
                      position_index = excluded.position_index,
                      parent_comment_id = excluded.parent_comment_id,
                      text = excluded.text,
                      liked = excluded.liked,
                      like_selector = excluded.like_selector
                    """,
                    (
                        run_id,
                        pass_index,
                        post.post_id,
                        comment_position_index,
                        comment.comment_id,
                        comment.parent_comment_id,
                        comment.text,
                        self._bool_value(comment.liked),
                        comment.like_selector,
                    ),
                )
        self.conn.commit()

    def record_run_report(self, run_id: str, search_url: str, artifact_path: str, report) -> None:
        report_dict = report.to_dict() if hasattr(report, "to_dict") else report
        normalized_report = normalize_report_payload(report_dict)
        screenshot_path = getattr(report, "screenshot_path", None)
        if screenshot_path is None and isinstance(report_dict, dict):
            screenshot_path = report_dict.get("screenshot_path")
        self.conn.execute(
            f"""
            INSERT INTO run_reports (run_id, search_url, artifact_path, screenshot_path, report_json)
            VALUES ({self.param}, {self.param}, {self.param}, {self.param}, {self.param})
            ON CONFLICT(run_id) DO UPDATE SET
              search_url = excluded.search_url,
              artifact_path = excluded.artifact_path,
              screenshot_path = excluded.screenshot_path,
              report_json = excluded.report_json
            """,
            (
                run_id,
                search_url,
                artifact_path,
                screenshot_path,
                json.dumps(normalized_report, sort_keys=True),
            ),
        )
        self.conn.commit()

    def upsert_company(
        self,
        company_id: str,
        timestamp: str,
        *,
        company_url: str,
        name: str,
        subtitle: str | None,
        followers_text: str | None,
        followed: bool,
        followed_at: str | None = None,
    ) -> None:
        if self.database_url:
            self.conn.execute(
                f"""
                INSERT INTO agencies (
                  company_id, company_url, name, subtitle, followers_text,
                  first_seen_at, last_seen_at, followed, followed_at
                )
                VALUES ({self.param}, {self.param}, {self.param}, {self.param}, {self.param}, {self.param}, {self.param}, {self.param}, {self.param})
                ON CONFLICT(company_id) DO UPDATE SET
                  company_url = EXCLUDED.company_url,
                  name = EXCLUDED.name,
                  subtitle = EXCLUDED.subtitle,
                  followers_text = EXCLUDED.followers_text,
                  last_seen_at = EXCLUDED.last_seen_at,
                  followed = EXCLUDED.followed,
                  followed_at = COALESCE(EXCLUDED.followed_at, agencies.followed_at)
                """,
                (
                    company_id,
                    company_url,
                    name,
                    subtitle,
                    followers_text,
                    timestamp,
                    timestamp,
                    followed,
                    followed_at,
                ),
            )
        else:
            self.conn.execute(
                f"""
                INSERT INTO agencies (
                  company_id, company_url, name, subtitle, followers_text,
                  first_seen_at, last_seen_at, followed, followed_at
                )
                VALUES ({self.param}, {self.param}, {self.param}, {self.param}, {self.param}, {self.param}, {self.param}, {self.param}, {self.param})
                ON CONFLICT(company_id) DO UPDATE SET
                  company_url = excluded.company_url,
                  name = excluded.name,
                  subtitle = excluded.subtitle,
                  followers_text = excluded.followers_text,
                  last_seen_at = excluded.last_seen_at,
                  followed = excluded.followed,
                  followed_at = COALESCE(excluded.followed_at, agencies.followed_at)
                """,
                (
                    company_id,
                    company_url,
                    name,
                    subtitle,
                    followers_text,
                    timestamp,
                    timestamp,
                    self._bool_value(followed),
                    followed_at,
                ),
            )
        self.conn.commit()

    def upsert_agency(
        self,
        company_id: str,
        timestamp: str,
        *,
        company_url: str,
        name: str,
        subtitle: str | None,
        followers_text: str | None,
        followed: bool,
        followed_at: str | None = None,
    ) -> None:
        self.upsert_company(
            company_id,
            timestamp,
            company_url=company_url,
            name=name,
            subtitle=subtitle,
            followers_text=followers_text,
            followed=followed,
            followed_at=followed_at,
        )

    def company_followed(self, company_id: str) -> bool:
        row = self.conn.execute(
            f"SELECT followed FROM agencies WHERE company_id = {self.param}",
            (company_id,),
        ).fetchone()
        return bool(row and row["followed"])

    def agency_followed(self, company_id: str) -> bool:
        return self.company_followed(company_id)

    def record_company_snapshot(self, run_id: str, pass_index: int, snapshot) -> None:
        self.conn.execute(
            f"""
            INSERT INTO agency_snapshots (
              run_id, pass_index, page_shape_ok, following_count, active_tab,
              challenge_signals_json, agencies_count, snapshot_json
            )
            VALUES ({self.param}, {self.param}, {self.param}, {self.param}, {self.param}, {self.param}, {self.param}, {self.param})
            ON CONFLICT(run_id, pass_index) DO UPDATE SET
              page_shape_ok = excluded.page_shape_ok,
              following_count = excluded.following_count,
              active_tab = excluded.active_tab,
              challenge_signals_json = excluded.challenge_signals_json,
              agencies_count = excluded.agencies_count,
              snapshot_json = excluded.snapshot_json
            """,
            (
                run_id,
                pass_index,
                self._bool_value(snapshot.page_shape_ok),
                snapshot.following_count,
                snapshot.active_tab,
                json.dumps(snapshot.challenge_signals, sort_keys=True),
                len(snapshot.companies),
                json.dumps(snapshot.to_dict(), sort_keys=True),
            ),
        )
        self.conn.commit()

    def record_agency_snapshot(self, run_id: str, pass_index: int, snapshot) -> None:
        self.record_company_snapshot(run_id, pass_index, snapshot)

    def record_company_observation(
        self,
        run_id: str,
        pass_index: int,
        position_index: int,
        company,
        *,
        action_taken: str | None,
    ) -> None:
        self.conn.execute(
            f"""
            INSERT INTO agency_observations (
              run_id, pass_index, position_index, company_id, company_url, name,
              subtitle, followers_text, already_following, follow_selector, action_taken
            )
            VALUES ({self.param}, {self.param}, {self.param}, {self.param}, {self.param}, {self.param}, {self.param}, {self.param}, {self.param}, {self.param}, {self.param})
            ON CONFLICT(run_id, pass_index, company_id) DO UPDATE SET
              position_index = excluded.position_index,
              company_url = excluded.company_url,
              name = excluded.name,
              subtitle = excluded.subtitle,
              followers_text = excluded.followers_text,
              already_following = excluded.already_following,
              follow_selector = excluded.follow_selector,
              action_taken = excluded.action_taken
            """,
            (
                run_id,
                pass_index,
                position_index,
                company.company_id,
                company.company_url,
                company.name,
                company.subtitle,
                company.followers_text,
                self._bool_value(company.already_following),
                company.follow_selector,
                action_taken,
            ),
        )
        self.conn.commit()

    def record_agency_observation(
        self,
        run_id: str,
        pass_index: int,
        position_index: int,
        agency,
        *,
        action_taken: str | None,
    ) -> None:
        self.record_company_observation(
            run_id,
            pass_index,
            position_index,
            agency,
            action_taken=action_taken,
        )

    def post_processed(self, post_id: str) -> bool:
        row = self.conn.execute(
            f"SELECT liked_by_actor FROM posts WHERE post_id = {self.param}",
            (post_id,),
        ).fetchone()
        return bool(row and row["liked_by_actor"])

    def comment_processed(self, comment_id: str) -> bool:
        row = self.conn.execute(
            f"SELECT liked FROM comments WHERE comment_id = {self.param}",
            (comment_id,),
        ).fetchone()
        return bool(row and row["liked"])

    def post_reposted(self, post_id: str) -> bool:
        row = self.conn.execute(
            f"SELECT reposted_by_actor FROM posts WHERE post_id = {self.param}",
            (post_id,),
        ).fetchone()
        return bool(row and row["reposted_by_actor"])
