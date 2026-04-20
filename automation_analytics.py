from __future__ import annotations

import json
import re
from dataclasses import asdict, is_dataclass
from typing import Any

from automation_catalog import automation_label, automation_surface, canonical_automation_name


ANALYTICS_POSTGRES_TABLE_SCHEMA = """
CREATE TABLE IF NOT EXISTS automation_runs (
  automation_name TEXT NOT NULL,
  automation_label TEXT NOT NULL,
  platform TEXT NOT NULL,
  surface TEXT,
  workspace_slug TEXT,
  received_at TEXT,
  profile_name TEXT,
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
  companies_scanned INTEGER NOT NULL DEFAULT 0,
  companies_followed INTEGER NOT NULL DEFAULT 0,
  metrics_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  action_events_json JSONB NOT NULL DEFAULT '[]'::jsonb,
  report_json JSONB NOT NULL,
  PRIMARY KEY (automation_name, run_id)
);
"""

NORTH_STAR_DAILY_METRICS_TABLE_SCHEMA = """
CREATE TABLE IF NOT EXISTS automation_daily_metrics (
  workspace_slug TEXT,
  platform TEXT NOT NULL,
  profile_name TEXT NOT NULL,
  metric_name TEXT NOT NULL,
  metric_date DATE NOT NULL,
  metric_value NUMERIC NOT NULL,
  source TEXT NOT NULL DEFAULT 'cron',
  captured_at TEXT NOT NULL,
  run_id TEXT,
  metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  PRIMARY KEY (workspace_slug, platform, profile_name, metric_name, metric_date)
);
"""

NORTH_STAR_DAILY_METRICS_VIEW_SCHEMA = """
DROP VIEW IF EXISTS automation_daily_metrics_v1;

CREATE OR REPLACE VIEW automation_daily_metrics_v1 AS
SELECT
  workspace_slug,
  platform,
  profile_name,
  metric_name,
  metric_date,
  metric_value,
  LAG(metric_value) OVER (
    PARTITION BY workspace_slug, platform, profile_name, metric_name
    ORDER BY metric_date
  ) AS previous_metric_value,
  metric_value - LAG(metric_value) OVER (
    PARTITION BY workspace_slug, platform, profile_name, metric_name
    ORDER BY metric_date
  ) AS daily_delta,
  source,
  captured_at,
  CASE
    WHEN captured_at IS NULL THEN NULL
    ELSE captured_at::timestamptz
  END AS captured_at_ts,
  run_id,
  metadata_json
FROM automation_daily_metrics;
"""

