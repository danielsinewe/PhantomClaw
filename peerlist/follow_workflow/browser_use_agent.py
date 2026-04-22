from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from automation_catalog import PEERLIST_FOLLOW_WORKFLOW, automation_default_parameters
from phantomclaw_bundle import build_run_bundle

try:
    from pydantic import BaseModel, Field
except ImportError:  # pragma: no cover - browser-use-sdk depends on pydantic.
    class BaseModel:  # type: ignore[no-redef]
        pass

    def Field(default: Any = None, *, default_factory: Any = None, **_: Any) -> Any:  # type: ignore[no-redef]
        if default_factory is not None:
            return default_factory()
        return default


DEFAULT_BROWSER_USE_MODEL = "claude-sonnet-4.6"
DEFAULT_PROXY_COUNTRY_CODE = "de"
DEFAULT_ALLOWED_DOMAINS = ("peerlist.io", "*.peerlist.io")
NO_PROXY_VALUES = {"", "none", "off", "direct", "false", "0"}


class BrowserUseAgentError(RuntimeError):
    """Raised when the Browser Use cloud agent cannot produce a usable report."""


class PeerlistWorkflowRecord(BaseModel):
    type: str | None = None
    target_name: str | None = None
    target_url: str | None = None
    reason: str | None = None
    selector: str | None = None
    target_excerpt: str | None = None
    verified: bool | None = None
    ts: str | None = None
    message: str | None = None


class PeerlistFollowWorkflowOutput(BaseModel):
    run_id: str
    started_at: str
    finished_at: str | None = None
    status: Literal["ok", "no_action", "blocked", "error"]
    stop_reason: str | None = None
    profile_name: str | None = None
    actor_verified: bool = False
    workflow_type: Literal["follow", "unfollow", "rebalance"] = "follow"
    workflow_parameters: dict[str, Any] = Field(default_factory=dict)
    peerlist_profile_followers_before: int | None = None
    peerlist_profile_followers_after: int | None = None
    profiles_scanned: int = 0
    profiles_considered: int = 0
    follows_count: int = 0
    unfollows_count: int = 0
    peers_preserved_count: int = 0
    actions: list[PeerlistWorkflowRecord] = Field(default_factory=list)
    skipped: list[PeerlistWorkflowRecord] = Field(default_factory=list)
    blockers: list[PeerlistWorkflowRecord] = Field(default_factory=list)
    events: list[PeerlistWorkflowRecord] = Field(default_factory=list)


def build_peerlist_follow_task(*, parameters: dict[str, Any], live: bool) -> str:
    mode = "LIVE MUTATION MODE" if live else "DRY RUN MODE"
    return f"""
You are running the PhantomClaw Peerlist follow workflow.

Mode: {mode}

Goal:
- Increase the authenticated Peerlist profile follower count.
- Use Peerlist only through the logged-in browser profile.
- Return one JSON object only. Do not wrap it in markdown.
- Match the structured output schema exactly.

Workflow parameters:
{json.dumps(parameters, indent=2, sort_keys=True)}

Safety rules:
- Fail closed if logged out, actor identity is unclear, or a challenge/CAPTCHA appears.
- Do not exceed the configured daily follow/unfollow caps.
- Do not unfollow mutual Peerlist peers when do_not_unfollow_peers is true.
- Do not unfollow profiles followed by this workflow until unfollow_after_days has elapsed.
- Verify state after every follow/unfollow action.
- Keep discovery separate from mutation. Scan candidates first, then apply filters and caps.

Peerlist behavior:
- Peerlist calls mutual follows "peers".
- Prefer profile-level UI actions for follow/unfollow mutations.

Required JSON shape:
{{
  "run_id": "peerlist-follow-<unique-id>",
  "started_at": "<ISO-8601 timestamp>",
  "finished_at": "<ISO-8601 timestamp>",
  "status": "ok|no_action|blocked|error",
  "stop_reason": null,
  "profile_name": "<authenticated Peerlist profile name>",
  "actor_verified": true,
  "workflow_type": "{parameters.get("type", "follow")}",
  "workflow_parameters": {json.dumps(parameters, sort_keys=True)},
  "peerlist_profile_followers_before": null,
  "peerlist_profile_followers_after": null,
  "profiles_scanned": 0,
  "profiles_considered": 0,
  "follows_count": 0,
  "unfollows_count": 0,
  "peers_preserved_count": 0,
  "actions": [],
  "skipped": [],
  "blockers": [],
  "events": []
}}

Action event requirements:
- For verified follows, add an event with type "peerlist_profile_followed".
- For verified unfollows, add an event with type "peerlist_profile_unfollowed".
- Include target_name, target_url, verified, and ts whenever available.

If this is DRY RUN MODE:
- Do not click follow or unfollow.
- Return status "no_action" unless a blocker is found.
- Still scan candidates and return follower count, profile name, blockers, skipped rows, and candidate counts.
""".strip()


