#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DEPLOY_PATH = REPO_ROOT / "deployments" / "openclaw-railway"
DEFAULT_CONTEXT_PREPARE = DEFAULT_DEPLOY_PATH / "scripts" / "prepare-phantomclaw-context.sh"
RAILWAY_CONFIG_PATH = Path.home() / ".railway" / "config.json"
TOKEN_ENV_VAR = "RAILWAY_TOKEN"
ACCOUNT_TOKEN_ENV_VAR = "RAILWAY_API_TOKEN"


@dataclass(frozen=True)
class RailwayTarget:
    project: str | None
    environment: str | None
    service: str | None
    source: str


def load_local_railway_target(path: Path = RAILWAY_CONFIG_PATH, repo_root: Path = REPO_ROOT) -> RailwayTarget:
    if not path.exists():
        return RailwayTarget(project=None, environment=None, service=None, source="missing_config")
    try:
        config = json.loads(path.read_text())
    except json.JSONDecodeError:
        return RailwayTarget(project=None, environment=None, service=None, source="invalid_config")
    projects = config.get("projects")
    if not isinstance(projects, dict):
        return RailwayTarget(project=None, environment=None, service=None, source="missing_projects")

    candidates = [repo_root, repo_root / "deployments" / "openclaw-railway"]
    for candidate in candidates:
        linked = projects.get(str(candidate))
        if isinstance(linked, dict):
            return RailwayTarget(
                project=string_or_none(linked.get("project")),
                environment=string_or_none(linked.get("environment") or linked.get("environmentName")),
                service=string_or_none(linked.get("service")),
                source=str(path),
            )
    return RailwayTarget(project=None, environment=None, service=None, source="unlinked_repo")


def string_or_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def resolve_target(args: argparse.Namespace) -> RailwayTarget:
    linked = load_local_railway_target()
    return RailwayTarget(
        project=string_or_none(args.project or os.getenv("RAILWAY_PROJECT_ID") or linked.project),
        environment=string_or_none(args.environment or os.getenv("RAILWAY_ENVIRONMENT_ID") or linked.environment),
        service=string_or_none(args.service or os.getenv("RAILWAY_SERVICE_ID") or linked.service or "OpenClaw"),
        source=linked.source,
    )


def command_env(args: argparse.Namespace) -> dict[str, str]:
    env = os.environ.copy()
    token_file = args.token_file or os.getenv("RAILWAY_TOKEN_FILE")
    if token_file and not env.get(TOKEN_ENV_VAR):
        token = Path(token_file).expanduser().read_text().strip()
        if token:
            env[TOKEN_ENV_VAR] = token
    return env


def auth_mode(env: dict[str, str]) -> str:
    if env.get(TOKEN_ENV_VAR):
        return "project_token"
    if env.get(ACCOUNT_TOKEN_ENV_VAR):
        return "account_token"
    return "oauth_session"


def run_command(command: list[str], *, cwd: Path, env: dict[str, str], timeout_seconds: int) -> dict[str, Any]:
    try:
        completed = subprocess.run(
            command,
            cwd=cwd,
            env=env,
            text=True,
            capture_output=True,
            check=False,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as exc:
        return {
            "ok": False,
            "exit_code": 124,
            "stdout": tail_text(exc.stdout),
            "stderr": f"timed out after {timeout_seconds}s. {tail_text(exc.stderr)}".strip(),
        }
    return {
        "ok": completed.returncode == 0,
        "exit_code": completed.returncode,
        "stdout": tail_text(completed.stdout),
        "stderr": tail_text(completed.stderr),
    }


def tail_text(value: object, limit: int = 4000) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        value = value.decode(errors="replace")
    return str(value).strip()[-limit:]


def build_deploy_command(args: argparse.Namespace, target: RailwayTarget) -> list[str]:
    command = [
        "railway",
        "up",
        "--detach",
        "--message",
        args.message,
    ]
    if target.service:
        command.extend(["--service", target.service])
    if target.environment:
        command.extend(["--environment", target.environment])
    if target.project:
        command.extend(["--project", target.project])
    if args.json:
        command.append("--json")
    return command


def required_target_fields(target: RailwayTarget) -> list[str]:
    missing = []
    if not target.project:
        missing.append("project")
    if not target.environment:
        missing.append("environment")
    if not target.service:
        missing.append("service")
    return missing


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Preflight and deploy the OpenClaw Railway service without relying on stale OAuth state.")
    parser.add_argument("--deploy", action="store_true", help="Run the Railway deployment. Without this flag, only preflight and print the command.")
    parser.add_argument("--prepare-context", action=argparse.BooleanOptionalAction, default=True, help="Refresh deployments/openclaw-railway/phantomclaw before deploying.")
    parser.add_argument("--deploy-path", type=Path, default=DEFAULT_DEPLOY_PATH)
    parser.add_argument("--project")
    parser.add_argument("--environment")
    parser.add_argument("--service")
    parser.add_argument("--token-file", help="Read RAILWAY_TOKEN from this file without printing it.")
    parser.add_argument("--message", default="Deploy PhantomClaw/OpenClaw runtime update")
    parser.add_argument("--timeout-seconds", type=int, default=120)
    parser.add_argument("--json", action="store_true", help="Ask Railway for JSON deployment output.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        env = command_env(args)
    except OSError as exc:
        print(
            json.dumps(
                {
                    "ok": False,
                    "deploy_requested": args.deploy,
                    "reason": "railway_token_file_unreadable",
                    "token_file": args.token_file or os.getenv("RAILWAY_TOKEN_FILE"),
                    "error": str(exc),
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 2
    target = resolve_target(args)
    deploy_command = build_deploy_command(args, target)
    missing = required_target_fields(target)

    result: dict[str, Any] = {
        "ok": False,
        "deploy_requested": args.deploy,
        "auth_mode": auth_mode(env),
        "target": {
            "project": target.project,
            "environment": target.environment,
            "service": target.service,
            "source": target.source,
        },
        "deploy_path": str(Path(args.deploy_path).expanduser()),
        "deploy_command": deploy_command,
        "missing_target_fields": missing,
    }

    if missing:
        result["reason"] = "missing_railway_target"
        print(json.dumps(result, indent=2, sort_keys=True))
        return 2

    status = run_command(["railway", "status", "--json"], cwd=REPO_ROOT, env=env, timeout_seconds=args.timeout_seconds)
    result["status_check"] = status
    if not status["ok"]:
        result["reason"] = "railway_auth_or_link_check_failed"
        result["next_step"] = (
            "Set RAILWAY_TOKEN or RAILWAY_TOKEN_FILE for non-interactive deploys, "
            "or refresh the local session with railway login from an interactive terminal."
        )
        print(json.dumps(result, indent=2, sort_keys=True))
        return 3

    if not args.deploy:
        result["ok"] = True
        result["reason"] = "preflight_passed"
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0

    if args.prepare_context:
        prepare = run_command(["bash", str(DEFAULT_CONTEXT_PREPARE)], cwd=REPO_ROOT, env=env, timeout_seconds=args.timeout_seconds)
        result["prepare_context"] = prepare
        if not prepare["ok"]:
            result["reason"] = "prepare_context_failed"
            print(json.dumps(result, indent=2, sort_keys=True))
            return 4

    deploy = run_command(deploy_command, cwd=Path(args.deploy_path).expanduser(), env=env, timeout_seconds=args.timeout_seconds)
    result["deploy"] = deploy
    result["ok"] = deploy["ok"]
    result["reason"] = "deploy_finished" if deploy["ok"] else "deploy_failed"
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if deploy["ok"] else 5


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
