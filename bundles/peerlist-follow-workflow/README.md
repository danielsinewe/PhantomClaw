# Peerlist Follow/Unfollow

`peerlist-follow-workflow` is the first canonical PhantomClaw automation bundle.

Goal: grow the authenticated user's own Peerlist follower count through conservative, verified follow/unfollow operations.

North-star metric:

```text
peerlist_profile_followers
```

## Current Runtime

Verified runtime:

```text
OpenClaw on Railway
  -> /usr/local/bin/run-peerlist-follow-workflow.sh
  -> scripts/run_peerlist_follow_http.py
  -> phantomclaw.run-bundle.v1
  -> Neon/Postgres analytics
```

The current production backend uses authenticated Peerlist HTTP APIs with saved cookies. Browser Use Cloud, Browserbase, and OpenClaw browser profiles remain fallback/debug runtimes.

## Default Parameters

```json
{
  "type": "follow",
  "follows_per_day": 3,
  "max_follows_per_run": 1,
  "unfollows_per_day": 10,
  "max_unfollows_per_run": 1,
  "unfollow_source": "workflow_history",
  "unfollow_after_days": 14,
  "do_not_unfollow_peers": true,
  "do_not_unfollow_followers": true,
  "active_window_start": "09:00",
  "active_window_end": "21:00",
  "candidate_pool_limit": 50,
  "skip_existing_following": true,
  "skip_existing_followers": false,
  "skip_peers": true
}
```

## Safety Rules

- Dry-run is the default.
- Live mode requires `PEERLIST_FOLLOW_LIVE=1`.
- Daily follow/unfollow caps are enforced from `automation_action_events_v1`.
- Per-run caps are enforced with `max_follows_per_run` and `max_unfollows_per_run`.
- Every follow/unfollow must be verified after mutation.
- Mutual peers are preserved.
- Actor identity must be verified before mutation.
- Challenge/CAPTCHA or unclear auth blocks the run.

## Run

Dry run:

```bash
PEERLIST_BROWSER_BACKEND=peerlist-http \
PEERLIST_FOLLOW_LIVE=0 \
/usr/local/bin/run-peerlist-follow-workflow.sh
```

Conservative live run:

```bash
PEERLIST_BROWSER_BACKEND=peerlist-http \
PEERLIST_FOLLOW_LIVE=1 \
PEERLIST_FOLLOWS_PER_DAY=3 \
PEERLIST_MAX_FOLLOWS_PER_RUN=1 \
/usr/local/bin/run-peerlist-follow-workflow.sh
```

## Outputs

Each run emits:

- `phantomclaw.run-bundle.v1`
- `automation_runs` row
- `automation_action_events_v1` rows for verified mutations
- append-only `automation_daily_metrics_v1` snapshot rows for `peerlist_profile_followers` and `peerlist_profile_following`

## Verified State

Verified on 2026-04-21:

- Railway/OpenClaw live run `peerlist-follow-1776762943` completed with `status=ok`.
- One verified follow action was stored.
- Daily follower metric was stored as `peerlist_profile_followers=474`.
- Daily cap guard prevented extra follows after the configured cap was reached.
- Current-following cleanup was verified on Railway/OpenClaw on 2026-04-21 with 100 verified unfollows and live following count moving from 9911 to 9811.
