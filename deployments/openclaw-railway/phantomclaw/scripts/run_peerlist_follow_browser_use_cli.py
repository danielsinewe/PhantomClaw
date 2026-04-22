#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

PACKAGE_ROOT = Path(__file__).resolve().parent.parent
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

from automation_catalog import PEERLIST_FOLLOW_WORKFLOW, automation_default_parameters
from phantomclaw_bundle import build_run_bundle


SEARCH_URL = "https://peerlist.io/search"
CHALLENGE_PATTERN = re.compile(
    r"Cloudflare|captcha|verify you are human|checking your browser|access denied",
    re.I,
)


DISCOVER_JS = r"""
(() => {
  const bodyText = document.body.innerText || "";
  const followerMatch = bodyText.match(/([0-9][0-9,.\u00a0 ]*)\s*followers/i);
  const followers = followerMatch
    ? Number((followerMatch[1] || "").replace(/[^0-9]/g, ""))
    : null;
  const buttons = Array.from(document.querySelectorAll("button"))
    .filter((button) => /^Follow$/i.test((button.innerText || "").trim()))
    .filter((button) => {
      const rect = button.getBoundingClientRect();
      return rect.width > 0 && rect.height > 0;
    });
  const candidates = buttons.slice(0, 50).map((button, index) => {
    let card = button;
    for (let depth = 0; card && depth < 8; depth += 1) {
      const text = (card.innerText || "").replace(/\s+/g, " ").trim();
      if (text.length > 45 && /Follow|Following|Peers?/i.test(text)) break;
      card = card.parentElement;
    }
    card = card || button.parentElement || button;
    const text = (card.innerText || "").replace(/\s+/g, " ").trim();
    const links = Array.from(card.querySelectorAll('a[href^="/"]'));
    const profileLink = links.find((link) => {
      const href = link.getAttribute("href") || "";
      const normalized = href.replace(/\/$/, "");
      return /^\/[A-Za-z0-9_.-]+\/?$/.test(href)
        && !["/search", "/scroll", "/launchpad", "/articles", "/jobs", "/network"].includes(normalized);
    });
    const profileText = profileLink
      ? (profileLink.innerText || profileLink.textContent || "").replace(/\s+/g, " ").trim()
      : "";
    const lines = text.split(/\s{2,}|\n/).map((line) => line.trim()).filter(Boolean);
    const targetName = profileText || lines.find((line) =>
      line && !/^(Follow|Following|Peer|Peers|People|Visit)$/i.test(line)
    ) || `Peerlist profile ${index}`;
    return {
      type: "follow",
      target_name: targetName.slice(0, 160),
      target_url: profileLink ? profileLink.href : null,
      target_excerpt: text.slice(0, 500),
      selector: `browser-use-cli:button-follow:${index}`,
      verified: false
    };
  });
  return JSON.stringify({
    url: location.href,
    title: document.title,
    body_text: bodyText.slice(0, 4000),
    followers,
    candidates
  });
})()
"""


CLICK_FOLLOW_JS = r"""
(() => {
  const button = Array.from(document.querySelectorAll("button"))
    .find((candidate) => /^Follow$/i.test((candidate.innerText || "").trim()));
  if (!button) return JSON.stringify({clicked: false, reason: "follow_button_missing"});
  button.scrollIntoView({block: "center", inline: "center"});
  button.click();
  return JSON.stringify({clicked: true});
})()
"""


VERIFY_FOLLOW_JS = r"""
(() => {
  const labels = Array.from(document.querySelectorAll("button"))
    .map((button) => (button.innerText || "").trim())
    .filter(Boolean);
  return JSON.stringify({
    labels,
    verified: labels.some((label) => /^(Following|Peer|Peers)$/i.test(label))
  });
})()
"""


def run_command(args: list[str], timeout: int = 120) -> str:
    result = subprocess.run(args, check=True, capture_output=True, text=True, timeout=timeout)
    return result.stdout.strip()


def browser_use(session: str, *args: str, cdp_url: str | None = None, timeout: int = 120) -> str:
    command = ["browser-use", "--session", session]
    if cdp_url:
        command.extend(["--cdp-url", cdp_url])
    command.extend(args)
    return run_command(command, timeout=timeout)


