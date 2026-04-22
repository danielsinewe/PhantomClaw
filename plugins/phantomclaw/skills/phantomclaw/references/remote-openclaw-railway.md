# Remote OpenClaw On Railway

## Known State

- Railway project observed: `content-friendship`.
- Services observed: `OpenClaw`, `Paperclip`, `Postgres`.
- OpenClaw gateway observed in Codex Desktop:

```text
wss://openclaw-production-22d3d.up.railway.app/openclaw/
```

Gateway token auth was shown as connected in Codex Desktop. Do not expose, log, or commit the token.

## Codex Desktop Settings

Use:

- OpenClaw active: enabled.
- OpenClaw runs: `Remote (another host)`.
- Transport: `Direct (ws/wss)`.
- Gateway: Railway `wss://.../openclaw/` URL.
- Gateway token: configured locally in Codex Desktop.

`ws://` is only appropriate for localhost or trusted tunnels. Railway remote hosts should use `wss://`.

## Railway Requirements

Remote browser automation needs more than a reachable websocket:

- A browser runtime available inside the OpenClaw service.
- Persistent profile storage if logins must survive restarts or deploys.
- Environment variables for gateway auth and runtime configuration.
- Service logs that make auth drift, challenge pages, and browser launch failures visible.
- A health or gateway test path that can be checked before scheduling jobs.

For Peerlist, the verified runtime is OpenClaw on Railway orchestrating the authenticated Peerlist HTTP backend with saved Peerlist cookies. Railway remains the OpenClaw gateway host and scheduler/orchestrator. Browser Use CLI, Browser Use Cloud SDK/CDP, Browserbase CDP, and OpenClaw browser actions remain fallback/debug paths, but provider credits, tunnels, or session availability were unreliable during 2026-04-21 verification.

## Peerlist Remote Runtime

Use the Railway/OpenClaw entrypoint:

```bash
/usr/local/bin/run-peerlist-follow-workflow.sh
```

Expected Railway variables:

```bash
PEERLIST_BROWSER_BACKEND=peerlist-http
PEERLIST_COOKIES_JSON=...
AUTOMATION_ANALYTICS_DATABASE_URL=...
PHANTOMCLAW_REPO_DIR=/opt/phantomclaw
PHANTOMCLAW_WORKSPACE_SLUG=daniel-sinewe
PEERLIST_FOLLOW_LIVE=0
PEERLIST_SYNC_BLOCKED_RUNS=0
```

Verified 2026-04-21:

- deployment `027fe250-eb2b-4f7a-befd-ea9b81d0c2e3`: `SUCCESS`
- direct dry run `peerlist-follow-1776762903`: `status=no_action`, authenticated actor verified, candidates discovered, Neon run row stored, daily metric stored
- capped live run `peerlist-follow-1776762943`: `status=ok`, authenticated actor verified, one verified follow, Neon run row stored, action event stored, daily metric stored
- verified live action event: `peerlist_profile_followed` for `https://peerlist.io/jhayer`
- daily cap guard run `peerlist-follow-1776763893`: `status=no_action`, `daily_follows_before=3`, `daily_follows_remaining=0`, no mutation, Neon sync ok
- daily north-star metric: `peerlist_profile_followers=474`
- OpenClaw cron job `f3a3d7f8-a28d-4f82-b56d-4383f6ae485e` is enabled in live conservative mode:
  - schedule: every two hours from 09:07 through 21:07 Europe/Berlin
  - command: `PEERLIST_FOLLOW_LIVE=1 PEERLIST_FOLLOWS_PER_DAY=3 PEERLIST_MAX_FOLLOWS_PER_RUN=1 PEERLIST_UNFOLLOWS_PER_DAY=10 PEERLIST_MAX_UNFOLLOWS_PER_RUN=1 /usr/local/bin/run-peerlist-follow-workflow.sh`
  - Railway health check after restart returned `{"ok":true,"status":"live"}`

Do not raise `PEERLIST_FOLLOWS_PER_DAY`, `PEERLIST_MAX_FOLLOWS_PER_RUN`, `PEERLIST_UNFOLLOWS_PER_DAY`, or `PEERLIST_MAX_UNFOLLOWS_PER_RUN` until multiple days of action events and timestamped metrics look healthy.

## Browser Use Remote CDP Fallback

Browser Use Cloud can be attached to OpenClaw as a normal remote CDP profile. Keep it configured for debugging and future retry once provider-side Peerlist tunnel behavior improves.

Recommended private OpenClaw config shape:

