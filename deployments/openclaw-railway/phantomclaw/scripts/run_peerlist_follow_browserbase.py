#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

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


def normalize_cookie(raw: dict[str, Any]) -> dict[str, Any] | None:
    if not raw.get("name") or raw.get("value") is None:
        return None
    cookie = {
        "name": raw["name"],
        "value": raw["value"],
        "domain": raw.get("domain") or "peerlist.io",
        "path": raw.get("path") or "/",
        "secure": bool(raw.get("secure")),
        "httpOnly": bool(raw.get("httpOnly")),
    }
    expires = raw.get("expires")
    if isinstance(expires, (int, float)) and expires > 0:
        cookie["expires"] = int(expires)
    if raw.get("sameSite") in {"Strict", "Lax", "None"}:
        cookie["sameSite"] = raw["sameSite"]
    return cookie


def load_peerlist_cookies() -> list[dict[str, Any]]:
    try:
        raw = json.loads(os.environ.get("PEERLIST_COOKIES_JSON") or "[]")
    except json.JSONDecodeError:
        raw = []
    if not isinstance(raw, list):
        return []
    cookies = [normalize_cookie(cookie) for cookie in raw if isinstance(cookie, dict)]
    return [cookie for cookie in cookies if cookie]


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


async def candidate_from_button(button: Any, index: int) -> dict[str, Any]:
    return await button.evaluate(
        """
        (element, index) => {
          let card = element;
          for (let depth = 0; card && depth < 8; depth += 1) {
            const text = (card.innerText || "").replace(/\\s+/g, " ").trim();
            if (text.length > 45 && /Follow|Following|Peers?/i.test(text)) break;
            card = card.parentElement;
          }
          card = card || element.parentElement || element;
          const text = (card.innerText || "").replace(/\\s+/g, " ").trim();
          const links = Array.from(card.querySelectorAll('a[href^="/"]'));
          const profileLink = links.find((link) => {
            const href = link.getAttribute("href") || "";
            return /^\\/[A-Za-z0-9_.-]+\\/?$/.test(href) && ![
              "/search", "/scroll", "/launchpad", "/articles", "/jobs", "/network"
            ].includes(href.replace(/\\/$/, ""));
          });
          const href = profileLink ? profileLink.href : "";
          const profileText = profileLink
            ? (profileLink.innerText || profileLink.textContent || "").replace(/\\s+/g, " ").trim()
            : "";
          const lines = text.split(/\\s{2,}|\\n/).map((line) => line.trim()).filter(Boolean);
          const targetName = profileText || lines.find((line) =>
            line && !/^(Follow|Following|Peer|Peers|People|Visit)$/i.test(line)
          ) || `Peerlist profile ${index}`;
          return {
            type: "follow",
            target_name: targetName.slice(0, 160),
            target_url: href || null,
            target_excerpt: text.slice(0, 500),
            selector: `button:has-text("Follow") >> nth=${index}`,
            verified: false,
          };
        }
        """,
        index,
    )


