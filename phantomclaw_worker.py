from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from automation_catalog import automation_default_parameters, canonical_automation_name


WORKER_SCHEMA = """
CREATE TABLE IF NOT EXISTS phantomclaw_automations (
  workspace_slug TEXT NOT NULL,
  automation_id TEXT NOT NULL,
  automation_name TEXT NOT NULL,
  status TEXT NOT NULL,
  source_status TEXT,
  timezone TEXT NOT NULL DEFAULT 'Europe/Berlin',
  rrule TEXT NOT NULL DEFAULT '',
  platform TEXT NOT NULL DEFAULT 'phantomclaw',
  surface TEXT,
  runner_status TEXT,
  runner_dispatch TEXT,
  runner_command JSONB NOT NULL DEFAULT '[]'::jsonb,
  runner_dry_run_command JSONB NOT NULL DEFAULT '[]'::jsonb,
  parameters_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (workspace_slug, automation_id)
);

CREATE TABLE IF NOT EXISTS phantomclaw_dispatches (
  workspace_slug TEXT NOT NULL,
  automation_id TEXT NOT NULL,
  occurrence_key TEXT NOT NULL,
  run_id TEXT,
  status TEXT NOT NULL DEFAULT 'claimed',
  claimed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  finished_at TIMESTAMPTZ,
  result_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  PRIMARY KEY (workspace_slug, automation_id, occurrence_key)
);

CREATE INDEX IF NOT EXISTS phantomclaw_automations_active_idx
  ON phantomclaw_automations (workspace_slug, status, automation_id);

CREATE INDEX IF NOT EXISTS phantomclaw_dispatches_status_idx
  ON phantomclaw_dispatches (workspace_slug, status, claimed_at);

ALTER TABLE phantomclaw_automations ADD COLUMN IF NOT EXISTS runner_dry_run_command JSONB NOT NULL DEFAULT '[]'::jsonb;
"""

DAY_CODES = ["MO", "TU", "WE", "TH", "FR", "SA", "SU"]
STALE_CLAIMED_MINUTES = 30


@dataclass(frozen=True)
class DueAutomation:
    workspace_slug: str
    automation_id: str
    automation_name: str
    timezone: str
    rrule: str
    platform: str
    surface: str | None
    runner_status: str | None
    runner_dispatch: str | None
    runner_command: list[str]
    runner_dry_run_command: list[str]
    parameters: dict[str, Any]
    metadata: dict[str, Any]
    occurrence_key: str


def default_database_url() -> str | None:
    return os.getenv("PHANTOMCLAW_DATABASE_URL") or os.getenv("AUTOMATION_ANALYTICS_DATABASE_URL") or os.getenv("DATABASE_URL")


def default_workspace_slug() -> str:
    return os.getenv("PHANTOMCLAW_WORKSPACE_SLUG") or os.getenv("PHANTOMCLAW_WORKSPACE") or "default"


def parse_rrule(rrule: str) -> dict[str, str]:
    parts: dict[str, str] = {}
    for part in (rrule or "").split(";"):
        if "=" not in part:
            continue
        key, value = part.split("=", 1)
        parts[key.upper()] = value
    return parts


def int_values(value: str | None, default: list[int]) -> list[int]:
    if not value:
        return default
    values: list[int] = []
    for item in value.split(","):
        try:
            values.append(int(item))
        except ValueError:
            continue
    return values or default


def day_allowed(parts: dict[str, str], now: datetime) -> bool:
    byday = parts.get("BYDAY")
    if not byday:
        return True
    allowed = {day.strip().upper() for day in byday.split(",") if day.strip()}
    return DAY_CODES[now.weekday()] in allowed


