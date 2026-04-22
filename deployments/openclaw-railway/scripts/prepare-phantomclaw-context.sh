#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEPLOY_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
REPO_DIR="$(cd "$DEPLOY_DIR/../.." && pwd)"
TARGET_DIR="$DEPLOY_DIR/phantomclaw"

rm -rf "$TARGET_DIR"
mkdir -p "$TARGET_DIR/peerlist" "$TARGET_DIR/scripts" "$TARGET_DIR/schemas"

cp "$REPO_DIR/automation_analytics.py" "$TARGET_DIR/"
cp "$REPO_DIR/automation_catalog.py" "$TARGET_DIR/"
cp "$REPO_DIR/phantomclaw_bundle.py" "$TARGET_DIR/"
cp "$REPO_DIR/peerlist/__init__.py" "$TARGET_DIR/peerlist/"
cp -R "$REPO_DIR/peerlist/follow_workflow" "$TARGET_DIR/peerlist/"
rm -rf "$TARGET_DIR/peerlist/follow_workflow/__pycache__"
cp "$REPO_DIR/scripts/run_peerlist_follow_browser_use_agent.py" "$TARGET_DIR/scripts/"
cp "$REPO_DIR/scripts/run_peerlist_follow_browser_use_cli.py" "$TARGET_DIR/scripts/"
cp "$REPO_DIR/scripts/run_peerlist_follow_browserbase.py" "$TARGET_DIR/scripts/"
cp "$REPO_DIR/scripts/run_peerlist_follow_http.py" "$TARGET_DIR/scripts/"
cp "$REPO_DIR/scripts/sync_run_bundle_to_neon.py" "$TARGET_DIR/scripts/"
cp "$REPO_DIR/scripts/upsert_daily_metric.py" "$TARGET_DIR/scripts/"
cp "$REPO_DIR/schemas/phantomclaw.run-bundle.v1.schema.json" "$TARGET_DIR/schemas/"

find "$TARGET_DIR" -name "__pycache__" -type d -prune -exec rm -rf {} +

echo "Prepared PhantomClaw Railway context at $TARGET_DIR"
