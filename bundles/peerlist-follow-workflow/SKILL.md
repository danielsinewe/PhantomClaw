---
name: peerlist-follow-workflow
description: Run, debug, or adapt the PhantomClaw Peerlist follow/unfollow workflow bundle. Use when configuring Peerlist audience-growth automation, checking follow/unfollow safety gates, verifying Peerlist follower north-star metrics, or preparing remote OpenClaw/Railway runs.
---

# Peerlist Follow/Unfollow Workflow

## Purpose

Use this bundle to grow an authenticated Peerlist profile's own follower count through conservative follow/unfollow actions.

North-star metric:

```text
peerlist_profile_followers
```

## Runtime

Verified runtime:

```text
OpenClaw on Railway -> peerlist-http backend -> run bundle -> Neon analytics
```

Preferred entrypoint:

```bash
/usr/local/bin/run-peerlist-follow-workflow.sh
```

## Defaults

- `follows_per_day`: 3
- `max_follows_per_run`: 1
- `unfollows_per_day`: 10
- `max_unfollows_per_run`: 1
- `unfollow_source`: `workflow_history`
- `unfollow_after_days`: 14
- `do_not_unfollow_peers`: true
- `do_not_unfollow_followers`: true
- `skip_existing_following`: true
- `skip_existing_followers`: false
- `skip_peers`: true

## Safety Rules

- Start with dry-run mode.
- Only run live when `PEERLIST_FOLLOW_LIVE=1` is explicit.
- Enforce daily caps from `automation_action_events_v1`.
- Enforce per-run caps locally.
- Verify actor identity before mutation.
- Verify every follow/unfollow after mutation.
- Never target or unfollow mutual peers when peer preservation is enabled.
- For historical account cleanup, use `unfollow_source=current_following` only after a dry-run verifies candidate relationships.
- Stop on auth drift, Cloudflare/challenge pages, unclear relationship state, or missing cap storage.

## Commands

Dry run:

```bash
PEERLIST_BROWSER_BACKEND=peerlist-http \
PEERLIST_FOLLOW_LIVE=0 \
/usr/local/bin/run-peerlist-follow-workflow.sh
```

Live conservative:

```bash
PEERLIST_BROWSER_BACKEND=peerlist-http \
PEERLIST_FOLLOW_LIVE=1 \
PEERLIST_FOLLOWS_PER_DAY=3 \
PEERLIST_MAX_FOLLOWS_PER_RUN=1 \
/usr/local/bin/run-peerlist-follow-workflow.sh
```

## Expected Evidence

After a successful live run, verify:

- `automation_runs.status = ok`
- `automation_action_events_v1.action_type = peerlist_profile_followed`
- `automation_action_events_v1.verified = true`
- `automation_daily_metrics_v1.metric_name = peerlist_profile_followers`
- `automation_daily_metrics_v1.metric_name = peerlist_profile_following` when an unfollow run changes the following count

If the daily cap is already reached, expect:

- `status = no_action`
- `follows_count = 0`
- skipped row with `type = daily_follow_cap_reached`
- daily metric still synced
