#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parent.parent
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

from automation_analytics import NORTH_STAR_DAILY_METRICS_TABLE_SCHEMA, NORTH_STAR_DAILY_METRICS_VIEW_SCHEMA


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Insert an append-only north-star metric snapshot")
    parser.add_argument("--database-url", default=os.getenv("AUTOMATION_ANALYTICS_DATABASE_URL"))
    parser.add_argument("--workspace-slug", default=os.getenv("PHANTOMCLAW_WORKSPACE_SLUG"))
    parser.add_argument("--platform", required=True)
    parser.add_argument("--profile-name", required=True)
    parser.add_argument("--metric-name", required=True)
    parser.add_argument("--metric-date", default=date.today().isoformat())
    parser.add_argument("--metric-value", required=True)
    parser.add_argument("--source", default="cron")
    parser.add_argument("--captured-at", default=datetime.now(UTC).isoformat())
    parser.add_argument("--run-id")
    parser.add_argument("--metadata-json", default="{}")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.database_url:
        parser.error("AUTOMATION_ANALYTICS_DATABASE_URL or --database-url is required")

    try:
        metadata = json.loads(args.metadata_json)
    except json.JSONDecodeError as exc:
        parser.error(f"--metadata-json must be valid JSON: {exc}")
    if not isinstance(metadata, dict):
        parser.error("--metadata-json must be a JSON object")

    import psycopg

    with psycopg.connect(args.database_url) as conn:
        with conn.cursor() as cur:
            cur.execute(NORTH_STAR_DAILY_METRICS_TABLE_SCHEMA)
            cur.execute(NORTH_STAR_DAILY_METRICS_VIEW_SCHEMA)
            cur.execute(
                """
                INSERT INTO automation_daily_metrics (
                  workspace_slug, platform, profile_name, metric_name, metric_date, metric_value,
                  source, captured_at, run_id, metadata_json
                )
                VALUES (%s, %s, %s, %s, %s::date, %s, %s, %s, %s, %s::jsonb)
                """,
                (
                    args.workspace_slug,
                    args.platform,
                    args.profile_name,
                    args.metric_name,
                    args.metric_date,
                    Decimal(str(args.metric_value)),
                    args.source,
                    args.captured_at,
                    args.run_id,
                    json.dumps(metadata, sort_keys=True),
                ),
            )
        conn.commit()

    print(
        json.dumps(
            {
                "inserted": True,
                "platform": args.platform,
                "profile_name": args.profile_name,
                "metric_name": args.metric_name,
                "metric_date": args.metric_date,
                "metric_value": str(args.metric_value),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
