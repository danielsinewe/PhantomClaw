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

For third-party sites with Cloudflare or similar bot protection, the preferred browser runtime is now Browser Use remote CDP, not Railway-local headless Chrome. Railway remains the OpenClaw gateway host, while the browser itself runs in Browser Use cloud infrastructure.

## Browser Use Remote CDP

Browser Use can be attached to OpenClaw as a normal remote CDP profile. This avoids Railway datacenter headless Chrome as the acting browser and gives the automation access to Browser Use stealth infrastructure, residential proxies, and persistent browser profiles.

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

Add `profileId=<PROFILE_ID>` after the Browser Use profile has been logged in and verified. Browser Use profile state persists cookies and localStorage; stop sessions cleanly when using the SDK/API so profile state is saved.

Current Browser Use state observed on April 20, 2026:

- `BROWSER_USE_API_KEY`, `BROWSER_USE_CDP_URL`, and `BROWSER_USE_PROFILE_ID` are configured in Vercel for `phantomclaw-ai` across Production, Preview, and Development.
- The selected Browser Use profile is named `Personal Profile` and has `peerlist.io` cookies.
- A profile-backed Browser Use CDP session was verified locally by opening `https://example.com` and reading page state through the Browser Use CLI.
- Railway OpenClaw has the same `browser-use` CDP profile applied in `/data/.openclaw/openclaw.json`, with `browser.defaultProfile` set to `browser-use` and node browser proxy routing disabled.
- Direct loopback browser API checks on Railway verified that `browser-use` starts, reaches CDP, opens `https://example.com`, opens `https://peerlist.io/scroll`, and returns an authenticated Peerlist snapshot.
- The `openclaw browser ...` CLI path can still time out against the local gateway websocket on Railway. Use the loopback browser HTTP API for cron jobs until the CLI gateway timeout is fixed.
- For Peerlist actions, use the direct Browser Use Playwright runner at `/data/workspace/scripts/peerlist-browser-use-direct.mjs`. OpenClaw's loopback browser API is reliable for start/navigate/snapshot, but `/act` ref actions against Browser Use CDP were observed to lose the target mid-run.

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
NODE_PATH=/opt/openclaw/node_modules/.pnpm/playwright@1.58.2/node_modules:/opt/openclaw/node_modules/.pnpm/playwright-core@1.58.2/node_modules \
  PEERLIST_MAX_UPVOTES=1 \
  node /data/workspace/scripts/peerlist-browser-use-direct.mjs
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
