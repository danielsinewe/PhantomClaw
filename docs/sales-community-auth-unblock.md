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