def _extract_json_object(raw: str) -> dict[str, Any]:
    text = raw.strip()
    if not text:
        raise BrowserUseAgentError("Browser Use returned an empty output")
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if not match:
            raise BrowserUseAgentError("Browser Use output did not include a JSON object")
        parsed = json.loads(match.group(0))
    if not isinstance(parsed, dict):
        raise BrowserUseAgentError("Browser Use output JSON must be an object")
    return parsed


def report_from_browser_use_output(raw_output: Any, *, parameters: dict[str, Any]) -> dict[str, Any]:
    if isinstance(raw_output, dict):
        report = dict(raw_output)
    elif hasattr(raw_output, "model_dump"):
        dumped = raw_output.model_dump()
        if not isinstance(dumped, dict):
            raise BrowserUseAgentError("Browser Use model output must dump to an object")
        report = dict(dumped)
    else:
        report = _extract_json_object(str(raw_output))

    now = datetime.now(UTC).isoformat()
    report.setdefault("run_id", f"peerlist-follow-{int(datetime.now(UTC).timestamp())}")
    report.setdefault("started_at", now)
    report.setdefault("finished_at", now)
    report.setdefault("status", "no_action")
    report.setdefault("workflow_type", parameters.get("type", "follow"))
    report.setdefault("workflow_parameters", parameters)
    report.setdefault("actor_verified", False)
    report.setdefault("profiles_scanned", int(report.get("items_scanned", 0) or 0))
    report.setdefault("profiles_considered", int(report.get("items_considered", 0) or 0))
    report.setdefault("follows_count", 0)
    report.setdefault("unfollows_count", 0)
    report.setdefault("peers_preserved_count", 0)
    report.setdefault("actions", [])
    report.setdefault("skipped", [])
    report.setdefault("blockers", [])
    report.setdefault("events", [])
    return report


def load_parameters(args: argparse.Namespace) -> dict[str, Any]:
    parameters = automation_default_parameters(PEERLIST_FOLLOW_WORKFLOW)
    parameters.update(
        {
            "type": args.workflow_type,
            "follows_per_day": args.follows_per_day,
            "unfollows_per_day": args.unfollows_per_day,
            "unfollow_after_days": args.unfollow_after_days,
            "do_not_unfollow_peers": args.do_not_unfollow_peers,
        }
    )
    return parameters