ANALYTICS_POSTGRES_VIEW_SCHEMA = """
DROP VIEW IF EXISTS automation_kpi_runs_v1;

CREATE OR REPLACE VIEW automation_kpi_runs_v1 AS
SELECT
  automation_name,
  automation_label,
  platform,
  COALESCE(surface, 'unknown') AS surface,
  workspace_slug,
  received_at,
  CASE
    WHEN received_at IS NULL THEN NULL
    ELSE received_at::timestamptz
  END AS received_at_ts,
  COALESCE(
    profile_name,
    report_json->>'profile_name',
    report_json->>'actor_name',
    CASE WHEN automation_name = 'linkedin-company-profile-engagement' THEN 'TrustOutreach' END
  ) AS profile_name,
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
  repost_ctx.reposted_post_url AS reposted_post_url,
  comments_liked_count,
  follows_count,
  metrics_json->>'north_star_metric' AS north_star_metric,
  metrics_json->>'workflow_type' AS workflow_type,
  CASE
    WHEN metrics_json ? 'peerlist_profile_followers_before'
      AND metrics_json->>'peerlist_profile_followers_before' <> ''
    THEN (metrics_json->>'peerlist_profile_followers_before')::integer
    ELSE NULL
  END AS peerlist_profile_followers_before,
  CASE
    WHEN metrics_json ? 'peerlist_profile_followers_after'
      AND metrics_json->>'peerlist_profile_followers_after' <> ''
    THEN (metrics_json->>'peerlist_profile_followers_after')::integer
    ELSE NULL
  END AS peerlist_profile_followers_after,
  CASE
    WHEN metrics_json ? 'peerlist_profile_followers_delta'
      AND metrics_json->>'peerlist_profile_followers_delta' <> ''
    THEN (metrics_json->>'peerlist_profile_followers_delta')::integer
    ELSE NULL
  END AS peerlist_profile_followers_delta,
  CASE
    WHEN metrics_json ? 'unfollows_count'
      AND metrics_json->>'unfollows_count' <> ''
    THEN (metrics_json->>'unfollows_count')::integer
    ELSE 0
  END AS unfollows_count,
  CASE
    WHEN metrics_json ? 'peers_preserved_count'
      AND metrics_json->>'peers_preserved_count' <> ''
    THEN (metrics_json->>'peers_preserved_count')::integer
    ELSE 0
  END AS peers_preserved_count,
  CASE
    WHEN metrics_json ? 'skipped_count'
      AND metrics_json->>'skipped_count' <> ''
    THEN (metrics_json->>'skipped_count')::integer
    ELSE 0
  END AS skipped_count,
  CASE
    WHEN metrics_json ? 'blockers_count'
      AND metrics_json->>'blockers_count' <> ''
    THEN (metrics_json->>'blockers_count')::integer
    ELSE 0
  END AS blockers_count,
  COALESCE(companies_scanned, 0) AS companies_scanned,
  COALESCE(companies_followed, 0) AS companies_followed,
  metrics_json,
  action_events_json,
  report_json
FROM automation_runs
LEFT JOIN LATERAL (
  SELECT
    COALESCE(
      NULLIF(repost_event->>'target_url', ''),
      NULLIF(repost_event->>'post_url', ''),
      NULLIF(post_row.post_url, ''),
      NULLIF(post_ctx.post_url, ''),
      CASE
        WHEN COALESCE(repost_event->>'post_id', '') LIKE 'urn:li:activity:%'
          THEN concat('https://www.linkedin.com/feed/update/', repost_event->>'post_id', '/')
        WHEN comment_ctx.activity_urn IS NOT NULL
          THEN concat('https://www.linkedin.com/feed/update/', comment_ctx.activity_urn, '/')
        ELSE NULL
      END
    ) AS reposted_post_url
  FROM jsonb_array_elements(COALESCE(automation_runs.action_events_json, '[]'::jsonb)) WITH ORDINALITY AS action_events(repost_event, action_ordinal)
  LEFT JOIN posts post_row
    ON post_row.post_id = repost_event->>'post_id'
  LEFT JOIN LATERAL (
    SELECT post_url
    FROM post_observations
    WHERE post_observations.run_id = automation_runs.run_id
      AND post_observations.post_id = repost_event->>'post_id'
      AND COALESCE(post_observations.post_url, '') <> ''
    ORDER BY pass_index DESC, position_index DESC
    LIMIT 1
  ) post_ctx ON TRUE
  LEFT JOIN LATERAL (
    SELECT (regexp_match(comment_id, 'urn:li:comment:\\((urn:li:activity:[0-9]+),'))[1] AS activity_urn
    FROM comment_observations
    WHERE comment_observations.run_id = automation_runs.run_id
      AND comment_observations.post_id = repost_event->>'post_id'
    ORDER BY pass_index DESC, position_index DESC
    LIMIT 1
  ) comment_ctx ON TRUE
  WHERE repost_event->>'type' = 'post_reposted'
  ORDER BY action_ordinal
  LIMIT 1
) repost_ctx ON TRUE;
"""

