#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

PACKAGE_ROOT = Path(__file__).resolve().parent.parent
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

from phantomclaw_worker import default_database_url, sync_registry_to_neon

AUTOMATION_ID = "linkedin-sales-community"
PAUSE_REASON = "sales_community_auth_required"


def default_registry_path() -> Path:
    return Path(os.getenv("PHANTOMCLAW_REGISTRY_PATH", Path.home() / ".config" / "phantomclaw" / "automations" / "registry.json"))


def run_auth_check(
    *,
    artifact_dir: Path,
    db_path: Path,
    timeout_seconds: int,
) -> dict[str, Any]:
    artifact_dir.mkdir(parents=True, exist_ok=True)
    command = [
        sys.executable,
        "-m",
        "linkedin.sales_community_engagement.runner",
        "--like-cap",
        "0",
        "--artifact-dir",
        str(artifact_dir),
        "--db-path",
        str(db_path),
    ]
    completed = subprocess.run(command, text=True, capture_output=True, check=False, timeout=timeout_seconds)
    report_path = newest_report_path(artifact_dir)
    report = load_report(report_path) if report_path else None
    return {
        "command": command,
        "exit_code": completed.returncode,
        "stdout": completed.stdout.strip()[-1000:],
        "stderr": completed.stderr.strip()[-1000:],
        "report_path": str(report_path) if report_path else None,
        "report": report,
        "ready": report_ready_for_activation(report),
    }


def newest_report_path(artifact_dir: Path) -> Path | None:
    reports = sorted(artifact_dir.glob("*.json"), key=lambda path: path.stat().st_mtime, reverse=True)
    return reports[0] if reports else None


def load_report(path: Path) -> dict[str, Any]:
    loaded = json.loads(path.read_text())
    if not isinstance(loaded, dict):
        raise ValueError(f"report must be a JSON object: {path}")
    return loaded


def report_ready_for_activation(report: dict[str, Any] | None) -> bool:
    if not report:
        return False
    return (
        report.get("status") == "ok"
        and report.get("page_shape_ok") is True
        and not report.get("stop_reason")
    )


def activation_failure_reason(check: dict[str, Any]) -> str:
    report = check.get("report")
    if not isinstance(report, dict):
        return "report_missing"
    if report.get("stop_reason"):
        return str(report["stop_reason"])
    if report.get("status") != "ok":
        return f"status_{report.get('status') or 'unknown'}"
    if report.get("page_shape_ok") is not True:
        return "page_shape_not_ok"
    if check.get("exit_code") not in {0, None}:
        return f"exit_code_{check['exit_code']}"
    return "not_ready"


def activate_sales_community_in_registry(registry_path: Path) -> dict[str, Any]:
    registry = json.loads(registry_path.read_text())
    automations = registry.get("automations")
    if not isinstance(automations, list):
        raise ValueError("registry.automations must be a list")
    for automation in automations:
        if not isinstance(automation, dict) or automation.get("id") != AUTOMATION_ID:
            continue
        parameters = automation.get("parameters")
        if not isinstance(parameters, dict):
            parameters = {}
        parameters["live_enabled"] = True
        parameters.pop("pause_reason", None)
        automation["parameters"] = parameters
        automation["status"] = "ACTIVE"
        automation["source_status"] = "ACTIVE"
        registry_path.write_text(json.dumps(registry, indent=2, sort_keys=True) + "\n")
        return {
            "updated": True,
            "automation_id": AUTOMATION_ID,
            "status": "ACTIVE",
            "source_status": "ACTIVE",
            "live_enabled": True,
        }
    raise ValueError(f"automation not found in registry: {AUTOMATION_ID}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify and optionally activate the LinkedIn Sales Community automation")
    parser.add_argument("--artifact-dir", type=Path, default=Path(".tmp/sales-community-activation-check"))
    parser.add_argument("--db-path", type=Path, default=None)
    parser.add_argument("--registry-path", type=Path, default=default_registry_path())
    parser.add_argument("--database-url", default=default_database_url())
    parser.add_argument("--workspace-slug", default=os.getenv("PHANTOMCLAW_WORKSPACE_SLUG") or os.getenv("PHANTOMCLAW_WORKSPACE") or "daniel-sinewe")
    parser.add_argument("--timeout-seconds", type=int, default=180)
    parser.add_argument("--activate", action="store_true", help="Update registry and sync Neon only after the auth check is ready")
    parser.add_argument("--sync-neon", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--prune-absent", action=argparse.BooleanOptionalAction, default=True)
    args = parser.parse_args(argv)

    db_path = args.db_path or (args.artifact_dir / "state.sqlite3")
    check = run_auth_check(
        artifact_dir=args.artifact_dir,
        db_path=db_path,
        timeout_seconds=args.timeout_seconds,
    )
    result: dict[str, Any] = {
        "ok": bool(check["ready"]),
        "ready": bool(check["ready"]),
        "activated": False,
        "check": {
            "exit_code": check["exit_code"],
            "report_path": check["report_path"],
            "status": (check.get("report") or {}).get("status") if isinstance(check.get("report"), dict) else None,
            "stop_reason": (check.get("report") or {}).get("stop_reason") if isinstance(check.get("report"), dict) else None,
            "page_shape_ok": (check.get("report") or {}).get("page_shape_ok") if isinstance(check.get("report"), dict) else None,
            "items_scanned": (check.get("report") or {}).get("items_scanned") if isinstance(check.get("report"), dict) else None,
            "items_considered": (check.get("report") or {}).get("items_considered") if isinstance(check.get("report"), dict) else None,
        },
    }
    if not check["ready"]:
        result["reason"] = activation_failure_reason(check)
        print(json.dumps(result, indent=2, sort_keys=True))
        return 1
    if not args.activate:
        result["reason"] = "activation_ready"
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0

    result["registry_update"] = activate_sales_community_in_registry(args.registry_path)
    result["activated"] = True
    if args.sync_neon:
        if not args.database_url:
            result["ok"] = False
            result["reason"] = "database_url_missing"
            print(json.dumps(result, indent=2, sort_keys=True))
            return 2
        result["neon_sync"] = sync_registry_to_neon(
            database_url=args.database_url,
            registry_path=args.registry_path,
            workspace_slug=args.workspace_slug,
            prune_absent=args.prune_absent,
        )
    result["reason"] = "activated"
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
