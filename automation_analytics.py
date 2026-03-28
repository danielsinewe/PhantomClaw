from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from typing import Any

from automation_catalog import automation_label, automation_surface, canonical_automation_name


ANALYTICS_POSTGRES_TABLE_SCHEMA = """
CREATE TABLE IF NOT EXISTS automation_runs (
  automation_name TEXT NOT NULL,
  automation_label TEXT NOT NULL,
  platform TEXT NOT NULL,
  surface TEXT,
  run_id TEXT NOT NULL,
  started_at TEXT NOT NULL,
  finished_at TEXT,
  status TEXT NOT NULL,
  stop_reason TEXT,
  search_url TEXT,
  artifact_path TEXT,
  screenshot_path TEXT,
  page_shape_ok BOOLEAN,
  actor_verified BOOLEAN,
  search_shape_ok BOOLEAN,
  challenge_detected BOOLEAN NOT NULL DEFAULT FALSE,
  items_scanned INTEGER NOT NULL DEFAULT 0,
  items_considered INTEGER NOT NULL DEFAULT 0,
  actions_total INTEGER NOT NULL DEFAULT 0,
  likes_count INTEGER NOT NULL DEFAULT 0,
  reposts_count INTEGER NOT NULL DEFAULT 0,
  comments_liked_count INTEGER NOT NULL DEFAULT 0,
  follows_count INTEGER NOT NULL DEFAULT 0,
  metrics_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  report_json JSONB NOT NULL,
  PRIMARY KEY (automation_name, run_id)
);
"""

ANALYTICS_POSTGRES_VIEW_SCHEMA = """
DROP VIEW IF EXISTS automation_kpi_runs_v1;

CREATE OR REPLACE VIEW automation_kpi_runs_v1 AS
SELECT
  automation_name,
  automation_label,
  platform,
  COALESCE(surface, 'unknown') AS surface,
  run_id,
  started_at,
  finished_at,
  started_at::timestamptz AS started_at_ts,
  CASE WHEN finished_at IS NULL THEN NULL ELSE finished_at::timestamptz END AS finished_at_ts,
  CASE
    WHEN finished_at IS NULL THEN NULL
    ELSE EXTRACT(EPOCH FROM ((finished_at::timestamptz) - (started_at::timestamptz)))
  END AS duration_seconds,
  status,
  stop_reason,
  search_url,
  artifact_path,
  screenshot_path,
  COALESCE(page_shape_ok, FALSE) AS page_shape_ok,
  COALESCE(actor_verified, FALSE) AS actor_verified,
  COALESCE(search_shape_ok, FALSE) AS search_shape_ok,
  challenge_detected,
  items_scanned,
  items_considered,
  actions_total,
  likes_count,
  reposts_count,
  comments_liked_count,
  follows_count,
  metrics_json,
  report_json
FROM automation_runs;
"""


def _report_to_dict(report: Any) -> dict[str, Any]:
    if is_dataclass(report):
        return asdict(report)
    if isinstance(report, dict):
        return report
    raise TypeError(f"Unsupported report type: {type(report)!r}")


def trustoutreach_metrics(report: Any) -> dict[str, Any]:
    data = _report_to_dict(report)
    return {
        "page_shape_ok": None,
        "actor_verified": bool(data.get("actor_verified", False)),
        "search_shape_ok": bool(data.get("search_shape_ok", False)),
        "challenge_detected": data.get("stop_reason") == "anti_automation_challenge",
        "items_scanned": int(data.get("posts_scanned", 0)),
        "items_considered": int(data.get("posts_liked", 0)) + int(data.get("posts_reposted", 0)) + int(data.get("comments_liked", 0)) + int(data.get("agencies_followed", 0)),
        "actions_total": int(data.get("posts_liked", 0)) + int(data.get("posts_reposted", 0)) + int(data.get("comments_liked", 0)) + int(data.get("agencies_followed", 0)),
        "likes_count": int(data.get("posts_liked", 0)),
        "reposts_count": int(data.get("posts_reposted", 0)),
        "comments_liked_count": int(data.get("comments_liked", 0)),
        "follows_count": int(data.get("agencies_followed", 0)),
        "metrics_json": {
            "posts_scanned": int(data.get("posts_scanned", 0)),
            "posts_liked": int(data.get("posts_liked", 0)),
            "posts_reposted": int(data.get("posts_reposted", 0)),
            "comments_liked": int(data.get("comments_liked", 0)),
            "agencies_scanned": int(data.get("agencies_scanned", 0)),
            "agencies_followed": int(data.get("agencies_followed", 0)),
        },
    }


def linkedin_sales_community_metrics(report: Any) -> dict[str, Any]:
    data = _report_to_dict(report)
    return {
        "page_shape_ok": bool(data.get("page_shape_ok", False)),
        "actor_verified": None,
        "search_shape_ok": None,
        "challenge_detected": data.get("stop_reason") == "challenge_signals",
        "items_scanned": int(data.get("items_scanned", 0)),
        "items_considered": int(data.get("items_considered", 0)),
        "actions_total": int(data.get("items_liked", 0)),
        "likes_count": int(data.get("items_liked", 0)),
        "reposts_count": 0,
        "comments_liked_count": 0,
        "follows_count": 0,
        "metrics_json": {
            "items_scanned": int(data.get("items_scanned", 0)),
            "items_considered": int(data.get("items_considered", 0)),
            "items_liked": int(data.get("items_liked", 0)),
        },
    }