def due_occurrence_key(automation_id: str, rrule: str, now: datetime) -> str | None:
    parts = parse_rrule(rrule)
    freq = parts.get("FREQ", "").upper()
    if not freq or not day_allowed(parts, now):
        return None

    minutes = int_values(parts.get("BYMINUTE"), [0])
    if now.minute not in minutes:
        return None

    if freq == "HOURLY":
        interval = int_values(parts.get("INTERVAL"), [1])[0]
        if interval <= 0:
            interval = 1
        byhour = parts.get("BYHOUR")
        if byhour:
            hours = set(int_values(byhour, []))
            if now.hour not in hours:
                return None
        elif now.hour % interval != 0:
            return None
        return f"{automation_id}:{now.strftime('%Y-%m-%dT%H')}:{now.minute:02d}"

    if freq in {"WEEKLY", "DAILY"}:
        hours = int_values(parts.get("BYHOUR"), [0])
        if now.hour not in hours:
            return None
        if freq == "WEEKLY":
            return f"{automation_id}:{DAY_CODES[now.weekday()]}:{now.strftime('%Y-%m-%d')}:{now.hour:02d}:{now.minute:02d}"
        return f"{automation_id}:{now.strftime('%Y-%m-%d')}:{now.hour:02d}:{now.minute:02d}"

    return None


def recent_expected_occurrences(
    automation_id: str,
    rrule: str,
    *,
    now: datetime,
    timezone_name: str,
    lookback_hours: int,
) -> list[str]:
    tz = ZoneInfo(timezone_name or "Europe/Berlin")
    local_now = now.astimezone(tz).replace(second=0, microsecond=0)
    lookback_minutes = max(0, int(lookback_hours) * 60)
    occurrences: list[str] = []
    for offset in range(lookback_minutes, -1, -1):
        candidate = local_now - timedelta(minutes=offset)
        occurrence = due_occurrence_key(automation_id, rrule, candidate)
        if occurrence:
            occurrences.append(occurrence)
    return occurrences


def recent_due_occurrences(
    automation_id: str,
    rrule: str,
    *,
    now: datetime,
    catchup_minutes: int,
) -> list[str]:
    local_now = now.replace(second=0, microsecond=0)
    occurrences: list[str] = []
    for offset in range(max(0, int(catchup_minutes)), -1, -1):
        occurrence = due_occurrence_key(automation_id, rrule, local_now - timedelta(minutes=offset))
        if occurrence and occurrence not in occurrences:
            occurrences.append(occurrence)
    return occurrences


def connect(database_url: str):
    import psycopg

    return psycopg.connect(database_url)


def ensure_worker_schema(database_url: str) -> None:
    with connect(database_url) as conn:
        with conn.cursor() as cur:
            cur.execute(WORKER_SCHEMA)
        conn.commit()


def registry_entry_parameters(entry: dict[str, Any]) -> dict[str, Any]:
    automation_id = canonical_automation_name(str(entry.get("id") or ""))
    parameters = automation_default_parameters(automation_id)
    explicit = entry.get("parameters")
    if isinstance(explicit, dict):
        parameters.update(explicit)
    return parameters


