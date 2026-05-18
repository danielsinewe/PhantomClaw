#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

PACKAGE_ROOT = Path(__file__).resolve().parent.parent
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

from phantomclaw_codex_migration import load_registry, registry_readiness_report
from phantomclaw_worker import default_database_url
from scripts.phantomclaw_production_check import (
    active_codex_automations,
    check_worker_health,
    default_codex_automation_root,
    http_health,
    paused_native_automation_status,
    registry_source_path_status,
    verify_phantomclaw_cli,
    cli_summary,
)


def checklist_status(checks: dict[str, dict[str, Any]]) -> str:
    if all(bool(check.get("ok")) for check in checks.values()):
        return "complete"
    paused = checks.get("no_paused_native_automations", {})
    active_checks = {
        key: check
        for key, check in checks.items()
        if key != "no_paused_native_automations"
    }
    paused_automations = paused.get("paused_automations")
    if (
        all(bool(check.get("ok")) for check in active_checks.values())
        and isinstance(paused_automations, list)
        and len(paused_automations) == 1
        and paused_automations[0].get("id") == "linkedin-sales-community"
        and paused_automations[0].get("pause_reason") == "sales_community_auth_required"
    ):
        return "blocked_sales_community_auth"
    return "failing"


def next_action_for_status(status: str) -> dict[str, Any]:
    if status == "complete":
        return {
            "type": "none",
            "summary": "All automation completion checks passed.",
        }
    if status == "blocked_sales_community_auth":
        return {
            "type": "external_auth",
            "summary": "Restore authenticated access to LinkedIn Sales Community, then run the guarded activation.",
            "blocked_automation_id": "linkedin-sales-community",
            "doc": "docs/sales-community-auth-unblock.md",
            "verify_profile_command": 'browser-use --profile "danielsinewe.com" open https://scommunity.linkedin.com/',
            "activation_command": "railway run uv run python scripts/sales_community_auth_activation.py --activate",
        }
    return {
        "type": "investigate_failed_check",
        "summary": "Inspect checks with ok=false and fix the first failing production-health requirement.",
    }


def build_completion_audit(
    *,
    registry: dict[str, Any],
    codex_active: list[str],
    gateway: dict[str, Any],
    phantomclaw_cli: dict[str, Any],
    worker: dict[str, Any],
) -> dict[str, Any]:
    readiness = registry_readiness_report(registry)
    source_paths = registry_source_path_status(registry)
    paused_native = paused_native_automation_status(registry)
    checks = {
        "no_active_codex_automations": {
            "ok": len(codex_active) == 0,
            "active_count": len(codex_active),
            "active_paths": codex_active,
        },
        "gateway_health": gateway,
        "phantomclaw_cli": cli_summary(phantomclaw_cli),
        "registry_active_runners": {
            "ok": bool(readiness["ready"]) and readiness["total_without_remote_runner"] == 0,
            "active": readiness["active"],
            "total": readiness["total"],
            "blocked": readiness["blocked"],
            "total_without_remote_runner": readiness["total_without_remote_runner"],
            "runnable_automations": readiness["runnable_automations"],
            "blocked_automations": readiness["blocked_automations"],
        },
        "registry_source_paths": {
            "ok": source_paths["ok"],
            "missing_count": source_paths["missing_count"],
            "deleted_missing_count": source_paths["deleted_missing_count"],
        },
        "worker_health": worker,
        "no_paused_native_automations": paused_native,
    }
    status = checklist_status(checks)
    return {
        "ok": status == "complete",
        "status": status,
        "objective": "make sure all the automations are working perfectly",
        "next_action": next_action_for_status(status),
        "checks": checks,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit whether all PhantomClaw automations are actually complete")
    parser.add_argument("--registry", type=Path)
    parser.add_argument("--codex-automations-root", type=Path, default=default_codex_automation_root())
    parser.add_argument("--gateway-health-url", default="https://openclaw-production-22d3d.up.railway.app/health")
    parser.add_argument("--phantomclaw-cli", default=str(Path.home() / "Documents/GitHub/phantomclaw-cli/dist/cli.js"))
    parser.add_argument("--timeout", type=int, default=20)
    parser.add_argument("--database-url", default=default_database_url())
    parser.add_argument("--workspace-slug", default=os.getenv("PHANTOMCLAW_WORKSPACE_SLUG") or os.getenv("PHANTOMCLAW_WORKSPACE") or "daniel-sinewe")
    parser.add_argument("--worker-lookback-hours", type=int, default=1)
    parser.add_argument("--require-worker", action=argparse.BooleanOptionalAction, default=True)
    args = parser.parse_args(argv)

    audit = build_completion_audit(
        registry=load_registry(args.registry),
        codex_active=active_codex_automations(args.codex_automations_root),
        gateway=http_health(args.gateway_health_url, args.timeout),
        phantomclaw_cli=verify_phantomclaw_cli(args.phantomclaw_cli, args.timeout),
        worker=check_worker_health(
            database_url=args.database_url,
            workspace_slug=args.workspace_slug,
            lookback_hours=args.worker_lookback_hours,
            require_worker=args.require_worker,
            fail_on_recent_failures=True,
        ),
    )
    print(json.dumps(audit, indent=2, sort_keys=True))
    return 0 if audit["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
