#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

PACKAGE_ROOT = Path(__file__).resolve().parent.parent
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

from automation_analytics import (
    NORTH_STAR_DAILY_METRICS_TABLE_SCHEMA,
    NORTH_STAR_DAILY_METRICS_VIEW_SCHEMA,
    upsert_automation_run,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Sync a PhantomClaw run bundle into Neon analytics storage")
    parser.add_argument("--bundle-path", type=Path, required=True)
    parser.add_argument("--database-url", default=os.getenv("AUTOMATION_ANALYTICS_DATABASE_URL") or os.getenv("DATABASE_URL"))
    parser.add_argument("--workspace-slug", default=os.getenv("PHANTOMCLAW_WORKSPACE_SLUG") or os.getenv("PHANTOMCLAW_WORKSPACE"))
    parser.add_argument("--received-at", default=datetime.now(UTC).isoformat())
    return parser


def _load_bundle(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text())
    if not isinstance(payload, dict):
        raise SystemExit("Run bundle must be a JSON object")
    for field in ("automation", "run", "metrics", "report"):
        if not isinstance(payload.get(field), dict):
            raise SystemExit(f"Run bundle is missing object field: {field}")
    return payload


def _date_from_iso(raw: Any, fallback: str) -> str:
    if not raw:
        raw = fallback
    try:
        return datetime.fromisoformat(str(raw).replace("Z", "+00:00")).date().isoformat()
    except ValueError:
        return datetime.now(UTC).date().isoformat()


def _insert_metric_snapshot(
    *,
    database_url: str,
    bundle: dict[str, Any],
    report: dict[str, Any],
    received_at: str,
    metric_name: str,
) -> bool:
    automation = bundle["automation"]
    if not metric_name:
        return False

    metrics_json = bundle["metrics"].get("metrics_json")
    if not isinstance(metrics_json, dict):
        return False
    metric_value = metrics_json.get(f"{metric_name}_after")
    if metric_value is None:
        metric_value = metrics_json.get(metric_name)
    if metric_value is None:
        return False

    profile_name = bundle["run"].get("profile_name") or report.get("profile_name")
    if not profile_name:
        return False

    import psycopg

    with psycopg.connect(database_url) as conn:
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
                    report.get("workspace_slug"),
                    automation["platform"],
                    profile_name,
                    metric_name,
                    _date_from_iso(bundle["run"].get("finished_at") or bundle["run"].get("started_at"), received_at),
                    metric_value,
                    "workflow",
                    received_at,
                    bundle["run"]["run_id"],
                    json.dumps(
                        {
                            "automation_name": automation["name"],
                            "workflow_type": metrics_json.get("workflow_type"),
                            "source_bundle_path": str(bundle.get("source", {}).get("artifact_path") or ""),
                        },
                        sort_keys=True,
                    ),
                ),
            )
        conn.commit()
    return True


def _insert_metric_snapshots(
    *,
    database_url: str,
    bundle: dict[str, Any],
    report: dict[str, Any],
    received_at: str,
) -> list[str]:
    automation = bundle["automation"]
    metrics_json = bundle["metrics"].get("metrics_json")
    if not isinstance(metrics_json, dict):
        return []
    metric_names = []
    north_star = automation.get("north_star_metric")
    if isinstance(north_star, str) and north_star:
        metric_names.append(north_star)
    if metrics_json.get("peerlist_profile_following_after") is not None:
        metric_names.append("peerlist_profile_following")

    inserted: list[str] = []
    for metric_name in dict.fromkeys(metric_names):
        if _insert_metric_snapshot(
            database_url=database_url,
            bundle=bundle,
            report=report,
            received_at=received_at,
            metric_name=metric_name,
        ):
            inserted.append(metric_name)
    return inserted


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.database_url:
        parser.error("AUTOMATION_ANALYTICS_DATABASE_URL, DATABASE_URL, or --database-url is required")

    bundle = _load_bundle(args.bundle_path)
    automation = bundle["automation"]
    source = bundle.get("source") if isinstance(bundle.get("source"), dict) else {}
    report = dict(bundle["report"])
    if args.workspace_slug and not report.get("workspace_slug"):
        report["workspace_slug"] = args.workspace_slug
    if args.received_at and not report.get("received_at"):
        report["received_at"] = args.received_at

    upsert_automation_run(
        database_url=args.database_url,
        automation_name=automation["name"],
        platform=automation["platform"],
        surface=automation.get("surface"),
        search_url=source.get("search_url") or "",
        artifact_path=source.get("artifact_path") or str(args.bundle_path),
        report=report,
        metrics=bundle["metrics"],
    )
    daily_metrics_synced = _insert_metric_snapshots(
        database_url=args.database_url,
        bundle=bundle,
        report=report,
        received_at=args.received_at,
    )

    print(
        json.dumps(
            {
                "synced": True,
                "daily_metric_synced": bool(daily_metrics_synced),
                "daily_metrics_synced": daily_metrics_synced,
                "automation_name": automation["name"],
                "run_id": bundle["run"]["run_id"],
                "workspace_slug": report.get("workspace_slug"),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
