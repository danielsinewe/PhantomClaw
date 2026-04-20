---
name: phantomclaw
description: Use when working on PhantomClaw/OpenClaw remote browser automation, Railway-hosted gateways, run-bundle sync, remote Codex cron jobs, or compliance-aware platform automations such as Peerlist.
---

# PhantomClaw

## When To Use

Use this skill when the user mentions PhantomClaw, OpenClaw, Railway-hosted browser automation, remote Codex automations, run bundles, PhantomClaw Cloud, `phantomclaw-cli`, or moving local automations to a remote OpenClaw gateway.

## Current Operating Model

PhantomClaw is split into three surfaces:

- `phantomclaw`: public automation core in `/Users/danielsinewe/Documents/GitHub/Automations`.
- `phantomclaw-cli`: private authenticated CLI for login, workspace selection, and run-bundle sync.
- `phantomclaw.ai`: private control plane for account, dashboard, and hosted storage.

OpenClaw is the browser gateway/runtime that can run locally or remotely. The current Railway inventory includes a `content-friendship` project with `OpenClaw`, `Paperclip`, and `Postgres` services. The observed remote gateway is:

```text
wss://openclaw-production-22d3d.up.railway.app/openclaw/
```

Never print or commit the gateway token. Treat it as a secret.

## Remote Automation Checklist

Before running a remote automation:

1. Confirm Codex Desktop has OpenClaw active and is set to `Remote (another host)`.
2. Confirm transport is `Direct (ws/wss)` for Railway and uses `wss://`.
3. Test the remote gateway and verify token auth succeeds.
4. Confirm the selected remote browser profile has an authenticated platform session.
5. Prefer Browser Use remote CDP for third-party sites with bot protection; use Railway-local Chrome only for low-risk/internal pages or debugging.
6. Use strict caps, jitter, and fail-closed checks.
7. Return concise run logs with links, actions, and skip reasons.

## Railway Notes

Prefer the Railway CLI for operational checks:

```bash
railway whoami --json
railway project list --json
railway service status --all --json
railway logs --service OpenClaw --lines 200 --json
railway variable list --service OpenClaw --json
```

Do not mutate Railway configuration until the target project, environment, and service are clear. For destructive changes, confirm with the user first.

## Peerlist Remote Automation Rules

For Peerlist, apply the Peerlist compliance gate before any action:

- Do not send unsolicited DMs asking for upvotes.
- Do not ask for upvotes in comments or replies.
- Do not spam reposts or repeatedly reshare launch links.
- Do not publish link-only Scroll posts.
- Prefer feedback, critique, questions, product context, and constructive engagement.

Safe recurring engagement defaults:

- Engage with 2-4 posts per run.
- Use different creators in one run.
- Mix likes/upvotes and at most one thoughtful comment.
- Add randomized delays between actions.
- Skip low-signal, sensitive, ambiguous, or repetitive opportunities.

Safe publishing default:

- Draft first; do not publish unless the user explicitly approves.
- Use an approved Scroll context such as `#show` or `#ask`.
- Include one concrete build detail.
- Ask for feedback, not upvotes.

## First-Class Runner Path

The public automation repo currently has LinkedIn runners and the `phantomclaw.run-bundle.v1` export seam. A first-class Peerlist runner should be added later under a dedicated `peerlist/` package with:

- platform-specific config and state modules,
- fail-closed browser shape checks,
- authenticated session verification,
- capped action execution,
- report JSON artifacts,
- metrics adapter and run-bundle support,
- tests with fixtures before live execution.

Until that exists, use Codex Cron plus remote OpenClaw browser automation for Peerlist.

## Browser Use Remote CDP

For remote browser automations, especially Peerlist or other Cloudflare-protected sites, use Browser Use as the primary browser runtime instead of Railway-hosted headless Chrome. Browser Use provides a remote CDP endpoint, stealth browser infrastructure, residential proxies, live preview, and persistent profile support.

Configure OpenClaw with a `browser-use` profile and make it the default remote browser:

```json
{
  "browser": {
    "enabled": true,
    "defaultProfile": "browser-use",
    "remoteCdpTimeoutMs": 3000,
    "remoteCdpHandshakeTimeoutMs": 5000,
    "profiles": {
      "browser-use": {
        "cdpUrl": "wss://connect.browser-use.com?apiKey=<BROWSER_USE_API_KEY>&proxyCountryCode=us&timeout=240",
        "color": "#ff750e"
      }
    }
  },
  "gateway": {
    "nodes": {
      "browser": {
        "mode": "off"
      }
    }
  }
}
```

Use a `profileId` query parameter once a logged-in Browser Use profile exists:

```text
wss://connect.browser-use.com?apiKey=<BROWSER_USE_API_KEY>&profileId=<PROFILE_ID>&proxyCountryCode=us&timeout=240
```

Never commit real Browser Use API keys, CDP URLs, gateway tokens, or profile IDs. Store app-facing values in Vercel/Railway environment variables and keep OpenClaw runtime config private.

## Run-Bundle Contract

The OSS core exports `phantomclaw.run-bundle.v1` via:

```bash
.venv/bin/python scripts/export_run_bundle.py --automation-name <name> --report-path <path>
```

Hosted PhantomClaw should receive bundles through `phantomclaw-cli`, not direct OSS writes into the managed database. Direct database URLs are self-hosted mode.

## Remote Peerlist Prompt Template

```text
Run a Peerlist Scroll engagement session through the authenticated remote OpenClaw browser.

Follow Peerlist compliance strictly:
- Do not send DMs.
- Do not ask for upvotes.
- Do not comment asking for votes.
- Do not spam reposts or repeated launch links.
- Do not publish link-only posts.

Engage with 2-4 high-signal Scroll posts from different creators. Mix likes/upvotes and at most one thoughtful comment. Comments must be specific to the post, such as a UX detail, implementation tradeoff, metric, or useful next step. Add randomized delays between actions. Skip low-signal, promotional, sensitive, or unclear posts. Return a concise run log with links, actions taken, and skip reasons.
```

## Peerlist Follow Workflow

Use `references/peerlist-follow-workflow.md` for the first Peerlist workflow automation contract:

- automation name: `peerlist-follow-workflow`
- platform: `peerlist`
- surface: `network`
- north-star metric: `peerlist_profile_followers`
- parameters: follow/unfollow type, daily caps, unfollow age, and peer-preservation behavior
