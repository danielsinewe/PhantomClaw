#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="${PHANTOMCLAW_REPO_DIR:-/opt/phantomclaw}"
ARTIFACT_DIR="${PEERLIST_FOLLOW_ARTIFACT_DIR:-/data/workspace/artifacts/peerlist-follow-workflow}"
REPORT_PATH="${PEERLIST_FOLLOW_REPORT_PATH:-$ARTIFACT_DIR/latest-report.json}"
BUNDLE_PATH="${PEERLIST_FOLLOW_BUNDLE_PATH:-$ARTIFACT_DIR/latest.bundle.json}"
PYTHON_BIN="${PHANTOMCLAW_PYTHON_BIN:-}"

if [ -z "$PYTHON_BIN" ]; then
  if [ -x /opt/phantomclaw-venv/bin/python3 ]; then
    PYTHON_BIN=/opt/phantomclaw-venv/bin/python3
  else
    PYTHON_BIN=python3
  fi
fi

if [ ! -d "$REPO_DIR" ]; then
  echo "PhantomClaw repo not found at $REPO_DIR. Set PHANTOMCLAW_REPO_DIR." >&2
  exit 1
fi

mkdir -p "$ARTIFACT_DIR"
cd "$REPO_DIR"

if [ "${PEERLIST_BROWSER_BACKEND:-peerlist-http}" != "peerlist-http" ]; then
"$PYTHON_BIN" - <<'PY'
import importlib.util
import sys

missing = [
    module
    for module in ("browser_use_sdk", "pydantic")
    if importlib.util.find_spec(module) is None
]
if missing:
    sys.stderr.write(
        "Missing Python modules: "
        + ", ".join(missing)
        + ". Install repo dependencies before running this Railway entrypoint.\\n"
    )
    sys.exit(1)
PY
fi

args=(
  "scripts/run_peerlist_follow_browser_use_agent.py"
  "--profile-id" "${BROWSER_USE_PROFILE_ID:?BROWSER_USE_PROFILE_ID is required}"
  "--proxy-country-code" "${BROWSER_USE_PROXY_COUNTRY_CODE:-de}"
  "--report-output" "$REPORT_PATH"
  "--bundle-output" "$BUNDLE_PATH"
)

if [ -n "${BROWSER_USE_WORKSPACE_ID:-}" ]; then
  args+=("--workspace-id" "$BROWSER_USE_WORKSPACE_ID")
fi

if [ -n "${BROWSER_USE_1PASSWORD_VAULT_ID:-}" ]; then
  args+=("--op-vault-id" "$BROWSER_USE_1PASSWORD_VAULT_ID")
fi

if [ -n "${BROWSER_USE_MAX_COST_USD:-}" ]; then
  args+=("--max-cost-usd" "$BROWSER_USE_MAX_COST_USD")
fi

if [ "${PEERLIST_FOLLOW_LIVE:-0}" = "1" ]; then
  args+=("--live")
fi

if [ -n "${PEERLIST_FOLLOWS_PER_DAY:-}" ]; then
  args+=("--follows-per-day" "$PEERLIST_FOLLOWS_PER_DAY")
fi

if [ -n "${PEERLIST_UNFOLLOWS_PER_DAY:-}" ]; then
  args+=("--unfollows-per-day" "$PEERLIST_UNFOLLOWS_PER_DAY")
fi

if [ -n "${PEERLIST_MAX_UNFOLLOWS_PER_RUN:-}" ]; then
  args+=("--max-unfollows-per-run" "$PEERLIST_MAX_UNFOLLOWS_PER_RUN")
fi

if [ -n "${PEERLIST_UNFOLLOW_AFTER_DAYS:-}" ]; then
  args+=("--unfollow-after-days" "$PEERLIST_UNFOLLOW_AFTER_DAYS")
fi