def sync_registry_to_neon(
    *,
    database_url: str,
    registry_path: Path,
    workspace_slug: str,
    activate_only_runnable: bool = True,
) -> dict[str, Any]:
    registry = json.loads(registry_path.read_text())
    automations = registry.get("automations")
    if not isinstance(automations, list):
        raise ValueError("registry.automations must be a list")

    ensure_worker_schema(database_url)
    upserted: list[str] = []
    with connect(database_url) as conn:
        with conn.cursor() as cur:
            for entry in automations:
                if not isinstance(entry, dict):
                    continue
                runner = entry.get("runner") if isinstance(entry.get("runner"), dict) else {}
                runner_status = runner.get("status")
                status = str(entry.get("status") or "PAUSED")
                runner_command = runner.get("command") if isinstance(runner.get("command"), list) else []
                runner_runnable = (
                    runner_status in {"native", "native_candidate"}
                    and runner.get("dispatch") in {"phantomclaw_native", "openclaw_railway_host_command"}
                    and all(isinstance(item, str) and item for item in runner_command)
                )
                if activate_only_runnable and status == "ACTIVE" and not runner_runnable:
                    status = "PAUSED"
                automation_id = str(entry["id"])
                cur.execute(
                    """
                    INSERT INTO phantomclaw_automations (
                      workspace_slug, automation_id, automation_name, status, source_status,
                      timezone, rrule, platform, surface, runner_status, runner_dispatch,
                      runner_command, runner_dry_run_command, parameters_json, metadata_json, updated_at
                    )
                    VALUES (
                      %s, %s, %s, %s, %s,
                      %s, %s, %s, %s, %s, %s,
                      %s::jsonb, %s::jsonb, %s::jsonb, %s::jsonb, now()
                    )
                    ON CONFLICT (workspace_slug, automation_id) DO UPDATE SET
                      automation_name = EXCLUDED.automation_name,
                      status = EXCLUDED.status,
                      source_status = EXCLUDED.source_status,
                      timezone = EXCLUDED.timezone,
                      rrule = EXCLUDED.rrule,
                      platform = EXCLUDED.platform,
                      surface = EXCLUDED.surface,
                      runner_status = EXCLUDED.runner_status,
                      runner_dispatch = EXCLUDED.runner_dispatch,
                      runner_command = EXCLUDED.runner_command,
                      runner_dry_run_command = EXCLUDED.runner_dry_run_command,
                      parameters_json = EXCLUDED.parameters_json,
                      metadata_json = EXCLUDED.metadata_json,
                      updated_at = now()
                    """,
                    (
                        workspace_slug,
                        automation_id,
                        str(entry.get("name") or automation_id),
                        status,
                        entry.get("source_status"),
                        str(entry.get("timezone") or "Europe/Berlin"),
                        str(entry.get("rrule") or ""),
                        str(entry.get("platform") or "phantomclaw"),
                        entry.get("surface"),
                        runner_status,
                        runner.get("dispatch"),
                        json.dumps(runner_command),
                        json.dumps(runner.get("dry_run_command") if isinstance(runner.get("dry_run_command"), list) else []),
                        json.dumps(registry_entry_parameters(entry), sort_keys=True),
                        json.dumps(
                            {
                                "cwds": entry.get("cwds"),
                                "source": entry.get("source"),
                                "processing_system": entry.get("processing_system"),
                                "codex_processing_enabled": entry.get("codex_processing_enabled"),
                            },
                            sort_keys=True,
                        ),
                    ),
                )
                upserted.append(automation_id)
        conn.commit()
    return {"synced": True, "workspace_slug": workspace_slug, "upserted_count": len(upserted), "automation_ids": upserted}