def extract_json(output: str) -> dict[str, Any]:
    stripped = output.strip()
    for candidate in (stripped, stripped[stripped.find("{") : stripped.rfind("}") + 1]):
        if candidate:
            try:
                parsed = json.loads(candidate)
                if isinstance(parsed, str):
                    parsed = json.loads(parsed)
                if isinstance(parsed, dict):
                    return parsed
            except json.JSONDecodeError:
                pass
    raise ValueError(f"Could not parse browser-use JSON output: {output[:500]}")


def load_cookie_file() -> Path:
    raw = os.environ.get("PEERLIST_COOKIES_JSON")
    if not raw:
        raise ValueError("PEERLIST_COOKIES_JSON is required")
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError("PEERLIST_COOKIES_JSON is not valid JSON") from exc
    if not isinstance(parsed, list):
        raise ValueError("PEERLIST_COOKIES_JSON must be a JSON array")
    handle = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False)
    with handle:
        json.dump(parsed, handle)
    return Path(handle.name)


def build_parameters(args: argparse.Namespace) -> dict[str, Any]:
    parameters = automation_default_parameters(PEERLIST_FOLLOW_WORKFLOW)
    parameters.update(
        {
            "type": args.workflow_type,
            "follows_per_day": args.follows_per_day,
            "unfollows_per_day": args.unfollows_per_day,
            "unfollow_after_days": args.unfollow_after_days,
            "do_not_unfollow_peers": args.do_not_unfollow_peers,
        }
    )
    return parameters


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def build_cdp_url(args: argparse.Namespace) -> str:
    if args.cdp_url:
        return args.cdp_url
    if args.browser_use_api_key and args.browser_use_profile_id:
        query = {
            "apiKey": args.browser_use_api_key,
            "profileId": args.browser_use_profile_id,
            "timeout": str(args.browser_use_timeout_minutes),
        }
        if args.browser_use_proxy_country_code:
            query["proxyCountryCode"] = args.browser_use_proxy_country_code
        return "wss://connect.browser-use.com?" + urlencode(query)
    if args.browserbase_api_key:
        return f"wss://connect.browserbase.com?apiKey={args.browserbase_api_key}"
    raise ValueError(
        "BROWSER_USE_CLI_CDP_URL, BROWSER_USE_API_KEY+BROWSER_USE_PROFILE_ID, "
        "or BROWSERBASE_API_KEY is required"
    )


