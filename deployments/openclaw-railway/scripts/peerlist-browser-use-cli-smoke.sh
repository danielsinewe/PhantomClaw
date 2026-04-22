#!/usr/bin/env bash
set -euo pipefail

SESSION="${BROWSER_USE_CLI_SESSION:-peerlist-cli}"
COOKIE_FILE="${BROWSER_USE_CLI_COOKIE_FILE:-/tmp/peerlist-browser-use-cookies.json}"
CDP_URL="${BROWSER_USE_CLI_CDP_URL:-}"

if [ -z "$CDP_URL" ]; then
  if [ -n "${BROWSER_USE_API_KEY:-}" ] && [ -n "${BROWSER_USE_PROFILE_ID:-}" ]; then
    CDP_URL="wss://connect.browser-use.com?apiKey=${BROWSER_USE_API_KEY}&profileId=${BROWSER_USE_PROFILE_ID}&proxyCountryCode=${BROWSER_USE_PROXY_COUNTRY_CODE:-de}&timeout=${BROWSER_USE_TIMEOUT_MINUTES:-30}"
  elif [ -n "${BROWSERBASE_API_KEY:-}" ]; then
    CDP_URL="wss://connect.browserbase.com?apiKey=${BROWSERBASE_API_KEY}"
  else
    CDP_URL="${BROWSER_USE_CDP_URL:?BROWSER_USE_CDP_URL, BROWSER_USE_API_KEY+BROWSER_USE_PROFILE_ID, or BROWSERBASE_API_KEY is required}"
  fi
fi

if [ -z "${PEERLIST_COOKIES_JSON:-}" ]; then
  echo "PEERLIST_COOKIES_JSON is required" >&2
  exit 1
fi

printf '%s' "$PEERLIST_COOKIES_JSON" > "$COOKIE_FILE"

browser-use --session "$SESSION" close >/dev/null 2>&1 || true
browser-use --session "$SESSION" --cdp-url "$CDP_URL" open about:blank >/dev/null
browser-use --session "$SESSION" cookies import "$COOKIE_FILE" >/dev/null
browser-use --session "$SESSION" open https://peerlist.io/scroll >/dev/null

python3 - <<'PY' "$SESSION"
import json
import subprocess
import sys

session = sys.argv[1]

def run(*args: str) -> str:
    return subprocess.check_output(["browser-use", "--session", session, *args], text=True)

title = run("get", "title").strip()
text = run(
    "eval",
    "document.body.innerText.slice(0, 2000)",
)
actor_verified = (
    "Daniel" in text
    and "followers" in text
    and "following" in text
    and "Log in" not in text
    and "Sign in" not in text
)
print(json.dumps({
    "backend": "browser-use-cli",
    "title": title,
    "actor_verified": actor_verified,
    "has_composer": "What are you working on" in text or "Ask a question to the community" in text,
    "has_login": "Log in" in text or "Sign in" in text,
}, indent=2, sort_keys=True))
if not actor_verified:
    raise SystemExit(2)
PY