def json_object(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value:
        parsed = json.loads(value)
        return parsed if isinstance(parsed, dict) else {}
    return {}


def json_array(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value]
    if isinstance(value, str) and value:
        parsed = json.loads(value)
        if isinstance(parsed, list):
            return [str(item) for item in parsed]
    return []


def default_due_catchup_minutes() -> int:
    raw = os.getenv("PHANTOMCLAW_DUE_CATCHUP_MINUTES", "3").strip()
    try:
        return max(0, int(raw))
    except ValueError:
        return 3


def load_due_automations(
    database_url: str,
    *,
    workspace_slug: str,
    now: datetime,
    catchup_minutes: int | None = None,
) -> list[DueAutomation]:
    ensure_worker_schema(database_url)
    rows: list[Any]
    with connect(database_url) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                  workspace_slug, automation_id, automation_name, timezone, rrule,
                  platform, surface, runner_status, runner_dispatch, runner_command,
                  runner_dry_run_command, parameters_json, metadata_json
                FROM phantomclaw_automations
                WHERE workspace_slug = %s
                  AND status = 'ACTIVE'
                ORDER BY automation_id
                """,
                (workspace_slug,),
            )
            rows = cur.fetchall()

    resolved_catchup_minutes = default_due_catchup_minutes() if catchup_minutes is None else max(0, int(catchup_minutes))
    candidates: list[tuple[Any, str]] = []
    due: list[DueAutomation] = []
    active_rows_by_id = {str(row[1]): row for row in rows}
    for row in rows:
        tz = ZoneInfo(row[3] or "Europe/Berlin")
        local_now = now.astimezone(tz)
        for occurrence in recent_due_occurrences(
            row[1],
            row[4],
            now=local_now,
            catchup_minutes=resolved_catchup_minutes,
        ):
            candidates.append((row, occurrence))

    stale_claimed_before = now.astimezone(UTC) - timedelta(minutes=STALE_CLAIMED_MINUTES)
    with connect(database_url) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT automation_id, occurrence_key
                FROM phantomclaw_dispatches
                WHERE workspace_slug = %s
                  AND status = 'claimed'
                  AND finished_at IS NULL
                  AND claimed_at < %s
                ORDER BY claimed_at ASC
                LIMIT 50
                """,
                (workspace_slug, stale_claimed_before),
            )
            stale_claimed_rows = cur.fetchall()

    seen_candidate_occurrences = {occurrence for _, occurrence in candidates}
    for automation_id, occurrence in stale_claimed_rows:
        row = active_rows_by_id.get(str(automation_id))
        occurrence_key = str(occurrence)
        if row is None or occurrence_key in seen_candidate_occurrences:
            continue
        candidates.append((row, occurrence_key))
        seen_candidate_occurrences.add(occurrence_key)

    if not candidates:
        return due

    occurrence_keys = [occurrence for _, occurrence in candidates]
    with connect(database_url) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT occurrence_key, status, claimed_at, finished_at
                FROM phantomclaw_dispatches
                WHERE workspace_slug = %s
                  AND occurrence_key = ANY(%s)
                """,
                (workspace_slug, occurrence_keys),
            )
            dispatch_rows = cur.fetchall()

    existing_occurrences: set[str] = set()
    reclaimable_occurrences: set[str] = set()
    for dispatch in dispatch_rows:
        occurrence_key = str(dispatch[0])
        existing_occurrences.add(occurrence_key)
        claimed_at = dispatch[2]
        if hasattr(claimed_at, "astimezone"):
            claimed_at_utc = claimed_at.astimezone(UTC)
        else:
            claimed_at_utc = now.astimezone(UTC)
        if str(dispatch[1]) == "claimed" and dispatch[3] is None and claimed_at_utc < stale_claimed_before:
            reclaimable_occurrences.add(occurrence_key)

    for row, occurrence in candidates:
        if occurrence in existing_occurrences and occurrence not in reclaimable_occurrences:
            continue
        due.append(
            DueAutomation(
                workspace_slug=row[0],
                automation_id=row[1],
                automation_name=row[2],
                timezone=row[3],
                rrule=row[4],
                platform=row[5],
                surface=row[6],
                runner_status=row[7],
                runner_dispatch=row[8],
                runner_command=json_array(row[9]),
                runner_dry_run_command=json_array(row[10]),
                parameters=json_object(row[11]),
                metadata=json_object(row[12]),
                occurrence_key=occurrence,
            )
        )
    return due


def worker_status(
    *,
    database_url: str,
    workspace_slug: str,
    now: datetime | None = None,
    lookback_hours: int = 24,
) -> dict[str, Any]:
    resolved_now = now or datetime.now(UTC)
    ensure_worker_schema(database_url)
    active_rows: list[Any]
    dispatch_rows: list[Any]
    window_start = resolved_now.astimezone(UTC) - timedelta(hours=max(1, lookback_hours))
    stale_claimed_before = resolved_now.astimezone(UTC) - timedelta(minutes=STALE_CLAIMED_MINUTES)
    with connect(database_url) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT automation_id, automation_name, timezone, rrule, parameters_json
                FROM phantomclaw_automations
                WHERE workspace_slug = %s
                  AND status = 'ACTIVE'
                ORDER BY automation_id
                """,
                (workspace_slug,),
            )
            active_rows = cur.fetchall()
            cur.execute(
                """
                SELECT automation_id, occurrence_key, status, run_id, claimed_at, finished_at, result_json
                FROM phantomclaw_dispatches
                WHERE workspace_slug = %s
                  AND claimed_at >= %s
                ORDER BY claimed_at DESC
                LIMIT 100
                """,
                (workspace_slug, window_start),
            )
            dispatch_rows = cur.fetchall()

    dispatches_by_occurrence = {str(row[1]): row for row in dispatch_rows}
    automations: list[dict[str, Any]] = []
    missing_occurrences: list[dict[str, str]] = []
    for row in active_rows:
        automation_id = str(row[0])
        timezone_name = str(row[2] or "Europe/Berlin")
        expected = recent_expected_occurrences(
            automation_id,
            str(row[3] or ""),
            now=resolved_now,
            timezone_name=timezone_name,
            lookback_hours=lookback_hours,
        )
        missing = [occurrence for occurrence in expected if occurrence not in dispatches_by_occurrence]
        for occurrence in missing:
            missing_occurrences.append({"automation_id": automation_id, "occurrence_key": occurrence})
        automations.append(
            {
                "id": automation_id,
                "name": str(row[1]),
                "timezone": timezone_name,
                "rrule": str(row[3] or ""),
                "parameters": json_object(row[4]),
                "expected_occurrences": expected,
                "missing_occurrences": missing,
            }
        )

    stale_claimed: list[dict[str, str]] = []
    for row in dispatch_rows:
        claimed_at = row[4]
        if hasattr(claimed_at, "astimezone"):
            claimed_at_utc = claimed_at.astimezone(UTC)
        else:
            claimed_at_utc = resolved_now.astimezone(UTC)
        if str(row[2]) == "claimed" and row[5] is None and claimed_at_utc < stale_claimed_before:
            stale_claimed.append(
                {
                    "automation_id": str(row[0]),
                    "occurrence_key": str(row[1]),
                    "claimed_at": claimed_at.isoformat() if hasattr(claimed_at, "isoformat") else str(claimed_at),
                }
            )
    recent_dispatches = [
        {
            "automation_id": str(row[0]),
            "occurrence_key": str(row[1]),
            "status": str(row[2]),
            "run_id": row[3],
            "claimed_at": row[4].isoformat() if hasattr(row[4], "isoformat") else str(row[4]),
            "finished_at": row[5].isoformat() if hasattr(row[5], "isoformat") else (str(row[5]) if row[5] is not None else None),
        }
        for row in dispatch_rows[:20]
    ]
    return {
        "ok": not missing_occurrences and not stale_claimed,
        "workspace_slug": workspace_slug,
        "now": resolved_now.isoformat(),
        "lookback_hours": lookback_hours,
        "active_count": len(active_rows),
        "recent_dispatch_count": len(dispatch_rows),
        "missing_occurrence_count": len(missing_occurrences),
        "missing_occurrences": missing_occurrences,
        "stale_claimed_count": len(stale_claimed),
        "stale_claimed": stale_claimed,
        "automations": automations,
        "recent_dispatches": recent_dispatches,
    }