async def run_workflow(args: argparse.Namespace) -> dict[str, Any]:
    from playwright.async_api import async_playwright

    started_at = datetime.now(UTC).isoformat()
    parameters = build_parameters(args)
    run_id = f"peerlist-follow-{int(datetime.now(UTC).timestamp())}"
    actions: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    blockers: list[dict[str, Any]] = []
    events: list[dict[str, Any]] = []

    cookies = load_peerlist_cookies()
    if not cookies:
        blockers.append(
            {
                "type": "auth_missing",
                "reason": "PEERLIST_COOKIES_JSON is empty or invalid",
                "verified": False,
                "ts": started_at,
            }
        )

    async with async_playwright() as playwright:
        browser = await playwright.chromium.connect_over_cdp(
            f"wss://connect.browserbase.com?apiKey={args.browserbase_api_key}",
            timeout=60_000,
        )
        try:
            context = browser.contexts[0] if browser.contexts else await browser.new_context()
            if cookies:
                await context.add_cookies(cookies)
            page = context.pages[0] if context.pages else await context.new_page()
            page.set_default_timeout(15_000)
            await page.goto(SEARCH_URL, wait_until="domcontentloaded", timeout=90_000)
            await page.wait_for_timeout(6_000)
            body_text = await page.locator("body").inner_text()
            actor_verified = (
                "Daniel" in body_text
                and "followers" in body_text
                and "following" in body_text
                and "Log in" not in body_text
                and "Sign in" not in body_text
            )
            has_challenge = bool(CHALLENGE_PATTERN.search(body_text))
            if not actor_verified:
                blockers.append(
                    {
                        "type": "actor_not_verified",
                        "reason": "Authenticated Peerlist actor could not be verified",
                        "verified": False,
                        "target_url": page.url,
                        "ts": datetime.now(UTC).isoformat(),
                    }
                )
            if has_challenge:
                blockers.append(
                    {
                        "type": "challenge_detected",
                        "reason": "Challenge or access-denied text detected",
                        "verified": False,
                        "target_url": page.url,
                        "ts": datetime.now(UTC).isoformat(),
                    }
                )

            follower_match = re.search(r"([0-9][0-9,.\u00a0 ]*)\s*followers", body_text, re.I)
            followers_before = None
            if follower_match:
                raw_count = re.sub(r"[^0-9]", "", follower_match.group(1))
                followers_before = int(raw_count) if raw_count else None

            follow_buttons = page.get_by_role("button", name=re.compile(r"^Follow$", re.I))
            button_count = await follow_buttons.count()
            candidates: list[dict[str, Any]] = []
            for index in range(button_count):
                button = follow_buttons.nth(index)
                if await button.is_visible():
                    candidates.append(await candidate_from_button(button, index))

            if not blockers and args.live:
                cap = max(0, min(args.follows_per_day, len(candidates)))
                for candidate in candidates[:cap]:
                    if not candidate.get("target_url"):
                        skipped.append({**candidate, "reason": "missing_target_url"})
                        continue
                    await page.goto(candidate["target_url"], wait_until="domcontentloaded", timeout=90_000)
                    await page.wait_for_timeout(3_000)
                    profile_button = page.get_by_role("button", name=re.compile(r"^Follow$", re.I)).first
                    if await profile_button.count() == 0:
                        skipped.append({**candidate, "reason": "profile_follow_button_missing"})
                        continue
                    await profile_button.scroll_into_view_if_needed()
                    await page.wait_for_timeout(800)
                    await profile_button.click()
                    await page.wait_for_timeout(2_500)
                    profile_buttons = await page.get_by_role(
                        "button",
                        name=re.compile(r"^(Following|Peer|Peers)$", re.I),
                    ).count()
                    label = ""
                    if profile_buttons:
                        label = "Following"
                    else:
                        label = (await profile_button.inner_text()).strip()
                    verified = label.lower() in {"following", "peer", "peers"}
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
                        skipped.append({**action, "reason": f"follow_not_verified_label_{label}"})
            else:
                skipped.extend({**candidate, "reason": "dry_run" if not args.live else "blocked"} for candidate in candidates)

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
                "peerlist_profile_followers_before": followers_before,
                "peerlist_profile_followers_after": followers_before,
                "profiles_scanned": len(candidates),
                "profiles_considered": len(candidates),
                "follows_count": len(actions),
                "unfollows_count": 0,
                "peers_preserved_count": 0,
                "actions": actions,
                "skipped": skipped,
                "blockers": blockers,
                "events": events,
                "browser_provider": "browserbase",
                "search_url": SEARCH_URL,
            }
        finally:
            await browser.close()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run Peerlist follow workflow through Browserbase CDP")
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--workflow-type", choices=("follow", "unfollow", "rebalance"), default="follow")
    parser.add_argument("--follows-per-day", type=int, default=20)
    parser.add_argument("--unfollows-per-day", type=int, default=10)
    parser.add_argument("--unfollow-after-days", type=int, default=14)
    parser.add_argument("--do-not-unfollow-peers", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--browserbase-api-key", default=os.getenv("BROWSERBASE_API_KEY"))
    parser.add_argument("--report-output", type=Path)
    parser.add_argument("--bundle-output", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.browserbase_api_key:
        parser.error("BROWSERBASE_API_KEY or --browserbase-api-key is required")

    report = asyncio.run(run_workflow(args))
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
