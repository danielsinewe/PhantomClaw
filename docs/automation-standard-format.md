# Automation Standard Format

PhantomClaw automations are reusable bundles. The hosted platform can remain private, but bundles should be open-source-like: inspectable, forkable, versioned, testable, and portable across cloud runtimes.

Every bundle should define:

- stable automation identity,
- parameter schema,
- required permissions/secrets,
- supported runtimes,
- safety gates,
- action-event types,
- north-star metric,
- fixtures and tests,
- dry-run and live-run examples.

Every PhantomClaw automation should produce a `phantomclaw.run-bundle.v1` payload with the same top-level sections:

```json
{
  "schema_version": "phantomclaw.run-bundle.v1",
  "generated_at": "2026-04-20T15:00:00+00:00",
  "source": {},
  "automation": {},
  "run": {},
  "metrics": {},
  "report": {}
}
```

## Automation Section

The automation section identifies the durable product contract, not one specific script implementation.

```json
{
  "name": "peerlist-follow-workflow",
  "label": "Peerlist Follow Workflow",
  "kind": "workflow",
  "platform": "peerlist",
  "surface": "network",
  "north_star_metric": "peerlist_profile_followers",
  "parameters": {
    "type": "follow",
    "follows_per_day": 20,
    "max_follows_per_run": 1,
    "unfollows_per_day": 1000,
    "max_unfollows_per_run": 1,
    "unfollow_after_days": 14,
    "do_not_unfollow_peers": true
  }
}
```

Standard fields:

- `name`: stable machine name.
- `label`: human-readable label.
- `kind`: `engagement` or `workflow`.
- `platform`: broad platform, for example `linkedin` or `peerlist`.
- `surface`: platform area, for example `scroll`, `network`, or `sales-community`.
- `north_star_metric`: nullable metric the workflow is ultimately trying to improve.
- `parameters`: normalized run parameters. Use `{}` when there are none.

## Run Section

```json
{
  "run_id": "peerlist-follow-123",
  "started_at": "2026-04-20T15:00:00+00:00",
  "finished_at": "2026-04-20T15:02:00+00:00",
  "status": "ok",
  "stop_reason": null,
  "profile_name": "Daniel",
  "action_events": [],
  "screenshot_path": "/path/to/screenshot.png"
}
```

Use fail-closed statuses:

- `ok`: at least one verified intended action happened.
- `no_action`: checks passed, but caps, duplicate guards, or target filters produced no action.
- `blocked`: a safeguard stopped execution before actions.
- `error`: the runner failed unexpectedly.

## Metrics Section

The shared columns power dashboards across all automations:

```json
{
  "items_scanned": 12,
  "items_considered": 3,
  "actions_total": 1,
  "likes_count": 0,
  "reposts_count": 0,
  "comments_liked_count": 0,
  "follows_count": 1,
  "metrics_json": {}
}
```

Platform-specific details go in `metrics_json`. For Peerlist follow workflow:

```json
{
  "north_star_metric": "peerlist_profile_followers",
  "peerlist_profile_followers_before": 473,
  "peerlist_profile_followers_after": 474,
  "peerlist_profile_followers_delta": 1,
  "automation_kind": "workflow",
  "workflow_type": "follow",
  "workflow_parameters": {
    "type": "follow",
    "follows_per_day": 20,
    "max_follows_per_run": 1,
    "unfollows_per_day": 1000,
    "max_unfollows_per_run": 1,
    "unfollow_after_days": 14,
    "do_not_unfollow_peers": true
  },
  "profiles_scanned": 12,
  "profiles_considered": 3,
  "follows_count": 1,
  "unfollows_count": 0,
  "peers_preserved_count": 0
}
```

Dashboard views should expose these Peerlist workflow fields as normal columns:

- `north_star_metric`
- `workflow_type`
- `peerlist_profile_followers_before`
- `peerlist_profile_followers_after`
- `peerlist_profile_followers_delta`
- `unfollows_count`
- `peers_preserved_count`
- `skipped_count`
- `blockers_count`

North-star metrics should also be captured as append-only timestamped absolute snapshots in a separate table:

```json
{
  "platform": "peerlist",
  "profile_name": "Daniel",
  "metric_name": "peerlist_profile_followers",
  "metric_date": "2026-04-20",
  "metric_value": 474,
  "captured_at": "2026-04-20T15:02:00+00:00",
  "source": "cron"
}
```

Use the per-run `metrics_json.peerlist_profile_followers_delta` for run attribution and debugging. Use `automation_daily_metrics_v1.captured_at_ts` for timestamped trend charts and north-star reporting. Use `metric_date` only when grouping snapshots by day.

## Action Events

Action events are the audit trail for verified mutations.

```json
{
  "type": "peerlist_profile_followed",
  "ts": "2026-04-20T15:01:00+00:00",
  "target_name": "Ada Builder",
  "target_url": "https://peerlist.io/adabuilder",
  "verified": true
}
```

Events should include:

- `type`
- `ts`
- target identity (`target_name`, `target_url`, or a platform-specific id)
- `verified`
- optional `reason`, `selector`, `target_excerpt`, or relationship state

The action drilldown view should expose `verified` as a boolean column and keep the full raw event in `action_event_json`.

## Report Section

`report` keeps the raw runner output for debugging and future migrations. It may include screenshots, browser provider diagnostics, skip lists, blockers, and discovery state. Dashboards should prefer normalized fields first and drill into `report_json` only when needed.

## Browser Use Cloud Agent Runner

For workflows that benefit from Browser Use's managed agent, persistent profile, workspace, stealth browser, and residential proxy, use the Browser Use Cloud SDK as an optional runner. Keep the API key in `BROWSER_USE_API_KEY`; never commit it.

```bash
python3 scripts/run_peerlist_follow_browser_use_agent.py \
  --profile-id "$BROWSER_USE_PROFILE_ID" \
  --workspace-id "$BROWSER_USE_WORKSPACE_ID" \
  --op-vault-id "$BROWSER_USE_1PASSWORD_VAULT_ID" \
  --max-cost-usd 1.00 \
  --report-output /tmp/peerlist-follow-report.json \
  --bundle-output /tmp/peerlist-follow-bundle.json
```

The runner defaults to dry-run mode. Add `--live` only when the profile is authenticated, the daily caps are correct, and the output bundle path is wired to storage.

When `--op-vault-id` is set, Browser Use may use the connected 1Password vault only for `peerlist.io` and `*.peerlist.io` unless additional `--allowed-domain` values are passed.

The Browser Use runner uses structured output and an explicit Browser Use session lifecycle. It creates a session with the saved profile, runs the task against that session, and stops the session in cleanup so profile state can persist.

Enable `--cache-script` only after the dry-run and live workflow are stable. Browser Use cached scripts can remove most LLM cost from repeat runs, but mutation workflows should be cached only after their guards and output validation are proven.