def claim_due_automation(database_url: str, due: DueAutomation) -> bool:
    with connect(database_url) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO phantomclaw_dispatches (
                  workspace_slug, automation_id, occurrence_key, status, claimed_at
                )
                VALUES (%s, %s, %s, 'claimed', now())
                ON CONFLICT (workspace_slug, automation_id, occurrence_key) DO UPDATE SET
                  status = 'claimed',
                  run_id = NULL,
                  claimed_at = now(),
                  finished_at = NULL,
                  result_json = jsonb_build_object(
                    'reclaimed_from_stale', true,
                    'previous_status', phantomclaw_dispatches.status,
                    'previous_claimed_at', phantomclaw_dispatches.claimed_at
                  )
                WHERE phantomclaw_dispatches.status = 'claimed'
                  AND phantomclaw_dispatches.finished_at IS NULL
                  AND phantomclaw_dispatches.claimed_at < now() - (%s * interval '1 minute')
                """,
                (due.workspace_slug, due.automation_id, due.occurrence_key, STALE_CLAIMED_MINUTES),
            )
            claimed = cur.rowcount == 1
        conn.commit()
    return claimed


def finish_dispatch(database_url: str, due: DueAutomation, *, status: str, result: dict[str, Any], run_id: str | None = None) -> None:
    with connect(database_url) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE phantomclaw_dispatches
                SET status = %s,
                    run_id = %s,
                    finished_at = now(),
                    result_json = %s::jsonb
                WHERE workspace_slug = %s
                  AND automation_id = %s
                  AND occurrence_key = %s
                """,
                (
                    status,
                    run_id,
                    json.dumps(result, sort_keys=True),
                    due.workspace_slug,
                    due.automation_id,
                    due.occurrence_key,
                ),
            )
        conn.commit()


