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
  "max_follows_per_run": 1,
  "unfollows_per_day": 10,
  "unfollow_after_days": 14,
  "do_not_unfollow_peers": true,
  "active_window_start": "09:00",
  "active_window_end": "21:00",
  "min_delay_seconds": 45,
  "max_delay_seconds": 180,
  "error_backoff_seconds": 900,
  "candidate_pool_limit": 50,
  "require_verified_profile": false,
  "skip_existing_following": true,
  "skip_existing_followers": false,
  "skip_peers": true,
  "profile_blacklist": [],
  "profile_whitelist": []
}
```

Parameter notes:

- `type`: `follow`, `unfollow`, or `rebalance`.
- `follows_per_day`: maximum verified follow actions per calendar day.
- `max_follows_per_run`: maximum verified follow actions in one scheduler run.
- `unfollows_per_day`: maximum verified unfollow actions per calendar day.
- `max_unfollows_per_run`: maximum verified unfollow actions in one scheduler run.
- `unfollow_after_days`: earliest age for cleanup candidates followed by this workflow.
- `do_not_unfollow_peers`: when true, never unfollow mutual relationships. Peerlist calls mutual follows `peers`.
- `active_window_start` / `active_window_end`: normal activity window in local scheduler time.
- `min_delay_seconds` / `max_delay_seconds`: live mutation jitter.
- `candidate_pool_limit`: maximum discovery pool before filters and daily caps.
- `skip_existing_following`, `skip_existing_followers`, and `skip_peers`: relationship safety filters.
- `profile_blacklist` / `profile_whitelist`: explicit profile controls.

Launch frequency is separate from action caps. Match the Phantombuster-style preset model at the product layer:

- once
- once every other day, once per day, twice per day, 3/4/6/8 times per day
- once every other hour, once/twice/3/4 times per hour
- working-hours variants for 09:00-17:00, optionally excluding weekends
- advanced cron
- after another workflow

The verified Railway setup currently uses a conservative repeated launch: every two hours from 09:07 through 21:07 Europe/Berlin, with `follows_per_day=3`, `max_follows_per_run=1`, `unfollows_per_day=10`, and `max_unfollows_per_run=1`.

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

The current default Railway implementation uses Peerlist's authenticated app APIs because the same saved Peerlist session works from OpenClaw/Railway while hosted browser providers were unreliable during verification.

Observed API shape:

- actor / north-star count: `GET /api/v1/follows/count?includePeer=true`
- discovery: `GET /api/v2/scroll/feed?numUpvoteProfiles=3&numComments=2&newest=true`
- relationship check: `GET /api/v1/users/peers?id=<target_id>`
- follow: `POST /api/v1/users/follow` with `{"followerUsername":["<handle>"]}`
- unfollow: `POST /api/v1/users/unfollow` with `{"followerUsername":"<handle>"}`

Peerlist relationship direction is easy to misread. In the `users/peers?id=<target_id>` response, `follower` means the authenticated actor follows the target; `following` means the target follows the actor. Verify a follow by checking `follower` or `peer`/`isPeers` after the POST. Refresh relationship state by target ID before filtering because feed relationship booleans can be stale.

Discovery should be separate from mutation. Build a candidate set from Scroll, Launchpad, notifications, or search; then apply daily caps and relationship filters before clicking.

For any live mutation, verify state after the action. If API verification is ambiguous, fall back to a browser/profile-level check before counting the action as verified.

## Railway/OpenClaw Peerlist HTTP Mode

The verified remote runner is OpenClaw on Railway calling the Peerlist HTTP backend with saved Peerlist cookies:

```bash
/usr/local/bin/run-peerlist-follow-workflow.sh
```

Required Railway environment:

- `PEERLIST_BROWSER_BACKEND=peerlist-http`
- `PEERLIST_COOKIES_JSON`
- `AUTOMATION_ANALYTICS_DATABASE_URL`
- `PHANTOMCLAW_REPO_DIR=/opt/phantomclaw`
- `PHANTOMCLAW_WORKSPACE_SLUG=daniel-sinewe`
- `PEERLIST_FOLLOW_LIVE=0`
- `PEERLIST_SYNC_BLOCKED_RUNS=0`

The entrypoint defaults to dry-run mode. Use a capped proof run before enabling larger caps:

```bash
PEERLIST_FOLLOW_LIVE=1 PEERLIST_FOLLOWS_PER_DAY=1 \
  /usr/local/bin/run-peerlist-follow-workflow.sh
```

Verified 2026-04-21 from Railway/OpenClaw:

- deployment `027fe250-eb2b-4f7a-befd-ea9b81d0c2e3`: `SUCCESS`
- direct dry run `peerlist-follow-1776762903`: `status=no_action`, `actor_verified=true`, daily follower metric stored
- capped live run `peerlist-follow-1776762943`: `status=ok`, `actor_verified=true`, `follows_count=1`, `actions_total=1`
- verified action event: `peerlist_profile_followed` for `https://peerlist.io/jhayer`
- daily cap guard run `peerlist-follow-1776763893`: `status=no_action`, `daily_follows_before=3`, `daily_follows_remaining=0`, no mutation, Neon sync ok
- daily north-star metric: `peerlist_profile_followers=474`
- Neon confirmed:
  - `automation_runs` contains `peerlist-follow-1776762943`
  - `automation_action_events_v1` contains the verified follow event
  - `automation_daily_metrics` and `automation_daily_metrics_v1` contain the 2026-04-21 follower snapshot
- OpenClaw cron job `f3a3d7f8-a28d-4f82-b56d-4383f6ae485e` is enabled in live conservative mode: `PEERLIST_FOLLOW_LIVE=1 PEERLIST_FOLLOWS_PER_DAY=3 PEERLIST_MAX_FOLLOWS_PER_RUN=1`

Do not raise `PEERLIST_FOLLOWS_PER_DAY` or `PEERLIST_MAX_FOLLOWS_PER_RUN` until multiple days of action events and daily metrics look healthy.

## Browser Use Cloud Agent Mode

Browser Use Cloud SDK v3 can run this workflow as a managed agent with a persistent profile and workspace, but Peerlist navigation and provider credit/session availability were unreliable during Railway verification on 2026-04-21. Keep it as a fallback/debug path until that provider-side issue is resolved:

```bash
python3 scripts/run_peerlist_follow_browser_use_agent.py \
  --profile-id "$BROWSER_USE_PROFILE_ID" \
  --workspace-id "$BROWSER_USE_WORKSPACE_ID" \
  --proxy-country-code none \
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

Use OpenClaw on Railway as the preferred remote-first scheduler/orchestrator. From that Railway runtime, call Peerlist HTTP mode for scheduled workflow execution:

1. Railway/OpenClaw starts the scheduled command.
2. The command reads saved Peerlist cookies and verifies actor identity.
3. Discovery uses the authenticated Peerlist feed API.
4. Mutation uses the authenticated follow/unfollow API only when `PEERLIST_FOLLOW_LIVE=1`.
5. The command verifies relationship state after mutation.
5. The command stores the resulting `phantomclaw.run-bundle.v1`, action events, and daily north-star metric in Neon.

Keep Browser Use and OpenClaw/CDP browser actions available for low-level debugging, but prefer the Railway-hosted Peerlist HTTP command for scheduled Peerlist workflow execution.