if [ "${PEERLIST_BROWSER_BACKEND:-peerlist-http}" = "peerlist-http" ]; then
  http_args=(
    "scripts/run_peerlist_follow_http.py"
    "--report-output" "$REPORT_PATH"
    "--bundle-output" "$BUNDLE_PATH"
    "--workflow-type" "${PEERLIST_WORKFLOW_TYPE:-follow}"
    "--follows-per-day" "${PEERLIST_FOLLOWS_PER_DAY:-20}"
    "--max-follows-per-run" "${PEERLIST_MAX_FOLLOWS_PER_RUN:-1}"
    "--unfollows-per-day" "${PEERLIST_UNFOLLOWS_PER_DAY:-1000}"
    "--max-unfollows-per-run" "${PEERLIST_MAX_UNFOLLOWS_PER_RUN:-1}"
    "--unfollow-source" "${PEERLIST_UNFOLLOW_SOURCE:-workflow_history}"
    "--unfollow-after-days" "${PEERLIST_UNFOLLOW_AFTER_DAYS:-14}"
  )
  if [ "${PEERLIST_DO_NOT_UNFOLLOW_FOLLOWERS:-1}" = "0" ]; then
    http_args+=("--no-do-not-unfollow-followers")
  fi
  if [ -n "${PEERLIST_FOLLOWING_PAGE_START:-}" ]; then
    http_args+=("--following-page-start" "$PEERLIST_FOLLOWING_PAGE_START")
  fi
  if [ -n "${PEERLIST_FOLLOWING_PAGE_LIMIT:-}" ]; then
    http_args+=("--following-page-limit" "$PEERLIST_FOLLOWING_PAGE_LIMIT")
  fi
  if [ "${PEERLIST_FOLLOW_LIVE:-0}" = "1" ]; then
    http_args+=("--live")
  fi
  "$PYTHON_BIN" "${http_args[@]}"
elif [ "${PEERLIST_BROWSER_BACKEND:-peerlist-http}" = "browserbase" ]; then
  browserbase_args=(
    "scripts/run_peerlist_follow_browserbase.py"
    "--report-output" "$REPORT_PATH"
    "--bundle-output" "$BUNDLE_PATH"
    "--workflow-type" "${PEERLIST_WORKFLOW_TYPE:-follow}"
    "--follows-per-day" "${PEERLIST_FOLLOWS_PER_DAY:-20}"
    "--unfollows-per-day" "${PEERLIST_UNFOLLOWS_PER_DAY:-1000}"
    "--unfollow-after-days" "${PEERLIST_UNFOLLOW_AFTER_DAYS:-14}"
  )
  if [ "${PEERLIST_FOLLOW_LIVE:-0}" = "1" ]; then
    browserbase_args+=("--live")
  fi
  "$PYTHON_BIN" "${browserbase_args[@]}"
elif [ "${PEERLIST_BROWSER_BACKEND:-peerlist-http}" = "browser-use-cli" ]; then
  cli_args=(
    "scripts/run_peerlist_follow_browser_use_cli.py"
    "--report-output" "$REPORT_PATH"
    "--bundle-output" "$BUNDLE_PATH"
    "--workflow-type" "${PEERLIST_WORKFLOW_TYPE:-follow}"
    "--follows-per-day" "${PEERLIST_FOLLOWS_PER_DAY:-20}"
    "--unfollows-per-day" "${PEERLIST_UNFOLLOWS_PER_DAY:-1000}"
    "--unfollow-after-days" "${PEERLIST_UNFOLLOW_AFTER_DAYS:-14}"
  )
  if [ "${PEERLIST_FOLLOW_LIVE:-0}" = "1" ]; then
    cli_args+=("--live")
  fi
  "$PYTHON_BIN" "${cli_args[@]}"
else
  "$PYTHON_BIN" "${args[@]}"
fi

bundle_status="$("$PYTHON_BIN" - <<'PY' "$BUNDLE_PATH"
import json
import sys
from pathlib import Path
print(json.loads(Path(sys.argv[1]).read_text())["run"]["status"])
PY
)"

if [ "$bundle_status" = "blocked" ] && [ "${PEERLIST_SYNC_BLOCKED_RUNS:-0}" != "1" ]; then
  echo "Run status is blocked; skipping Neon analytics sync. Set PEERLIST_SYNC_BLOCKED_RUNS=1 to sync blocked diagnostics." >&2
elif [ -n "${AUTOMATION_ANALYTICS_DATABASE_URL:-${DATABASE_URL:-}}" ]; then
  "$PYTHON_BIN" scripts/sync_run_bundle_to_neon.py --bundle-path "$BUNDLE_PATH"
else
  echo "AUTOMATION_ANALYTICS_DATABASE_URL is not set; skipping Neon analytics sync." >&2
fi

"$PYTHON_BIN" - <<'PY' "$BUNDLE_PATH"
import json
import sys
from pathlib import Path

bundle = json.loads(Path(sys.argv[1]).read_text())
print(json.dumps({
    "bundle_path": sys.argv[1],
    "run_id": bundle["run"]["run_id"],
    "automation_name": bundle["automation"]["name"],
    "status": bundle["run"]["status"],
    "actions_total": bundle["metrics"]["actions_total"],
    "follows_count": bundle["metrics"]["follows_count"],
    "unfollows_count": bundle["metrics"].get("metrics_json", {}).get("unfollows_count"),
    "north_star_metric": bundle["automation"].get("north_star_metric"),
}, indent=2, sort_keys=True))
PY