def namespace_for_peerlist(due: DueAutomation, *, live: bool, database_url: str, artifact_root: Path | None) -> argparse.Namespace:
    params = automation_default_parameters(due.automation_id)
    params.update(due.parameters)
    resolved_artifact_dir = (artifact_root / due.automation_id) if artifact_root else Path.cwd() / ".tmp" / "phantomclaw-worker" / due.automation_id
    return argparse.Namespace(
        automation_id=due.automation_id,
        live=live,
        dry_run=not live,
        sync=True,
        sync_blocked=True,
        artifact_dir=resolved_artifact_dir,
        report_output=None,
        bundle_output=None,
        database_url=database_url,
        workspace_slug=due.workspace_slug,
        backend=os.getenv("PEERLIST_BROWSER_BACKEND", "peerlist-http"),
        workflow_type=str(params.get("type") or params.get("workflow_type") or "follow"),
        follows_per_day=int(params.get("follows_per_day", 3)),
        max_follows_per_run=int(params.get("max_follows_per_run", 1)),
        unfollows_per_day=int(params.get("unfollows_per_day", 1000)),
        max_unfollows_per_run=int(params.get("max_unfollows_per_run", 1000)),
        unfollow_source=str(params.get("unfollow_source", "current_following")),
        unfollow_after_days=int(params.get("unfollow_after_days", 0)),
        following_page_start=int(params.get("following_page_start", 1)),
        following_page_limit=int(params.get("following_page_limit", 100)),
        do_not_unfollow_peers=bool(params.get("do_not_unfollow_peers", False)),
        do_not_unfollow_followers=bool(params.get("do_not_unfollow_followers", False)),
        min_delay_seconds=int(params.get("min_delay_seconds", 0)),
        max_delay_seconds=int(params.get("max_delay_seconds", 0)),
        candidate_pool_limit=int(params.get("candidate_pool_limit", 1000)),
    )


def due_effective_live(due: DueAutomation, *, live: bool) -> bool:
    if due.parameters.get("dry_run_only") is True:
        return False
    return live or due.parameters.get("live_enabled") is True


def execute_due_automation(due: DueAutomation, *, live: bool, database_url: str, artifact_root: Path | None) -> dict[str, Any]:
    canonical = canonical_automation_name(due.automation_id)
    if canonical != "peerlist-follow-workflow":
        return execute_native_command(due, live=live)

    from phantomclaw_cli import default_artifact_paths, run_peerlist_follow_workflow

    args = namespace_for_peerlist(due, live=due_effective_live(due, live=live), database_url=database_url, artifact_root=artifact_root)
    exit_code = int(run_peerlist_follow_workflow(args) or 0)
    _, bundle_path = default_artifact_paths("peerlist-follow-workflow", args.artifact_dir)
    bundle = json.loads(bundle_path.read_text())
    return {
        "executed": True,
        "exit_code": exit_code,
        "status": bundle["run"]["status"],
        "run_id": bundle["run"]["run_id"],
        "bundle_path": str(bundle_path),
    }


def dispatch_status_for_result(result: dict[str, Any]) -> str:
    status = str(result.get("status") or "")
    if status in {"failed", "error"}:
        return "failed"
    if status == "blocked":
        return "blocked"
    try:
        if int(result.get("exit_code", 0)) != 0:
            return "failed"
    except (TypeError, ValueError):
        return "failed"
    return "ok"


def native_command_for(due: DueAutomation, *, live: bool) -> list[str] | None:
    effective_live = due_effective_live(due, live=live)
    command = due.runner_command if effective_live else due.runner_dry_run_command
    if command:
        return normalize_native_command(command)
    if effective_live and due.runner_status == "native_candidate":
        return normalize_native_command(due.runner_command) if due.runner_command else None
    return None


def normalize_native_command(command: list[str]) -> list[str]:
    if not command:
        return command
    if command[0] in {"python", "python3"}:
        return [sys.executable, *command[1:]]
    return command


def native_working_directory(due: DueAutomation) -> Path:
    cwds = due.metadata.get("cwds")
    if isinstance(cwds, list):
        for item in cwds:
            if isinstance(item, str) and item:
                path = Path(item)
                if path.exists():
                    return path
    repo_dir = os.getenv("PHANTOMCLAW_REPO_DIR")
    if repo_dir and Path(repo_dir).exists():
        return Path(repo_dir)
    deployed_repo_dir = Path("/opt/phantomclaw")
    if deployed_repo_dir.exists():
        return deployed_repo_dir
    return Path.cwd()


