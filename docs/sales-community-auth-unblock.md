# LinkedIn Sales Community auth unblock

The `linkedin-sales-community` automation is intentionally paused while
`https://scommunity.linkedin.com/` resolves to the public Club Navigator page
instead of an authenticated community surface.

Current expected blocker:

- Automation id: `linkedin-sales-community`
- Registry state: `PAUSED`
- Pause reason: `sales_community_auth_required`
- Safe activation command: `scripts/sales_community_auth_activation.py`

## Verify the blocker

Run the canonical completion audit:

```bash
railway run uv run python scripts/phantomclaw_completion_audit.py
```

The current blocked state is:

```json
{
  "status": "blocked_sales_community_auth",
  "ok": false
}
```

The only failing check should be `no_paused_native_automations`, with
`linkedin-sales-community` paused for `sales_community_auth_required`.

## Check the browser profile

Use the real Chrome profile expected by the runner:

```bash
browser-use --profile "danielsinewe.com" open https://scommunity.linkedin.com/
browser-use --profile "danielsinewe.com" state
browser-use close --all
```

Do not activate the automation if the page still shows `Login`,
`Customer Login | Register`, or the public `Join the club` copy.

Known login paths observed on the public page:

- `https://scommunity.linkedin.com/ssoproxy/login?ssoType=openidconnect`
- `https://scommunity.linkedin.com/sso/login?ssoType=linkedin`

Both paths can legitimately stop at the LinkedIn password screen for
`hello@danielsinewe.com`. Treat that as a credential boundary, not an automation
bug.

## Activate after access is restored

After the browser profile reaches the authenticated community surface, run the
guarded activation. It performs a zero-action live check first by using
`--like-cap 0`; it only updates the registry after the report is clean.

```bash
railway run uv run python scripts/sales_community_auth_activation.py --activate
```

Successful activation requires:

- `ready: true`
- runner report `status: ok`
- `page_shape_ok: true`
- no `stop_reason`

Then rerun:

```bash
railway run uv run python scripts/phantomclaw_completion_audit.py
```

The objective is complete only when this audit returns `status: complete`.

## Resolution evidence, 2026-05-18

After authenticating the local `danielsinewe.com` Chrome profile, the first
guarded activation attempt still failed because Railway environment variables
selected the configured Browser Use cloud/CDP profile instead of the local
Chrome profile. The activation was rerun with those browser overrides unset and
`LINKEDIN_SALES_COMMUNITY_ENGAGEMENT_PROFILE=danielsinewe.com`.

The zero-action guard passed:

```json
{
  "ready": true,
  "reason": "activation_ready",
  "check": {
    "status": "ok",
    "stop_reason": null,
    "page_shape_ok": true,
    "items_scanned": 10,
    "items_considered": 3
  }
}
```

Activation then updated the registry and synced Neon:

```json
{
  "activated": true,
  "registry_update": {
    "automation_id": "linkedin-sales-community",
    "status": "ACTIVE",
    "source_status": "ACTIVE",
    "live_enabled": true
  },
  "neon_sync": {
    "synced": true,
    "upserted_count": 4,
    "pruned_count": 0
  }
}
```

The completion audit now returns:

```json
{
  "status": "complete",
  "ok": true
}
```
