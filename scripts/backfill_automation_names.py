from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
import sqlite3

PACKAGE_ROOT = Path(__file__).resolve().parent.parent
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

import psycopg
from automation_analytics import (
    ANALYTICS_POSTGRES_ACTION_EVENTS_VIEW_SCHEMA,
    ANALYTICS_POSTGRES_TABLE_SCHEMA,
    ANALYTICS_POSTGRES_VIEW_SCHEMA,
    action_events_from_report,
    linkedin_company_profile_engagement_metrics,
    linkedin_sales_community_metrics,
    normalize_report_payload,
)


POSTGRES_SQL = """
ALTER TABLE automation_runs ADD COLUMN IF NOT EXISTS automation_label TEXT;
ALTER TABLE automation_runs ADD COLUMN IF NOT EXISTS surface TEXT;
ALTER TABLE automation_runs ADD COLUMN IF NOT EXISTS profile_name TEXT;
ALTER TABLE automation_runs ADD COLUMN IF NOT EXISTS companies_scanned INTEGER NOT NULL DEFAULT 0;
ALTER TABLE automation_runs ADD COLUMN IF NOT EXISTS companies_followed INTEGER NOT NULL DEFAULT 0;
ALTER TABLE automation_runs ADD COLUMN IF NOT EXISTS action_events_json JSONB NOT NULL DEFAULT '[]'::jsonb;

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
WHERE automation_name IN (
  'trustoutreach-linkedin',
  'linkedin-sales-community',
  'linkedin-company-profile-engagement',
  'linkedin-sales-community-engagement'
);
"""

SQLITE_SQL = """
UPDATE automation_runs
SET automation_name = CASE automation_name
  WHEN 'trustoutreach-linkedin' THEN 'linkedin-company-profile-engagement'
  WHEN 'linkedin-sales-community' THEN 'linkedin-sales-community-engagement'
  ELSE automation_name
END
WHERE automation_name IN ('trustoutreach-linkedin', 'linkedin-sales-community');
"""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Backfill generic automation names into analytics storage")
    parser.add_argument("--database-url")
    parser.add_argument("--sqlite-path", type=Path)
    args = parser.parse_args(argv)

    if bool(args.database_url) == bool(args.sqlite_path):
        raise SystemExit("Provide exactly one of --database-url or --sqlite-path")

    if args.database_url:
        with psycopg.connect(args.database_url) as conn:
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
                cur.execute(POSTGRES_SQL)
                cur.execute("SELECT automation_name, run_id, profile_name, stop_reason, report_json, action_events_json, metrics_json FROM automation_runs")
                for automation_name, run_id, profile_name, stop_reason, report_json, action_events_json, metrics_json in cur.fetchall():
                    report_dict = report_json if isinstance(report_json, dict) else json.loads(report_json)
                    normalized_report = normalize_report_payload(report_dict)
                    new_profile_name = (
                        profile_name
                        or normalized_report.get("profile_name")
                        or normalized_report.get("actor_name")
                        or ("TrustOutreach" if automation_name == "linkedin-company-profile-engagement" else None)
                    )
                    new_action_events = action_events_from_report(normalized_report)
                    if automation_name == "linkedin-company-profile-engagement":
                        new_metrics = linkedin_company_profile_engagement_metrics(normalized_report)
                    elif automation_name == "linkedin-sales-community-engagement":
                        new_metrics = linkedin_sales_community_metrics(normalized_report)
                    else:
                        new_metrics = None
                    new_metrics_json = new_metrics.get("metrics_json", {}) if new_metrics else {}
                    new_companies_scanned = int(new_metrics.get("companies_scanned", 0)) if new_metrics else 0
                    new_companies_followed = int(new_metrics.get("companies_followed", 0)) if new_metrics else 0
                    current_action_events = action_events_json if isinstance(action_events_json, list) else json.loads(action_events_json or "[]")
                    current_metrics_json = metrics_json if isinstance(metrics_json, dict) else json.loads(metrics_json or "{}")
                    if (
                        new_profile_name != profile_name
                        or normalized_report.get("stop_reason") != stop_reason
                        or current_action_events != new_action_events
                        or current_metrics_json != new_metrics_json
                        or int(current_metrics_json.get("companies_scanned", 0)) != new_companies_scanned
                        or int(current_metrics_json.get("companies_followed", 0)) != new_companies_followed
                        or normalized_report != report_dict
                    ):
                        cur.execute(
                            """
                            UPDATE automation_runs
                            SET profile_name = %s,
                                companies_scanned = %s,
                                companies_followed = %s,
                                stop_reason = %s,
                                metrics_json = %s::jsonb,
                                action_events_json = %s::jsonb,
                                report_json = %s::jsonb
                            WHERE automation_name = %s
                              AND run_id = %s
                            """,
                            (
                                new_profile_name,
                                new_companies_scanned,
                                new_companies_followed,
                                normalized_report.get("stop_reason"),
                                json.dumps(new_metrics_json, sort_keys=True),
                                json.dumps(new_action_events, sort_keys=True),
                                json.dumps(normalized_report, sort_keys=True),
                                automation_name,
                                run_id,
                            ),
                        )
            conn.commit()
        print("Backfilled Postgres automation names, surfaces, profiles, company events, and drilldown columns")
        return 0

    with sqlite3.connect(args.sqlite_path) as conn:
        conn.execute(SQLITE_SQL)
        conn.commit()
    print(f"Backfilled SQLite automation names in {args.sqlite_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