def native_status_from_stdout(stdout: str, *, returncode: int) -> str:
    if returncode != 0:
        return "failed"
    text = stdout.strip()
    if not text:
        return "ok"
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return "ok"
    if not isinstance(parsed, dict):
        return "ok"
    status = str(parsed.get("status") or parsed.get("final_status") or "")
    if status in {"blocked", "failed", "error"}:
        return "failed" if status in {"failed", "error"} else "blocked"
    return "ok"


def tail_text(value: object, limit: int = 4000) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        text = value.decode(errors="replace")
    else:
        text = str(value)
    return text[-limit:]


def native_timeout_seconds() -> int:
    raw = os.getenv("PHANTOMCLAW_NATIVE_TIMEOUT_SECONDS", "900").strip()
    try:
        return max(1, int(raw))
    except ValueError:
        return 900


def parameter_text(value: object) -> str:
    if isinstance(value, bool):
        return "1" if value else "0"
    return str(value)


def set_env_parameter(env: dict[str, str], prefix: str, suffix: str, parameters: dict[str, Any], key: str) -> None:
    value = parameters.get(key)
    if value is None or value == "":
        return
    env[f"{prefix}_{suffix}"] = parameter_text(value)


def set_runner_database_env(env: dict[str, str], prefix: str) -> None:
    database_url = default_database_url()
    if not database_url:
        return
    env.setdefault("AUTOMATION_ANALYTICS_DATABASE_URL", database_url)
    env.setdefault(f"{prefix}_DATABASE_URL", database_url)
    env.setdefault(f"{prefix}_ANALYTICS_DATABASE_URL", database_url)


def apply_runner_parameter_env(env: dict[str, str], due: DueAutomation) -> None:
    canonical = canonical_automation_name(due.automation_id)
    parameters = automation_default_parameters(canonical)
    parameters.update(due.parameters)

    if canonical == "linkedin-company-profile-engagement":
        prefix = "LINKEDIN_COMPANY_PROFILE_ENGAGEMENT"
        set_runner_database_env(env, prefix)
        for key, suffix in {
            "search_url": "SEARCH_URL",
            "chrome_profile": "PROFILE",
            "actor_name": "ACTOR",
            "session_name": "SESSION",
            "post_cap": "POST_CAP",
            "repost_cap": "REPOST_CAP",
            "comment_cap": "COMMENT_CAP",
            "max_passes": "MAX_PASSES",
            "follow_admin_url": "FOLLOW_ADMIN_URL",
            "follow_cap": "FOLLOW_CAP",
            "analytics_url": "ANALYTICS_URL",
        }.items():
            set_env_parameter(env, prefix, suffix, parameters, key)
        return

    if canonical == "linkedin-sales-community-engagement":
        prefix = "LINKEDIN_SALES_COMMUNITY_ENGAGEMENT"
        set_runner_database_env(env, prefix)
        for key, suffix in {
            "url": "URL",
            "chrome_profile": "PROFILE",
            "profile_name": "PROFILE_NAME",
            "session_name": "SESSION",
            "like_cap": "LIKE_CAP",
            "require_action_verification": "REQUIRE_ACTION_VERIFICATION",
        }.items():
            set_env_parameter(env, prefix, suffix, parameters, key)