ANALYTICS_POSTGRES_ACTION_EVENTS_VIEW_SCHEMA = """
DROP VIEW IF EXISTS automation_action_events_v1;

CREATE OR REPLACE VIEW automation_action_events_v1 AS
SELECT
  automation_name,
  automation_label,
  platform,
  COALESCE(surface, 'unknown') AS surface,
  COALESCE(
    profile_name,
    report_json->>'profile_name',
    report_json->>'actor_name',
    CASE WHEN automation_name = 'linkedin-company-profile-engagement' THEN 'TrustOutreach' END
  ) AS profile_name,
  run_id,
  started_at,
  finished_at,
  status,
  action_ordinal - 1 AS action_index,
  action_event->>'type' AS action_type,
  CASE action_event->>'type'
    WHEN 'post_liked' THEN 'Post liked'
    WHEN 'post_reposted' THEN 'Post reposted'
    WHEN 'comment_liked' THEN 'Comment liked'
    WHEN 'company_followed' THEN 'Company followed'
    WHEN 'agency_followed' THEN 'Company followed'
    WHEN 'peerlist_post_upvoted' THEN 'Peerlist post upvoted'
    WHEN 'peerlist_profile_followed' THEN 'Peerlist profile followed'
    WHEN 'peerlist_profile_unfollowed' THEN 'Peerlist profile unfollowed'
    WHEN 'item_action_taken' THEN 'Item action taken'
    ELSE COALESCE(action_event->>'type', 'unknown')
  END AS action_label,
  action_event->>'ts' AS action_ts,
  action_event->>'post_id' AS post_id,
  action_event->>'post_url' AS post_url,
  action_event->>'comment_id' AS comment_id,
  action_event->>'company_id' AS company_id,
  action_event->>'company_url' AS company_url,
  CASE
    WHEN COALESCE(action_event->>'target_name', '') <> '' THEN action_event->>'target_name'
    WHEN COALESCE(action_event->>'name', '') <> '' THEN action_event->>'name'
    WHEN COALESCE(post_ctx.text, '') <> '' THEN NULLIF(regexp_replace(split_part(post_ctx.text, E'\\n\\n', 2), '^[^[:alnum:]]+', ''), '')
    ELSE NULL
  END AS target_name,
  CASE
    WHEN COALESCE(action_event->>'target_url', '') <> '' THEN action_event->>'target_url'
    WHEN COALESCE(action_event->>'post_url', '') <> '' THEN action_event->>'post_url'
    WHEN COALESCE(post_row.post_url, '') <> '' THEN post_row.post_url
    WHEN COALESCE(post_ctx.post_url, '') <> '' THEN post_ctx.post_url
    WHEN COALESCE(action_event->>'post_id', '') LIKE 'urn:li:activity:%' THEN concat('https://www.linkedin.com/feed/update/', action_event->>'post_id', '/')
    WHEN COALESCE(action_event->>'company_url', '') <> '' THEN action_event->>'company_url'
    WHEN COALESCE(action_event->>'company_id', '') <> '' THEN concat('https://www.linkedin.com/company/', action_event->>'company_id', '/')
    ELSE NULL
  END AS target_url,
  COALESCE(
    CASE
      WHEN COALESCE(action_event->>'target_url', '') <> '' THEN action_event->>'target_url'
      WHEN COALESCE(action_event->>'post_url', '') <> '' THEN action_event->>'post_url'
      WHEN COALESCE(post_row.post_url, '') <> '' THEN post_row.post_url
      WHEN COALESCE(post_ctx.post_url, '') <> '' THEN post_ctx.post_url
      WHEN COALESCE(action_event->>'post_id', '') LIKE 'urn:li:activity:%' THEN concat('https://www.linkedin.com/feed/update/', action_event->>'post_id', '/')
      WHEN COALESCE(action_event->>'company_url', '') <> '' THEN action_event->>'company_url'
      WHEN COALESCE(action_event->>'company_id', '') <> '' THEN concat('https://www.linkedin.com/company/', action_event->>'company_id', '/')
      ELSE NULL
    END,
    NULLIF(action_event->>'post_id', ''),
    NULLIF(action_event->>'comment_id', ''),
    NULLIF(action_event->>'company_id', '')
  ) AS target_locator,
  COALESCE(
    NULLIF(action_event->>'target_name', ''),
    NULLIF(action_event->>'name', ''),
    CASE
      WHEN COALESCE(post_ctx.text, '') <> '' THEN left(regexp_replace(post_ctx.text, E'\\s+', ' ', 'g'), 120)
      ELSE NULL
    END,
    NULLIF(action_event->>'post_id', ''),
    NULLIF(action_event->>'comment_id', ''),
    NULLIF(action_event->>'company_id', '')
  ) AS target_summary,
  CASE
    WHEN COALESCE(action_event->>'target_excerpt', '') <> '' THEN action_event->>'target_excerpt'
    WHEN COALESCE(action_event->>'name', '') <> '' THEN action_event->>'name'
    WHEN COALESCE(post_ctx.text, '') <> '' THEN left(regexp_replace(post_ctx.text, E'\\s+', ' ', 'g'), 180)
    ELSE NULL
  END AS target_excerpt,
  action_event->>'selector' AS selector,
  action_event->>'reason' AS reason,
  action_event->>'message' AS message,
  CASE
    WHEN action_event ? 'verified'
      AND action_event->>'verified' <> ''
    THEN (action_event->>'verified')::boolean
    ELSE NULL
  END AS verified,
  action_event AS action_event_json
FROM automation_runs
CROSS JOIN LATERAL jsonb_array_elements(COALESCE(action_events_json, '[]'::jsonb)) WITH ORDINALITY AS action_events(action_event, action_ordinal)
LEFT JOIN posts post_row
  ON post_row.post_id = action_events.action_event->>'post_id'
LEFT JOIN LATERAL (
  SELECT post_url, text
  FROM post_observations
  WHERE post_observations.run_id = automation_runs.run_id
    AND post_observations.post_id = action_events.action_event->>'post_id'
  ORDER BY pass_index DESC, position_index DESC
  LIMIT 1
) post_ctx ON TRUE;
"""


