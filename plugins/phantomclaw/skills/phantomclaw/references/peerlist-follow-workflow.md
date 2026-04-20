# Peerlist Follow Workflow

## Purpose

`peerlist-follow-workflow` is the first PhantomClaw workflow automation for Peerlist.

North-star metric:

```text
peerlist_profile_followers
```

The workflow tries to increase the authenticated Peerlist profile follower count through conservative follow/unfollow operations while preserving real Peerlist peers.

## Automation Identity

```json
{
  "automation_name": "peerlist-follow-workflow",
  "platform": "peerlist",
  "surface": "network"
}
```

## Parameters

```json
{
  "type": "follow",
  "follows_per_day": 20,
  "unfollows_per_day": 10,
  "unfollow_after_days": 14,
  "do_not_unfollow_peers": true
}
```

Parameter notes:

- `type`: `follow`, `unfollow`, or `rebalance`.
- `follows_per_day`: maximum verified follow actions per calendar day.
- `unfollows_per_day`: maximum verified unfollow actions per calendar day.
- `unfollow_after_days`: earliest age for cleanup candidates followed by this workflow.
- `do_not_unfollow_peers`: when true, never unfollow mutual relationships. Peerlist calls mutual follows `peers`.

## Run Metrics

Store these in `metrics_json`:

```json
{
  "north_star_metric": "peerlist_profile_followers",
  "peerlist_profile_followers_before": 473,
  "peerlist_profile_followers_after": 474,
  "peerlist_profile_followers_delta": 1,
  "workflow_type": "follow",
  "workflow_parameters": {
    "type": "follow",
    "follows_per_day": 20,
    "unfollows_per_day": 10,
    "unfollow_after_days": 14,
    "do_not_unfollow_peers": true
  },
  "profiles_scanned": 12,
  "profiles_considered": 3,
  "follows_count": 1,
  "unfollows_count": 0,
  "peers_preserved_count": 0,
  "skipped_count": 2,
  "blockers_count": 0
}
```

Top-level normalized metrics:

- `items_scanned`: profile candidates scanned.
- `items_considered`: profile candidates eligible after filters.
- `actions_total`: verified follows plus verified unfollows.
- `follows_count`: verified follows only.

Unfollows are stored in `metrics_json.unfollows_count` because the shared fact table has no dedicated `unfollows_count` column yet.

## Action Events

Follow:

```json
{
  "type": "peerlist_profile_followed",
  "target_name": "Ada Builder",
  "target_url": "https://peerlist.io/adabuilder",
  "verified": true
}
```

Unfollow:

```json
{
  "type": "peerlist_profile_unfollowed",
  "target_name": "Ada Builder",
  "target_url": "https://peerlist.io/adabuilder",
  "verified": true
}
```

Skip mutual Peerlist peers:

```json
{
  "type": "unfollow",
  "target_name": "Ada Builder",
  "target_url": "https://peerlist.io/adabuilder",
  "reason": "peer_preserved"
}
```

## Safety Rules

- Fail closed if actor identity is unclear, logged out, or challenged.
- Do not unfollow mutual peers when `do_not_unfollow_peers` is true.
- Do not exceed daily caps.
- Do not unfollow profiles followed by the workflow until `unfollow_after_days` has elapsed.
- Verify state after every follow/unfollow action.
- Store enough target identity to avoid duplicate actions: profile URL, handle, name, relationship state, and first seen/followed timestamp.

## Implementation Notes

Use profile-level UI actions for actual follow/unfollow mutations. Prior Peerlist runs observed that direct follow API mutation can report success without reliable state change.

Discovery should be separate from mutation. Build a candidate set from Scroll, Launchpad, notifications, or search; then apply daily caps and relationship filters before clicking.

## Browser Use Cloud Agent Mode

Browser Use Cloud SDK v3 can run this workflow as a managed agent with a persistent profile and workspace:

```bash
python3 scripts/run_peerlist_follow_browser_use_agent.py \
  --profile-id "$BROWSER_USE_PROFILE_ID" \
  --workspace-id "$BROWSER_USE_WORKSPACE_ID" \
  --proxy-country-code de \
  --op-vault-id "$BROWSER_USE_1PASSWORD_VAULT_ID" \
  --max-cost-usd 1.00 \
  --report-output /tmp/peerlist-follow-report.json \
  --bundle-output /tmp/peerlist-follow-bundle.json
```

Required environment:

- `BROWSER_USE_API_KEY`
- `BROWSER_USE_PROFILE_ID`
- optional `BROWSER_USE_WORKSPACE_ID`
- optional `BROWSER_USE_MODEL` (default: `claude-sonnet-4.6`)
- optional `BROWSER_USE_PROXY_COUNTRY_CODE` (default: `de`)
- optional `BROWSER_USE_MAX_COST_USD`
- optional `BROWSER_USE_1PASSWORD_VAULT_ID`

The script defaults to dry-run mode and must be passed `--live` before it can perform follow or unfollow mutations.

If `BROWSER_USE_1PASSWORD_VAULT_ID` is configured, Browser Use can autofill Peerlist login and TOTP from the connected 1Password integration. Keep allowed domains narrow: default to `peerlist.io` and `*.peerlist.io`.

Use Browser Use Cloud Agent mode as the preferred remote-first workflow runner:

1. Create a Browser Use session with the saved Peerlist profile, Germany proxy, workspace, optional recording, and optional cost cap.
2. Run the workflow task with structured output so the SDK validates the report shape before PhantomClaw builds a bundle.
3. Stop the Browser Use session in cleanup so profile state persists.
4. Store the resulting `phantomclaw.run-bundle.v1` in Neon.
5. Enable `--cache-script` only after dry-run and live runs are stable.

Keep OpenClaw/CDP mode available for low-level debugging and deterministic Playwright fixes, but prefer the Cloud Agent runner for scheduled remote workflow execution.