def execute_native_command(due: DueAutomation, *, live: bool) -> dict[str, Any]:
    if due.runner_status not in {"native", "native_candidate"}:
        return {"executed": False, "status": "blocked", "reason": "native_runner_missing"}
    effective_live = due_effective_live(due, live=live)
    command = native_command_for(due, live=live)
    if not command:
        return {
            "executed": False,
            "status": "blocked",
            "reason": "native_command_unavailable",
            "mode": "live" if effective_live else "dry-run",
        }
    env = os.environ.copy()
    env["PHANTOMCLAW_AUTOMATION_JSON"] = json.dumps(
        {
            "id": due.automation_id,
            "name": due.automation_name,
            "status": "ACTIVE",
            "source_status": due.metadata.get("source_status"),
            "rrule": due.rrule,
            "platform": due.platform,
            "surface": due.surface,
            "parameters": due.parameters,
            "cwds": due.metadata.get("cwds", []),
            "source": due.metadata.get("source", {}),
            "runner": {
                "status": due.runner_status,
                "dispatch": due.runner_dispatch,
                "command": due.runner_command,
                "dry_run_command": due.runner_dry_run_command,
                "codex_fallback_allowed": False,
            },
        },
        sort_keys=True,
    )
    apply_runner_parameter_env(env, due)
    timeout_seconds = native_timeout_seconds()
    with tempfile.TemporaryFile(mode="w+") as stdout_file, tempfile.TemporaryFile(mode="w+") as stderr_file:
        try:
            completed = subprocess.run(
                command,
                cwd=native_working_directory(due),
                check=False,
                stdout=stdout_file,
                stderr=stderr_file,
                text=True,
                timeout=timeout_seconds,
                env=env,
            )
        except subprocess.TimeoutExpired:
            stdout_file.seek(0)
            stderr_file.seek(0)
            return {
                "executed": True,
                "status": "failed",
                "reason": "native_runner_timeout",
                "mode": "live" if effective_live else "dry-run",
                "live_requested": live,
                "live_enabled": due.parameters.get("live_enabled") is True,
                "dry_run_only": due.parameters.get("dry_run_only") is True,
                "exit_code": 124,
                "stdout": tail_text(stdout_file.read().strip()),
                "stderr": tail_text(f"native runner timed out after {timeout_seconds}s. {stderr_file.read().strip()}"),
            }
        stdout_file.seek(0)
        stderr_file.seek(0)
        stdout = stdout_file.read().strip()
        stderr = stderr_file.read().strip()
    return {
        "executed": True,
        "status": native_status_from_stdout(stdout, returncode=completed.returncode),
        "mode": "live" if effective_live else "dry-run",
        "live_requested": live,
        "live_enabled": due.parameters.get("live_enabled") is True,
        "dry_run_only": due.parameters.get("dry_run_only") is True,
        "exit_code": completed.returncode,
        "stdout": tail_text(stdout),
        "stderr": tail_text(stderr),
    }


def run_worker_once(
    *,
    database_url: str,
    workspace_slug: str,
    now: datetime | None = None,
    live: bool = False,
    artifact_root: Path | None = None,
    catchup_minutes: int | None = None,
) -> dict[str, Any]:
    resolved_now = now or datetime.now(UTC)
    due_jobs = load_due_automations(
        database_url,
        workspace_slug=workspace_slug,
        now=resolved_now,
        catchup_minutes=catchup_minutes,
    )
    results: list[dict[str, Any]] = []
    for due in due_jobs:
        if not claim_due_automation(database_url, due):
            results.append({"automation_id": due.automation_id, "occurrence_key": due.occurrence_key, "claimed": False})
            continue
        try:
            result = execute_due_automation(due, live=live, database_url=database_url, artifact_root=artifact_root)
            dispatch_status = dispatch_status_for_result(result)
            finish_dispatch(
                database_url,
                due,
                status=dispatch_status,
                result=result,
                run_id=result.get("run_id") if isinstance(result.get("run_id"), str) else None,
            )
            result.update({"automation_id": due.automation_id, "occurrence_key": due.occurrence_key, "claimed": True})
            results.append(result)
        except Exception as exc:
            result = {"executed": False, "status": "failed", "error": type(exc).__name__, "message": str(exc)}
            finish_dispatch(database_url, due, status="failed", result=result)
            result.update({"automation_id": due.automation_id, "occurrence_key": due.occurrence_key, "claimed": True})
            results.append(result)
    return {
        "ok": all(item.get("status") not in {"failed", "blocked", "error"} for item in results),
        "workspace_slug": workspace_slug,
        "now": resolved_now.isoformat(),
        "due_count": len(due_jobs),
        "results": results,
    }


def run_worker_loop(
    *,
    database_url: str,
    workspace_slug: str,
    live: bool,
    interval_seconds: int,
    artifact_root: Path | None,
    catchup_minutes: int | None = None,
    max_iterations: int | None = None,
) -> None:
    iterations = 0
    while True:
        print(
            json.dumps(
                run_worker_once(
                    database_url=database_url,
                    workspace_slug=workspace_slug,
                    live=live,
                    artifact_root=artifact_root,
                    catchup_minutes=catchup_minutes,
                ),
                sort_keys=True,
            ),
            flush=True,
        )
        iterations += 1
        if max_iterations is not None and iterations >= max_iterations:
            return
        time.sleep(interval_seconds)