ACTION_EVENT_TYPES = {
    "company_followed",
    "comment_liked",
    "item_action_taken",
    "peerlist_post_upvoted",
    "peerlist_profile_followed",
    "peerlist_profile_unfollowed",
    "post_liked",
    "post_reposted",
}

LEGACY_COMPANY_EVENT_PREFIX = "agency_"
NORMALIZED_COMPANY_EVENT_PREFIX = "company_"


def normalize_company_event_value(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    if value.startswith(LEGACY_COMPANY_EVENT_PREFIX):
        return f"{NORMALIZED_COMPANY_EVENT_PREFIX}{value[len(LEGACY_COMPANY_EVENT_PREFIX):]}"
    return value


def normalize_report_payload(report: Any) -> dict[str, Any]:
    data = _report_to_dict(report)
    normalized = dict(data)

    stop_reason = normalized.get("stop_reason")
    normalized_stop_reason = normalize_company_event_value(stop_reason)
    if normalized_stop_reason != stop_reason:
        normalized["stop_reason"] = normalized_stop_reason

    events = normalized.get("events")
    if isinstance(events, list):
        normalized_events: list[Any] = []
        for event in events:
            if isinstance(event, dict):
                normalized_event = dict(event)
                event_type = normalized_event.get("type")
                normalized_type = normalize_company_event_value(event_type)
                if normalized_type != event_type:
                    normalized_event["type"] = normalized_type
                reason = normalized_event.get("reason")
                normalized_reason = normalize_company_event_value(reason)
                if normalized_reason != reason:
                    normalized_event["reason"] = normalized_reason
                normalized_events.append(normalized_event)
            else:
                normalized_events.append(event)
        normalized["events"] = normalized_events

    skips = normalized.get("skips")
    if isinstance(skips, list):
        normalized_skips: list[Any] = []
        for skip in skips:
            if isinstance(skip, dict):
                normalized_skip = dict(skip)
                reason = normalized_skip.get("reason")
                normalized_reason = normalize_company_event_value(reason)
                if normalized_reason != reason:
                    normalized_skip["reason"] = normalized_reason
                normalized_skips.append(normalized_skip)
            else:
                normalized_skips.append(skip)
        normalized["skips"] = normalized_skips

    companies_scanned = normalized.get("companies_scanned")
    agencies_scanned = normalized.get("agencies_scanned")
    if companies_scanned is None and agencies_scanned is not None:
        normalized["companies_scanned"] = agencies_scanned
    elif companies_scanned is not None and agencies_scanned is None:
        normalized["agencies_scanned"] = companies_scanned

    companies_followed = normalized.get("companies_followed")
    agencies_followed = normalized.get("agencies_followed")
    if companies_followed is None and agencies_followed is not None:
        normalized["companies_followed"] = agencies_followed
    elif companies_followed is not None and agencies_followed is None:
        normalized["agencies_followed"] = companies_followed

    return normalized


def normalize_report_events(report: Any) -> dict[str, Any]:
    return normalize_report_payload(report)


def extract_post_target_name(post_text: str | None) -> str | None:
    if not post_text:
        return None
    lines = [line.strip() for line in post_text.splitlines()]
    lines = [line for line in lines if line]
    if not lines:
        return None
    if lines[0].lower().startswith("feed post"):
        lines = lines[1:]
    for candidate in lines:
        candidate = re.sub(r"^[^\w]+", "", candidate, flags=re.UNICODE).strip()
        if not candidate:
            continue
        lower = candidate.lower()
        if lower in {"following", "like", "comment", "repost", "send", "reply"}:
            continue
        if "followers" in lower or "reaction button state" in lower:
            continue
        if len(candidate) > 120:
            continue
        return candidate
    return None


def extract_post_excerpt(post_text: str | None, limit: int = 180) -> str | None:
    if not post_text:
        return None
    cleaned = re.sub(r"\s+", " ", post_text).strip()
    if not cleaned:
        return None
    cleaned = re.sub(r"^Feed post\s+", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"^[^\w]+", "", cleaned, flags=re.UNICODE)
    cleaned = cleaned.replace(" • ", " ")
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned[:limit]


def _report_to_dict(report: Any) -> dict[str, Any]:
    if is_dataclass(report):
        return asdict(report)
    if isinstance(report, dict):
        return report
    raise TypeError(f"Unsupported report type: {type(report)!r}")


def action_events_from_report(report: Any) -> list[dict[str, Any]]:
    data = normalize_report_payload(report)
    events = data.get("events")
    if not isinstance(events, list):
        return []
    action_events: list[dict[str, Any]] = []
    for event in events:
        if isinstance(event, dict) and event.get("type") in ACTION_EVENT_TYPES:
            action_events.append(event)
    return action_events


def peerlist_follow_workflow_metrics(report: Any) -> dict[str, Any]:
    data = _report_to_dict(report)
    actions = data.get("actions")
    skipped = data.get("skipped")
    blockers = data.get("blockers")
    workflow_parameters = data.get("workflow_parameters")
    if not isinstance(actions, list):
        actions = []
    if not isinstance(skipped, list):
        skipped = []
    if not isinstance(blockers, list):
        blockers = []
    if not isinstance(workflow_parameters, dict):
        workflow_parameters = {}

    follows_count = int(
        data.get(
            "follows_count",
            sum(
                1
                for action in actions
                if isinstance(action, dict)
                and action.get("type") in {"follow", "peerlist_profile_followed"}
                and bool(action.get("verified", True))
            ),
        )
    )
    unfollows_count = int(
        data.get(
            "unfollows_count",
            sum(
                1
                for action in actions
                if isinstance(action, dict)
                and action.get("type") in {"unfollow", "peerlist_profile_unfollowed"}
                and bool(action.get("verified", True))
            ),
        )
    )
    peers_preserved_count = int(
        data.get(
            "peers_preserved_count",
            sum(
                1
                for item in skipped
                if isinstance(item, dict) and item.get("reason") in {"peer_preserved", "is_peer"}
            ),
        )
    )
    followers_before = data.get("peerlist_profile_followers_before")
    followers_after = data.get("peerlist_profile_followers_after")
    followers_delta = data.get("peerlist_profile_followers_delta")
    if followers_delta is None and followers_before is not None and followers_after is not None:
        followers_delta = int(followers_after) - int(followers_before)

    profiles_scanned = int(data.get("profiles_scanned", data.get("items_scanned", 0)))
    profiles_considered = int(data.get("profiles_considered", data.get("items_considered", profiles_scanned)))
    action_total = follows_count + unfollows_count

    return {
        "page_shape_ok": data.get("page_shape_ok"),
        "actor_verified": bool(data.get("actor_verified", False)),
        "search_shape_ok": data.get("search_shape_ok"),
        "challenge_detected": bool(data.get("has_challenge", False)) or data.get("stop_reason") == "challenge_detected",
        "items_scanned": profiles_scanned,
        "items_considered": profiles_considered,
        "actions_total": action_total,
        "likes_count": 0,
        "reposts_count": 0,
        "comments_liked_count": 0,
        "follows_count": follows_count,
        "metrics_json": {
            "north_star_metric": "peerlist_profile_followers",
            "peerlist_profile_followers_before": followers_before,
            "peerlist_profile_followers_after": followers_after,
            "peerlist_profile_followers_delta": followers_delta,
            "workflow_type": data.get("workflow_type") or workflow_parameters.get("type"),
            "automation_kind": "workflow",
            "workflow_parameters": workflow_parameters,
            "automation_parameters": workflow_parameters,
            "profiles_scanned": profiles_scanned,
            "profiles_considered": profiles_considered,
            "follows_count": follows_count,
            "unfollows_count": unfollows_count,
            "peers_preserved_count": peers_preserved_count,
            "skipped_count": len(skipped),
            "blockers_count": len(blockers),
        },
    }


def linkedin_company_profile_engagement_metrics(report: Any) -> dict[str, Any]:
    data = _report_to_dict(report)
    companies_scanned = int(data.get("companies_scanned", data.get("agencies_scanned", 0)))
    companies_followed = int(data.get("companies_followed", data.get("agencies_followed", 0)))
    return {
        "page_shape_ok": None,
        "actor_verified": bool(data.get("actor_verified", False)),
        "search_shape_ok": bool(data.get("search_shape_ok", False)),
        "challenge_detected": data.get("stop_reason") == "anti_automation_challenge",
        "items_scanned": int(data.get("posts_scanned", 0)),
        "items_considered": int(data.get("posts_liked", 0)) + int(data.get("posts_reposted", 0)) + int(data.get("comments_liked", 0)) + companies_followed,
        "actions_total": int(data.get("posts_liked", 0)) + int(data.get("posts_reposted", 0)) + int(data.get("comments_liked", 0)) + companies_followed,
        "likes_count": int(data.get("posts_liked", 0)),
        "reposts_count": int(data.get("posts_reposted", 0)),
        "comments_liked_count": int(data.get("comments_liked", 0)),
        "follows_count": companies_followed,
        "companies_scanned": companies_scanned,
        "companies_followed": companies_followed,
        "metrics_json": {
            "posts_scanned": int(data.get("posts_scanned", 0)),
            "posts_liked": int(data.get("posts_liked", 0)),
            "posts_reposted": int(data.get("posts_reposted", 0)),
            "comments_liked": int(data.get("comments_liked", 0)),
            "companies_scanned": companies_scanned,
            "companies_followed": companies_followed,
            "agencies_scanned": companies_scanned,
            "agencies_followed": companies_followed,
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


def peerlist_scroll_engagement_metrics(report: Any) -> dict[str, Any]:
    data = _report_to_dict(report)
    actions = data.get("actions")
    skipped = data.get("skipped")
    blockers = data.get("blockers")
    if not isinstance(actions, list):
        actions = []
    if not isinstance(skipped, list):
        skipped = []
    if not isinstance(blockers, list):
        blockers = []

    upvotes_count = int(
        data.get(
            "upvotes_count",
            sum(
                1
                for action in actions
                if isinstance(action, dict)
                and action.get("type") in {"upvote", "peerlist_post_upvoted"}
                and bool(action.get("verified", True))
            ),
        )
    )
    comments_count = int(data.get("comments_count", 0))
    follows_count = int(data.get("follows_count", 0))
    items_scanned = int(data.get("items_scanned", data.get("upvote_buttons_seen", 0)))
    items_considered = int(data.get("items_considered", max(items_scanned, upvotes_count)))
    action_total = upvotes_count + comments_count + follows_count

    return {
        "page_shape_ok": data.get("page_shape_ok"),
        "actor_verified": bool(data.get("actor_verified", False)),
        "search_shape_ok": None,
        "challenge_detected": bool(data.get("has_challenge", False)) or data.get("stop_reason") == "challenge_detected",
        "items_scanned": items_scanned,
        "items_considered": items_considered,
        "actions_total": action_total,
        "likes_count": upvotes_count,
        "reposts_count": 0,
        "comments_liked_count": 0,
        "follows_count": follows_count,
        "metrics_json": {
            "upvotes_count": upvotes_count,
            "comments_count": comments_count,
            "follows_count": follows_count,
            "skipped_count": len(skipped),
            "blockers_count": len(blockers),
            "browser_profile": data.get("browser_profile"),
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

    report_dict = normalize_report_payload(report)
    canonical_name = canonical_automation_name(automation_name)
    workspace_slug = report_dict.get("workspace_slug")
    received_at = report_dict.get("received_at")
    profile_name = report_dict.get("profile_name") or report_dict.get("actor_name")
    action_events = action_events_from_report(report_dict)
    companies_scanned = int(metrics.get("companies_scanned", 0))
    companies_followed = int(metrics.get("companies_followed", 0))
    with psycopg.connect(database_url) as conn:
        with conn.cursor() as cur:
            cur.execute(ANALYTICS_POSTGRES_TABLE_SCHEMA)
            cur.execute("ALTER TABLE automation_runs ADD COLUMN IF NOT EXISTS automation_label TEXT")
            cur.execute("ALTER TABLE automation_runs ADD COLUMN IF NOT EXISTS surface TEXT")
            cur.execute("ALTER TABLE automation_runs ADD COLUMN IF NOT EXISTS workspace_slug TEXT")
            cur.execute("ALTER TABLE automation_runs ADD COLUMN IF NOT EXISTS received_at TEXT")
            cur.execute("ALTER TABLE automation_runs ADD COLUMN IF NOT EXISTS profile_name TEXT")
            cur.execute("ALTER TABLE automation_runs ADD COLUMN IF NOT EXISTS companies_scanned INTEGER NOT NULL DEFAULT 0")
            cur.execute("ALTER TABLE automation_runs ADD COLUMN IF NOT EXISTS companies_followed INTEGER NOT NULL DEFAULT 0")
            cur.execute("ALTER TABLE automation_runs ADD COLUMN IF NOT EXISTS action_events_json JSONB NOT NULL DEFAULT '[]'::jsonb")
            cur.execute(ANALYTICS_POSTGRES_VIEW_SCHEMA)
            cur.execute(ANALYTICS_POSTGRES_ACTION_EVENTS_VIEW_SCHEMA)
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
                  automation_name, automation_label, platform, surface, workspace_slug, received_at, profile_name, companies_scanned, companies_followed, run_id, started_at, finished_at, status, stop_reason,
                  search_url, artifact_path, screenshot_path, page_shape_ok, actor_verified, search_shape_ok,
                  challenge_detected, items_scanned, items_considered, actions_total, likes_count,
                  reposts_count, comments_liked_count, follows_count, metrics_json, action_events_json, report_json
                )
                VALUES (
                  %(automation_name)s, %(automation_label)s, %(platform)s, %(surface)s, %(workspace_slug)s, %(received_at)s, %(profile_name)s, %(companies_scanned)s, %(companies_followed)s, %(run_id)s, %(started_at)s, %(finished_at)s, %(status)s, %(stop_reason)s,
                  %(search_url)s, %(artifact_path)s, %(screenshot_path)s, %(page_shape_ok)s, %(actor_verified)s, %(search_shape_ok)s,
                  %(challenge_detected)s, %(items_scanned)s, %(items_considered)s, %(actions_total)s, %(likes_count)s,
                  %(reposts_count)s, %(comments_liked_count)s, %(follows_count)s, %(metrics_json)s::jsonb, %(action_events_json)s::jsonb, %(report_json)s::jsonb
                )
                ON CONFLICT (automation_name, run_id) DO UPDATE SET
                  automation_label = EXCLUDED.automation_label,
                  platform = EXCLUDED.platform,
                  surface = EXCLUDED.surface,
                  workspace_slug = EXCLUDED.workspace_slug,
                  received_at = EXCLUDED.received_at,
                  profile_name = EXCLUDED.profile_name,
                  companies_scanned = EXCLUDED.companies_scanned,
                  companies_followed = EXCLUDED.companies_followed,
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
                  action_events_json = EXCLUDED.action_events_json,
                  report_json = EXCLUDED.report_json
                """,
                {
                    "automation_name": canonical_name,
                    "automation_label": automation_label(canonical_name),
                    "platform": platform,
                    "surface": surface or automation_surface(canonical_name),
                    "workspace_slug": workspace_slug,
                    "received_at": received_at,
                    "profile_name": profile_name,
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
                    "companies_scanned": companies_scanned,
                    "companies_followed": companies_followed,
                    "metrics_json": json.dumps(metrics.get("metrics_json", {}), sort_keys=True),
                    "action_events_json": json.dumps(action_events, sort_keys=True),
                    "report_json": json.dumps(report_dict, sort_keys=True),
                },
            )
        conn.commit()
