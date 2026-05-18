#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import tomllib
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen

PACKAGE_ROOT = Path(__file__).resolve().parent.parent
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

from phantomclaw_codex_migration import load_registry, registry_readiness_report
from phantomclaw_worker import default_database_url, worker_status


def default_codex_automation_root() -> Path:
    return Path.home() / ".codex" / "automations"


def active_codex_automations(root: Path) -> list[str]:
    if not root.exists():
        return []
    active: list[str] = []
    for path in sorted(root.glob("*/automation.toml")):
        if "_archived" in path.parts:
            continue
        data = tomllib.loads(path.read_text())
        if str(data.get("status") or "PAUSED").upper() == "ACTIVE":
            active.append(str(path))
    return active


def http_health(url: str, timeout: int) -> dict[str, Any]:
    try:
        request = Request(url, headers={"User-Agent": "phantomclaw-production-check/1"})
        with urlopen(request, timeout=timeout) as response:
            body = response.read(256).decode("utf-8", errors="replace")
            return {"ok": response.status == 200, "status": response.status, "body": body.strip()}
    except Exception as exc:
        return {"ok": False, "error": type(exc).__name__, "message": str(exc)}


def run_cli(command: list[str], timeout: int, *, env: dict[str, str] | None = None) -> dict[str, Any]:
    completed = subprocess.run(command, text=True, capture_output=True, timeout=timeout, check=False, env=env)
    return {
        "ok": completed.returncode == 0,
        "exit_code": completed.returncode,
        "stdout": completed.stdout.strip(),
        "stderr": completed.stderr.strip(),
    }


def verify_phantomclaw_cli(phantomclaw_cli: str, timeout: int) -> dict[str, Any]:
    command = ["node", phantomclaw_cli]
    if not os.getenv("PHANTOMCLAW_ACCESS_TOKEN"):
        return run_cli([*command, "whoami", "--verify"], timeout)

    with tempfile.TemporaryDirectory(prefix="phantomclaw-cli-check-") as config_dir:
        env = {
            **os.environ,
            "PHANTOMCLAW_CONFIG_DIR": config_dir,
        }
        login_command = [*command, "login"]
        workspace = os.getenv("PHANTOMCLAW_WORKSPACE_SLUG") or os.getenv("PHANTOMCLAW_WORKSPACE")
        if workspace:
            login_command.extend(["--workspace", workspace])
        login = run_cli(login_command, timeout, env=env)
        if not login["ok"]:
            return {
                **login,
                "phase": "login",
            }
        whoami = run_cli([*command, "whoami", "--verify"], timeout, env=env)
        return {
            **whoami,
            "phase": "whoami",
        }


def cli_summary(cli: dict[str, Any]) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "ok": cli["ok"],
        "exit_code": cli["exit_code"],
    }
    if cli.get("phase"):
        summary["phase"] = cli["phase"]
    if not cli["ok"]:
        # Keep the readiness JSON actionable without printing large command output.
        for stream in ("stdout", "stderr"):
            value = str(cli.get(stream) or "").strip()
            if value:
                summary[stream] = value[-500:]
    return summary


def check_worker_health(
    *,
    database_url: str | None,
    workspace_slug: str,
    lookback_hours: int,
    require_worker: bool,
    fail_on_recent_failures: bool,
) -> dict[str, Any]:
    if not database_url:
        return {
            "checked": False,
            "ok": not require_worker,
            "reason": "database_url_not_configured",
        }
    try:
        status = worker_status(
            database_url=database_url,
            workspace_slug=workspace_slug,
            lookback_hours=lookback_hours,
        )
    except Exception as exc:
        return {
            "checked": True,
            "ok": False,
            "error": type(exc).__name__,
            "message": str(exc),
        }
    recent_dispatches = status.get("recent_dispatches", [])
    recent_failed = [
        dispatch
        for dispatch in recent_dispatches
        if str(dispatch.get("status") or "") in {"blocked", "failed"}
    ]
    ok = bool(status.get("ok")) and (not fail_on_recent_failures or not recent_failed)
    return {
        "checked": True,
        "ok": ok,
        "active_count": status.get("active_count"),
        "recent_dispatch_count": status.get("recent_dispatch_count"),
        "recent_failed_dispatch_count": len(recent_failed),
        "missing_occurrence_count": status.get("missing_occurrence_count"),
        "stale_claimed_count": status.get("stale_claimed_count"),
        "recent_dispatches": recent_dispatches[:5],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check PhantomClaw production readiness")
    parser.add_argument("--registry", type=Path)
    parser.add_argument("--codex-automations-root", type=Path, default=default_codex_automation_root())
    parser.add_argument("--gateway-health-url", default="https://openclaw-production-22d3d.up.railway.app/health")
    parser.add_argument("--phantomclaw-cli", default=str(Path.home() / "Documents/GitHub/phantomclaw-cli/dist/cli.js"))
    parser.add_argument("--timeout", type=int, default=20)
    parser.add_argument("--allow-blocked", action="store_true", help="Return success even when active migrated jobs still need native runners")
    parser.add_argument("--require-all-remote-runners", action="store_true", help="Return failure unless every registry automation has a remote runnable command")
    parser.add_argument("--database-url", default=default_database_url())
    parser.add_argument("--workspace-slug", default=os.getenv("PHANTOMCLAW_WORKSPACE_SLUG") or os.getenv("PHANTOMCLAW_WORKSPACE") or "daniel-sinewe")
    parser.add_argument("--worker-lookback-hours", type=int, default=3)
    parser.add_argument("--require-worker", action="store_true", help="Return failure when worker dispatch health cannot be checked")
    parser.add_argument("--fail-on-recent-dispatch-failures", action="store_true", help="Return failure if recent worker dispatches include failed or blocked runs")
    args = parser.parse_args(argv)

    registry = load_registry(args.registry)
    readiness = registry_readiness_report(registry)
    codex_active = active_codex_automations(args.codex_automations_root)
    gateway = http_health(args.gateway_health_url, args.timeout)
    cli = verify_phantomclaw_cli(args.phantomclaw_cli, args.timeout)
    worker = check_worker_health(
        database_url=args.database_url,
        workspace_slug=args.workspace_slug,
        lookback_hours=args.worker_lookback_hours,
        require_worker=args.require_worker,
        fail_on_recent_failures=args.fail_on_recent_dispatch_failures,
    )

    all_remote_ok = not args.require_all_remote_runners or readiness["total_without_remote_runner"] == 0
    ok = (
        not codex_active
        and gateway["ok"]
        and cli["ok"]
        and worker["ok"]
        and (readiness["ready"] or args.allow_blocked)
        and all_remote_ok
    )
    result = {
        "ok": ok,
        "codex_processing_enabled": False,
        "active_codex_automations": len(codex_active),
        "phantomclaw_registry": readiness,
        "gateway_health": gateway,
        "phantomclaw_cli": cli_summary(cli),
        "worker": worker,
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