def run_workflow(args: argparse.Namespace) -> dict[str, Any]:
    started_at = datetime.now(UTC).isoformat()
    run_id = f"peerlist-follow-{int(datetime.now(UTC).timestamp())}"
    parameters = build_parameters(args)
    cdp_url = build_cdp_url(args)
    actions: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    blockers: list[dict[str, Any]] = []
    events: list[dict[str, Any]] = []

    cookie_file = load_cookie_file()
    try:
        browser_use(args.session, "close", timeout=30)
    except Exception:
        pass
    browser_use(args.session, "open", "about:blank", cdp_url=cdp_url)
    browser_use(args.session, "cookies", "import", str(cookie_file))
    browser_use(args.session, "open", SEARCH_URL)
    discovery = extract_json(browser_use(args.session, "eval", DISCOVER_JS))

    body_text = discovery.get("body_text") or ""
    actor_verified = (
        "Daniel" in body_text
        and "followers" in body_text
        and "following" in body_text
        and "Log in" not in body_text
        and "Sign in" not in body_text
    )
    if not actor_verified:
        blockers.append(
            {
                "type": "actor_not_verified",
                "reason": "Authenticated Peerlist actor could not be verified",
                "verified": False,
                "target_url": discovery.get("url"),
                "ts": datetime.now(UTC).isoformat(),
            }
        )
    if CHALLENGE_PATTERN.search(body_text):
        blockers.append(
            {
                "type": "challenge_detected",
                "reason": "Challenge or access-denied text detected",
                "verified": False,
                "target_url": discovery.get("url"),
                "ts": datetime.now(UTC).isoformat(),
            }
        )

    candidates = [item for item in discovery.get("candidates", []) if isinstance(item, dict)]
    if not blockers and args.live:
        cap = max(0, min(args.follows_per_day, len(candidates)))
        for candidate in candidates[:cap]:
            target_url = candidate.get("target_url")
            if not target_url:
                skipped.append({**candidate, "reason": "missing_target_url"})
                continue
            browser_use(args.session, "open", str(target_url))
            clicked = extract_json(browser_use(args.session, "eval", CLICK_FOLLOW_JS))
            if not clicked.get("clicked"):
                skipped.append({**candidate, "reason": clicked.get("reason", "follow_click_failed")})
                continue
            try:
                browser_use(args.session, "wait", "text", "Following", "--timeout", "10000")
            except Exception:
                pass
            verified_payload = extract_json(browser_use(args.session, "eval", VERIFY_FOLLOW_JS))
            verified = bool(verified_payload.get("verified"))
            action = {
                **candidate,
                "type": "follow",
                "verified": verified,
                "ts": datetime.now(UTC).isoformat(),
            }
            if verified:
                actions.append(action)
                events.append(
                    {
                        "type": "peerlist_profile_followed",
                        "target_name": action.get("target_name"),
                        "target_url": action.get("target_url"),
                        "target_excerpt": action.get("target_excerpt"),
                        "selector": action.get("selector"),
                        "verified": True,
                        "ts": action["ts"],
                    }
                )
            else:
                skipped.append({**action, "reason": "follow_not_verified"})
    else:
        skipped.extend(
            {**candidate, "reason": "dry_run" if not args.live else "blocked"}
            for candidate in candidates
        )

    finished_at = datetime.now(UTC).isoformat()
    status = "blocked" if blockers else ("ok" if actions else "no_action")
    stop_reason = blockers[0]["reason"] if blockers else None
    return {
        "run_id": run_id,
        "started_at": started_at,
        "finished_at": finished_at,
        "status": status,
        "stop_reason": stop_reason,
        "profile_name": "Daniel" if actor_verified else None,
        "actor_verified": actor_verified,
        "workflow_type": args.workflow_type,
        "workflow_parameters": parameters,
        "peerlist_profile_followers_before": discovery.get("followers"),
        "peerlist_profile_followers_after": discovery.get("followers"),
        "profiles_scanned": len(candidates),
        "profiles_considered": len(candidates),
        "follows_count": len(actions),
        "unfollows_count": 0,
        "peers_preserved_count": 0,
        "actions": actions,
        "skipped": skipped,
        "blockers": blockers,
        "events": events,
        "browser_provider": "browser-use-cli",
        "search_url": SEARCH_URL,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run Peerlist follow workflow through Browser Use CLI")
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--workflow-type", choices=("follow", "unfollow", "rebalance"), default="follow")
    parser.add_argument("--follows-per-day", type=int, default=20)
    parser.add_argument("--unfollows-per-day", type=int, default=10)
    parser.add_argument("--unfollow-after-days", type=int, default=14)
    parser.add_argument("--do-not-unfollow-peers", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--cdp-url", default=os.getenv("BROWSER_USE_CLI_CDP_URL"))
    parser.add_argument("--browser-use-api-key", default=os.getenv("BROWSER_USE_API_KEY"))
    parser.add_argument("--browser-use-profile-id", default=os.getenv("BROWSER_USE_PROFILE_ID"))
    parser.add_argument(
        "--browser-use-proxy-country-code",
        default=os.getenv("BROWSER_USE_PROXY_COUNTRY_CODE", "de"),
    )
    parser.add_argument(
        "--browser-use-timeout-minutes",
        type=int,
        default=int(os.getenv("BROWSER_USE_TIMEOUT_MINUTES", "30")),
    )
    parser.add_argument("--browserbase-api-key", default=os.getenv("BROWSERBASE_API_KEY"))
    parser.add_argument("--session", default=os.getenv("BROWSER_USE_CLI_SESSION", "peerlist-cli-workflow"))
    parser.add_argument("--report-output", type=Path)
    parser.add_argument("--bundle-output", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if (
        not args.cdp_url
        and not (args.browser_use_api_key and args.browser_use_profile_id)
        and not args.browserbase_api_key
    ):
        parser.error(
            "BROWSER_USE_CLI_CDP_URL, BROWSER_USE_API_KEY+BROWSER_USE_PROFILE_ID, "
            "or BROWSERBASE_API_KEY is required"
        )

    report = run_workflow(args)
    bundle = build_run_bundle(
        automation_name=PEERLIST_FOLLOW_WORKFLOW,
        report=report,
        artifact_path=str(args.report_output) if args.report_output else None,
        search_url=SEARCH_URL,
    )
    if args.report_output:
        write_json(args.report_output, report)
    if args.bundle_output:
        write_json(args.bundle_output, bundle)
    if not args.report_output and not args.bundle_output:
        print(json.dumps(bundle, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