```json
{
  "browser": {
    "enabled": true,
    "defaultProfile": "browser-use",
    "remoteCdpTimeoutMs": 3000,
    "remoteCdpHandshakeTimeoutMs": 5000,
    "profiles": {
      "browser-use": {
        "cdpUrl": "wss://connect.browser-use.com?apiKey=<BROWSER_USE_API_KEY>&proxyCountryCode=none&timeout=240",
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

Add `profileId=<PROFILE_ID>` after the Browser Use profile has been logged in and verified. Browser Use profile state persists cookies and localStorage; stop sessions cleanly when using the SDK/API so profile state is saved.

Current Browser Use Cloud state observed on April 21, 2026:

- `BROWSER_USE_API_KEY`, `BROWSER_USE_CDP_URL`, and `BROWSER_USE_PROFILE_ID` are configured in Vercel for `phantomclaw-ai` across Production, Preview, and Development.
- The selected Browser Use profile is named `Personal Profile` and has `peerlist.io` cookies.
- Railway OpenClaw has a `browser-use` CDP profile applied in `/data/.openclaw/openclaw.json`, with `browser.defaultProfile` set to `browser-use`.
- Browser Use SDK and CDP reach session creation/start, but Peerlist navigation fails with `ERR_TUNNEL_CONNECTION_FAILED`.
- For Peerlist actions, use `/usr/local/bin/run-peerlist-follow-workflow.sh` with `PEERLIST_BROWSER_BACKEND=peerlist-http`.

Verification sequence:

```bash
openclaw browser --browser-profile browser-use start
openclaw browser --browser-profile browser-use tabs
openclaw browser --browser-profile browser-use open https://example.com
openclaw browser --browser-profile browser-use snapshot
```

For Railway-hosted OpenClaw, run the same sequence over SSH:

```bash
railway ssh -s OpenClaw -- 'openclaw browser --browser-profile browser-use open https://example.com && openclaw browser --browser-profile browser-use snapshot'
```

Cron jobs currently use the loopback browser HTTP API instead:

```bash
railway ssh -s OpenClaw -- 'TOKEN=$(node -e "const fs=require(\"fs\");const c=JSON.parse(fs.readFileSync(\"/data/.openclaw/openclaw.json\",\"utf8\")); console.log(c.gateway?.auth?.token || c.gateway?.token || \"\")")
AUTH="authorization: Bearer $TOKEN"
curl -sS -X POST -H "$AUTH" "http://127.0.0.1:18791/stop?profile=browser-use"
curl -sS -X POST -H "$AUTH" "http://127.0.0.1:18791/start?profile=browser-use"
curl -sS -X POST -H "$AUTH" -H "content-type: application/json" --data "{\"url\":\"https://peerlist.io/scroll\"}" "http://127.0.0.1:18791/tabs/open?profile=browser-use"
curl -sS -H "$AUTH" "http://127.0.0.1:18791/snapshot?profile=browser-use&format=aria&limit=200"'
```

For the current Peerlist cron, the stable action path is:

```bash
PEERLIST_BROWSER_BACKEND=peerlist-http \
  PEERLIST_FOLLOW_LIVE=0 \
  /usr/local/bin/run-peerlist-follow-workflow.sh
```

Run a Browser Use CLI session smoke test:

```bash
/usr/local/bin/peerlist-browser-use-cli-smoke.sh
```

Run one capped live proof:

```bash
PEERLIST_BROWSER_BACKEND=peerlist-http \
  PEERLIST_FOLLOW_LIVE=1 \
  PEERLIST_FOLLOWS_PER_DAY=1 \
  /usr/local/bin/run-peerlist-follow-workflow.sh
```

If `gateway.nodes.browser` is left in proxy mode with a pinned local node, OpenClaw may route browser calls to a Mac node instead of the remote CDP profile. Disable node browser routing for the Browser Use path unless a node proxy is intentionally required.

## Railway-Local Browser Runtime Fix

The current Railway OpenClaw service is deployed from the image:

```text
colemandunn/openclaw_railway_optimized
```

It is not connected to a source repo in Railway. A remote diagnosis on April 20, 2026 found:

- no `google-chrome`, `google-chrome-stable`, `chromium`, `chromium-browser`, Brave, or Edge binary,
- `playwright-core` exists, but no Playwright browser payloads are installed,
- no browser-related env var points OpenClaw at a binary,
- `/data` is mounted and persistent, so browser profile persistence is available after the browser runtime is fixed.

For Railway/Linux local-browser fallback, prefer a real Google Chrome `.deb` install over snap Chromium. Snap Chromium is not suitable for OpenClaw-managed browser spawning because AppArmor/snap confinement interferes with process launch and monitoring.

Recommended OpenClaw browser config:

```json
{
  "browser": {
    "enabled": true,
    "executablePath": "/usr/bin/google-chrome-stable",
    "headless": true,
    "noSandbox": true
  }
}
```

Container image requirements:

```dockerfile
RUN apt-get update \
  && apt-get install -y --no-install-recommends wget ca-certificates fonts-liberation \
  && wget -O /tmp/google-chrome-stable_current_amd64.deb https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb \
  && apt-get install -y /tmp/google-chrome-stable_current_amd64.deb \
  && rm -rf /var/lib/apt/lists/* /tmp/google-chrome-stable_current_amd64.deb
```

After redeploy, verify inside the remote host:

```bash
command -v google-chrome-stable
google-chrome-stable --version
curl -s http://127.0.0.1:18791/ | jq '{running, pid, chosenBrowser}'
curl -s -X POST http://127.0.0.1:18791/start
curl -s http://127.0.0.1:18791/tabs
```

If using attach-only mode instead, OpenClaw should not launch the browser itself:

```json
{
  "browser": {
    "enabled": true,
    "attachOnly": true,
    "headless": true,
    "noSandbox": true
  }
}
```

The container must then start Chrome separately with CDP enabled:

```bash
google-chrome-stable --headless --no-sandbox --disable-gpu \
  --remote-debugging-port=18800 \
  --user-data-dir=/data/.openclaw/browser/openclaw/user-data \
  about:blank
```

## Operational Pattern

1. Verify Railway context before changes.
2. Check `OpenClaw` service health and logs.
3. Confirm Codex Desktop can connect with the gateway token.
4. Run a low-risk browser task first, such as opening a page and returning the title.
5. For authenticated platforms, verify the logged-in actor before actions.
6. Run capped automations with jitter and skip rules.
7. Save concise run logs.

## Failure Modes

- Browser profile missing: remote browser opens logged out.
- No persistent storage: login disappears after redeploy.
- Bad gateway token: Codex shows disconnected or unauthorized.
- Wrong transport: `ws://` fails or is blocked for remote Railway host.
- Anti-automation challenge: stop the run and report challenge signals.
- Page shape drift: stop instead of guessing selectors.
