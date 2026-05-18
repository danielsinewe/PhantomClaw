#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEPLOY_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
REPO_DIR="$(cd "$DEPLOY_DIR/../.." && pwd)"
TARGET_DIR="$DEPLOY_DIR/phantomclaw"

rm -rf "$TARGET_DIR"
mkdir -p "$TARGET_DIR/linkedin" "$TARGET_DIR/peerlist" "$TARGET_DIR/scripts" "$TARGET_DIR/schemas" "$TARGET_DIR/tests/fixtures"

cp "$REPO_DIR/automation_analytics.py" "$TARGET_DIR/"
cp "$REPO_DIR/automation_catalog.py" "$TARGET_DIR/"
cp "$REPO_DIR/phantomclaw_codex_migration.py" "$TARGET_DIR/"
cp "$REPO_DIR/phantomclaw_cli.py" "$TARGET_DIR/"
cp "$REPO_DIR/phantomclaw_worker.py" "$TARGET_DIR/"
cp "$REPO_DIR/phantomclaw_bundle.py" "$TARGET_DIR/"
cp "$REPO_DIR/run_lock.py" "$TARGET_DIR/"
if [ -f "${PHANTOMCLAW_REGISTRY_PATH:-$HOME/.config/phantomclaw/automations/registry.json}" ]; then
  cp "${PHANTOMCLAW_REGISTRY_PATH:-$HOME/.config/phantomclaw/automations/registry.json}" "$TARGET_DIR/registry.json"
fi
cp "$REPO_DIR/linkedin/__init__.py" "$TARGET_DIR/linkedin/"
cp -R "$REPO_DIR/linkedin/company_profile_engagement" "$TARGET_DIR/linkedin/"
cp -R "$REPO_DIR/linkedin/sales_community_engagement" "$TARGET_DIR/linkedin/"
cp "$REPO_DIR/peerlist/__init__.py" "$TARGET_DIR/peerlist/"
cp -R "$REPO_DIR/peerlist/follow_workflow" "$TARGET_DIR/peerlist/"
cp "$REPO_DIR/scripts/run_peerlist_follow_browser_use_agent.py" "$TARGET_DIR/scripts/"
cp "$REPO_DIR/scripts/run_peerlist_follow_browser_use_cli.py" "$TARGET_DIR/scripts/"
cp "$REPO_DIR/scripts/run_peerlist_follow_browserbase.py" "$TARGET_DIR/scripts/"
cp "$REPO_DIR/scripts/run_peerlist_follow_http.py" "$TARGET_DIR/scripts/"
cp "$DEPLOY_DIR/scripts/peerlist-browser-use-direct.mjs" "$TARGET_DIR/scripts/"
cp "$REPO_DIR/scripts/sync_run_bundle_to_neon.py" "$TARGET_DIR/scripts/"
cp "$REPO_DIR/scripts/cleanup_linkedin_dry_run_analytics.py" "$TARGET_DIR/scripts/"
cp "$REPO_DIR/scripts/sales_community_auth_activation.py" "$TARGET_DIR/scripts/"
cp "$REPO_DIR/scripts/repair_north_star_daily_metrics.py" "$TARGET_DIR/scripts/"
cp "$REPO_DIR/scripts/phantomclaw_run_due_automations.py" "$TARGET_DIR/scripts/"
cp "$REPO_DIR/scripts/upsert_daily_metric.py" "$TARGET_DIR/scripts/"
cp "$REPO_DIR/schemas/phantomclaw.run-bundle.v1.schema.json" "$TARGET_DIR/schemas/"
cp "$REPO_DIR/tests/fixtures/actor_missing.html" "$TARGET_DIR/tests/fixtures/"
cp "$REPO_DIR/tests/fixtures/company_profile_report.json" "$TARGET_DIR/tests/fixtures/"
cp "$REPO_DIR/tests/fixtures/linkedin_sales_community.html" "$TARGET_DIR/tests/fixtures/"
cp "$REPO_DIR/tests/fixtures/normal_feed.html" "$TARGET_DIR/tests/fixtures/"
cp "$REPO_DIR/tests/fixtures/promoted_feed.html" "$TARGET_DIR/tests/fixtures/"
cp "$REPO_DIR/tests/fixtures/sales_community_report.json" "$TARGET_DIR/tests/fixtures/"

find "$TARGET_DIR" -name "__pycache__" -type d -prune -exec rm -rf {} +
find "$TARGET_DIR" -name ".DS_Store" -type f -delete

echo "Prepared PhantomClaw Railway context at $TARGET_DIR"