def run_browser_use_agent(
    *,
    task: str,
    api_key: str,
    model: str,
    profile_id: str,
    workspace_id: str | None,
    proxy_country_code: str,
    max_cost_usd: float | None,
    enable_recording: bool | None,
    op_vault_id: str | None,
    allowed_domains: list[str],
    cache_script: bool | None,
) -> Any:
    try:
        from browser_use_sdk.v3 import BrowserUse
    except ImportError as exc:
        raise BrowserUseAgentError(
            "browser-use-sdk is not installed. Install it with `pip install --upgrade browser-use-sdk`."
        ) from exc

    client = BrowserUse(api_key=api_key)
    session_kwargs: dict[str, Any] = {
        "model": model,
        "profile_id": profile_id,
    }
    use_proxy = proxy_country_code.strip().lower() not in NO_PROXY_VALUES
    if use_proxy:
        session_kwargs["proxy_country_code"] = proxy_country_code
    if workspace_id:
        session_kwargs["workspace_id"] = workspace_id
    if max_cost_usd is not None:
        session_kwargs["max_cost_usd"] = max_cost_usd
    if enable_recording is not None:
        session_kwargs["enable_recording"] = enable_recording
    if cache_script is not None:
        session_kwargs["cache_script"] = cache_script

    session = client.sessions.create(**session_kwargs)
    try:
        run_kwargs: dict[str, Any] = {
            "model": model,
            "session_id": session.id,
            "output_schema": PeerlistFollowWorkflowOutput,
        }
        if use_proxy:
            run_kwargs["proxy_country_code"] = proxy_country_code
        if workspace_id:
            run_kwargs["workspace_id"] = workspace_id
        if max_cost_usd is not None:
            run_kwargs["max_cost_usd"] = max_cost_usd
        if cache_script is not None:
            run_kwargs["cache_script"] = cache_script
        if op_vault_id:
            run_kwargs["op_vault_id"] = op_vault_id
            run_kwargs["allowed_domains"] = allowed_domains
        return client.run(task, **run_kwargs)
    finally:
        client.sessions.stop(session.id)


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the Peerlist follow workflow through Browser Use Cloud Agent")
    parser.add_argument("--live", action="store_true", help="Allow follow/unfollow mutations. Defaults to dry-run.")
    parser.add_argument("--workflow-type", choices=("follow", "unfollow", "rebalance"), default="follow")
    parser.add_argument("--follows-per-day", type=int, default=20)
    parser.add_argument("--unfollows-per-day", type=int, default=10)
    parser.add_argument("--unfollow-after-days", type=int, default=14)
    parser.add_argument("--do-not-unfollow-peers", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--api-key", default=os.getenv("BROWSER_USE_API_KEY"))
    parser.add_argument("--model", default=os.getenv("BROWSER_USE_MODEL", DEFAULT_BROWSER_USE_MODEL))
    parser.add_argument("--profile-id", default=os.getenv("BROWSER_USE_PROFILE_ID"))
    parser.add_argument("--workspace-id", default=os.getenv("BROWSER_USE_WORKSPACE_ID"))
    parser.add_argument("--proxy-country-code", default=os.getenv("BROWSER_USE_PROXY_COUNTRY_CODE", DEFAULT_PROXY_COUNTRY_CODE))
    parser.add_argument("--op-vault-id", default=os.getenv("BROWSER_USE_1PASSWORD_VAULT_ID"))
    parser.add_argument(
        "--allowed-domain",
        action="append",
        dest="allowed_domains",
        default=None,
        help="Domain Browser Use may request 1Password credentials for. Repeatable.",
    )
    parser.add_argument(
        "--max-cost-usd",
        type=float,
        default=float(os.getenv("BROWSER_USE_MAX_COST_USD")) if os.getenv("BROWSER_USE_MAX_COST_USD") else None,
    )
    parser.add_argument("--enable-recording", action=argparse.BooleanOptionalAction, default=None)
    parser.add_argument("--cache-script", action=argparse.BooleanOptionalAction, default=None)
    parser.add_argument("--report-output", type=Path)
    parser.add_argument("--bundle-output", type=Path)
    parser.add_argument("--task-output", type=Path)
    parser.add_argument("--task-only", action="store_true", help="Render the Browser Use task and exit without calling the API.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    parameters = load_parameters(args)
    task = build_peerlist_follow_task(parameters=parameters, live=args.live)
    if args.task_output:
        args.task_output.parent.mkdir(parents=True, exist_ok=True)
        args.task_output.write_text(task + "\n")
    if args.task_only:
        if not args.task_output:
            print(task)
        return 0

    if not args.api_key:
        parser.error("BROWSER_USE_API_KEY or --api-key is required")
    if not args.profile_id:
        parser.error("BROWSER_USE_PROFILE_ID or --profile-id is required")

    result = run_browser_use_agent(
        task=task,
        api_key=args.api_key,
        model=args.model,
        profile_id=args.profile_id,
        workspace_id=args.workspace_id,
        proxy_country_code=args.proxy_country_code,
        max_cost_usd=args.max_cost_usd,
        enable_recording=args.enable_recording,
        op_vault_id=args.op_vault_id,
        allowed_domains=args.allowed_domains or list(DEFAULT_ALLOWED_DOMAINS),
        cache_script=args.cache_script,
    )
    raw_output = getattr(result, "output", result)
    report = report_from_browser_use_output(raw_output, parameters=parameters)
    bundle = build_run_bundle(automation_name=PEERLIST_FOLLOW_WORKFLOW, report=report)

    if args.report_output:
        write_json(args.report_output, report)
    if args.bundle_output:
        write_json(args.bundle_output, bundle)
    if not args.report_output and not args.bundle_output:
        print(json.dumps(bundle, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