def upsert_automation_run(
    *,
    database_url: str | None,
    automation_name: str,
    platform: str,
    surface: str | None,
    search_url: str,
    artifact_path: str,
    report: Any,
    metrics: dict[str, Any],
) -> None:
    if not database_url:
        return

    import psycopg

    report_dict = _report_to_dict(report)
    canonical_name = canonical_automation_name(automation_name)
    with psycopg.connect(database_url) as conn:
        with conn.cursor() as cur:
            cur.execute(ANALYTICS_POSTGRES_TABLE_SCHEMA)
            cur.execute("ALTER TABLE automation_runs ADD COLUMN IF NOT EXISTS automation_label TEXT")
            cur.execute("ALTER TABLE automation_runs ADD COLUMN IF NOT EXISTS surface TEXT")
            cur.execute(ANALYTICS_POSTGRES_VIEW_SCHEMA)
            cur.execute(
                """
                UPDATE automation_runs
                SET
                  automation_name = CASE automation_name
                    WHEN 'trustoutreach-linkedin' THEN 'linkedin-company-profile-engagement'
                    WHEN 'linkedin-sales-community' THEN 'linkedin-sales-community-engagement'
                    ELSE automation_name
                  END,
                  automation_label = CASE
                    WHEN automation_name IN ('trustoutreach-linkedin', 'linkedin-company-profile-engagement') THEN 'LinkedIn Company Profile Engagement'
                    WHEN automation_name IN ('linkedin-sales-community', 'linkedin-sales-community-engagement') THEN 'LinkedIn Sales Community Engagement'
                    ELSE COALESCE(automation_label, automation_name)
                  END,
                  surface = CASE
                    WHEN automation_name IN ('trustoutreach-linkedin', 'linkedin-company-profile-engagement') THEN 'core'
                    WHEN automation_name IN ('linkedin-sales-community', 'linkedin-sales-community-engagement') THEN 'sales-community'
                    ELSE COALESCE(surface, 'unknown')
                  END
                WHERE automation_name IN ('trustoutreach-linkedin', 'linkedin-sales-community')
                """
            )
            cur.execute(
                """
                INSERT INTO automation_runs (
                  automation_name, automation_label, platform, surface, run_id, started_at, finished_at, status, stop_reason,
                  search_url, artifact_path, screenshot_path, page_shape_ok, actor_verified, search_shape_ok,
                  challenge_detected, items_scanned, items_considered, actions_total, likes_count,
                  reposts_count, comments_liked_count, follows_count, metrics_json, report_json
                )
                VALUES (
                  %(automation_name)s, %(automation_label)s, %(platform)s, %(surface)s, %(run_id)s, %(started_at)s, %(finished_at)s, %(status)s, %(stop_reason)s,
                  %(search_url)s, %(artifact_path)s, %(screenshot_path)s, %(page_shape_ok)s, %(actor_verified)s, %(search_shape_ok)s,
                  %(challenge_detected)s, %(items_scanned)s, %(items_considered)s, %(actions_total)s, %(likes_count)s,
                  %(reposts_count)s, %(comments_liked_count)s, %(follows_count)s, %(metrics_json)s::jsonb, %(report_json)s::jsonb
                )
                ON CONFLICT (automation_name, run_id) DO UPDATE SET
                  automation_label = EXCLUDED.automation_label,
                  platform = EXCLUDED.platform,
                  surface = EXCLUDED.surface,
                  started_at = EXCLUDED.started_at,
                  finished_at = EXCLUDED.finished_at,
                  status = EXCLUDED.status,
                  stop_reason = EXCLUDED.stop_reason,
                  search_url = EXCLUDED.search_url,
                  artifact_path = EXCLUDED.artifact_path,
                  screenshot_path = EXCLUDED.screenshot_path,
                  page_shape_ok = EXCLUDED.page_shape_ok,
                  actor_verified = EXCLUDED.actor_verified,
                  search_shape_ok = EXCLUDED.search_shape_ok,
                  challenge_detected = EXCLUDED.challenge_detected,
                  items_scanned = EXCLUDED.items_scanned,
                  items_considered = EXCLUDED.items_considered,
                  actions_total = EXCLUDED.actions_total,
                  likes_count = EXCLUDED.likes_count,
                  reposts_count = EXCLUDED.reposts_count,
                  comments_liked_count = EXCLUDED.comments_liked_count,
                  follows_count = EXCLUDED.follows_count,
                  metrics_json = EXCLUDED.metrics_json,
                  report_json = EXCLUDED.report_json
                """,
                {
                    "automation_name": canonical_name,
                    "automation_label": automation_label(canonical_name),
                    "platform": platform,
                    "surface": surface or automation_surface(canonical_name),
                    "run_id": report_dict["run_id"],
                    "started_at": report_dict["started_at"],
                    "finished_at": report_dict.get("finished_at"),
                    "status": report_dict["status"],
                    "stop_reason": report_dict.get("stop_reason"),
                    "search_url": search_url,
                    "artifact_path": artifact_path,
                    "screenshot_path": report_dict.get("screenshot_path"),
                    "page_shape_ok": metrics.get("page_shape_ok"),
                    "actor_verified": metrics.get("actor_verified"),
                    "search_shape_ok": metrics.get("search_shape_ok"),
                    "challenge_detected": bool(metrics.get("challenge_detected", False)),
                    "items_scanned": int(metrics.get("items_scanned", 0)),
                    "items_considered": int(metrics.get("items_considered", 0)),
                    "actions_total": int(metrics.get("actions_total", 0)),
                    "likes_count": int(metrics.get("likes_count", 0)),
                    "reposts_count": int(metrics.get("reposts_count", 0)),
                    "comments_liked_count": int(metrics.get("comments_liked_count", 0)),
                    "follows_count": int(metrics.get("follows_count", 0)),
                    "metrics_json": json.dumps(metrics.get("metrics_json", {}), sort_keys=True),
                    "report_json": json.dumps(report_dict, sort_keys=True),
                },
            )
        conn.commit()
