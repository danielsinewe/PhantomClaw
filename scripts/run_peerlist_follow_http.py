#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import random
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

PACKAGE_ROOT = Path(__file__).resolve().parent.parent
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

from automation_catalog import PEERLIST_FOLLOW_WORKFLOW, automation_default_parameters
from phantomclaw_bundle import build_run_bundle


BASE_URL = "https://peerlist.io"
SCROLL_FEED_URL = "/api/v2/scroll/feed?numUpvoteProfiles=3&numComments=2&newest=true"
NETWORK_COUNT_URL = "/api/v1/follows/count?includePeer=true"
FOLLOWING_URL = "/api/v1/users/following"
FOLLOW_URL = "/api/v1/users/follow"
UNFOLLOW_URL = "/api/v1/users/unfollow"
DEFAULT_TIMEZONE = "Europe/Berlin"

CHALLENGE_PATTERN = re.compile(
    r"Cloudflare|captcha|verify you are human|checking your browser|access denied|Just a moment",
    re.I,
)


class PeerlistHTTPError(RuntimeError):
    def __init__(self, message: str, *, status: int | None = None, body: str = "") -> None:
        super().__init__(message)
        self.status = status
        self.body = body


def _cookie_lookup(cookies: list[dict[str, Any]]) -> dict[str, str]:
    lookup: dict[str, str] = {}
    for cookie in cookies:
        name = cookie.get("name")
        value = cookie.get("value")
        if isinstance(name, str) and value is not None:
            lookup[name] = str(value)
    return lookup


class PeerlistClient:
    def __init__(self, cookies: list[dict[str, Any]]) -> None:
        self.cookies = cookies
        self.cookie_lookup = _cookie_lookup(cookies)
        self.cookie_header = "; ".join(
            f"{cookie.get('name')}={cookie.get('value')}"
            for cookie in cookies
            if cookie.get("name") and cookie.get("value") is not None
        )

    @classmethod
    def from_env(cls) -> "PeerlistClient":
        raw = os.environ.get("PEERLIST_COOKIES_JSON")
        if not raw:
            raise ValueError("PEERLIST_COOKIES_JSON is required")
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError("PEERLIST_COOKIES_JSON is not valid JSON") from exc
        if not isinstance(parsed, list):
            raise ValueError("PEERLIST_COOKIES_JSON must be a JSON array")
        cookies = [cookie for cookie in parsed if isinstance(cookie, dict)]
        if not cookies:
            raise ValueError("PEERLIST_COOKIES_JSON is empty")
        return cls(cookies)

    def headers(self, *, accept: str = "application/json, text/plain, */*", json_body: bool = False) -> dict[str, str]:
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept": accept,
            "Accept-Language": "en-US,en;q=0.9",
            "Origin": BASE_URL,
            "Referer": f"{BASE_URL}/scroll",
            "Cookie": self.cookie_header,
        }
        if self.cookie_lookup.get("MY_IP"):
            headers["x-real-ip"] = self.cookie_lookup["MY_IP"]
        if self.cookie_lookup.get("ipv4"):
            headers["x-pl-ip"] = self.cookie_lookup["ipv4"]
        if self.cookie_lookup.get("id"):
            headers["x-peerlist-id"] = self.cookie_lookup["id"]
        if json_body:
            headers["Content-Type"] = "application/json"
        return headers

    def request_json(self, method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        url = path if path.startswith("http") else f"{BASE_URL}{path}"
        body = None
        if payload is not None:
            body = json.dumps(payload, separators=(",", ":")).encode()
        request = urllib.request.Request(
            url,
            data=body,
            headers=self.headers(json_body=payload is not None),
            method=method,
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                text = response.read().decode("utf-8", "ignore")
        except urllib.error.HTTPError as exc:
            text = exc.read().decode("utf-8", "ignore")
            raise PeerlistHTTPError(
                f"Peerlist HTTP {exc.code} for {method} {path}",
                status=exc.code,
                body=text,
            ) from exc
        except urllib.error.URLError as exc:
            raise PeerlistHTTPError(f"Peerlist request failed for {method} {path}: {exc}") from exc
        if CHALLENGE_PATTERN.search(text):
            raise PeerlistHTTPError(f"Peerlist challenge detected for {method} {path}", body=text)
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as exc:
            raise PeerlistHTTPError(f"Peerlist returned non-JSON for {method} {path}", body=text[:1000]) from exc
        if not isinstance(parsed, dict):
            raise PeerlistHTTPError(f"Peerlist returned non-object JSON for {method} {path}", body=text[:1000])
        return parsed


def build_parameters(args: argparse.Namespace) -> dict[str, Any]:
    parameters = automation_default_parameters(PEERLIST_FOLLOW_WORKFLOW)
    parameters.update(
        {
            "type": args.workflow_type,
            "follows_per_day": args.follows_per_day,
            "max_follows_per_run": args.max_follows_per_run,
            "unfollows_per_day": args.unfollows_per_day,
            "max_unfollows_per_run": args.max_unfollows_per_run,
            "unfollow_source": args.unfollow_source,
            "unfollow_after_days": args.unfollow_after_days,
            "do_not_unfollow_peers": args.do_not_unfollow_peers,
            "do_not_unfollow_followers": args.do_not_unfollow_followers,
            "active_window_start": args.active_window_start,
            "active_window_end": args.active_window_end,
            "min_delay_seconds": args.min_delay_seconds,
            "max_delay_seconds": args.max_delay_seconds,
            "error_backoff_seconds": args.error_backoff_seconds,
            "candidate_pool_limit": args.candidate_pool_limit,
            "require_verified_profile": args.require_verified_profile,
            "skip_existing_following": args.skip_existing_following,
            "skip_existing_followers": args.skip_existing_followers,
            "skip_peers": args.skip_peers,
            "profile_blacklist": args.profile_blacklist,
            "profile_whitelist": args.profile_whitelist,
            "following_page_start": args.following_page_start,
            "following_page_limit": args.following_page_limit,
        }
    )
    return parameters


def _as_user(raw: Any) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    handle = raw.get("profileHandle")
    user_id = raw.get("id")
    if not isinstance(handle, str) or not handle:
        return None
    return {
        "id": user_id,
        "profileHandle": handle,
        "displayName": raw.get("displayName") or " ".join(
            item for item in (str(raw.get("firstName") or ""), str(raw.get("lastName") or "")) if item
        ).strip(),
        "headline": raw.get("headline"),
        "verified": bool(raw.get("verified")),
        "following": bool(raw.get("following") or raw.get("isFollowing")),
        "follower": bool(raw.get("follower") or raw.get("isFollower")),
        "peer": bool(raw.get("peer") or raw.get("isPeers")),
    }


def discover_candidates(feed_payload: dict[str, Any]) -> list[dict[str, Any]]:
    data = feed_payload.get("data")
    posts = data.get("scroll") if isinstance(data, dict) else None
    if not isinstance(posts, list):
        return []
    candidates: list[dict[str, Any]] = []
    seen: set[str] = set()
    for post in posts:
        if not isinstance(post, dict):
            continue
        users = [
            _as_user(post.get("postedBy")),
            _as_user((post.get("metaData") or {}).get("createdBy") if isinstance(post.get("metaData"), dict) else None),
            _as_user((post.get("metaData") or {}).get("originalPoster") if isinstance(post.get("metaData"), dict) else None),
        ]
        for user in users:
            if not user:
                continue
            handle = user["profileHandle"]
            if handle in seen:
                continue
            seen.add(handle)
            candidates.append(
                {
                    "type": "follow",
                    "target_name": user.get("displayName") or handle,
                    "target_handle": handle,
                    "target_url": f"{BASE_URL}/{handle}",
                    "target_excerpt": str(user.get("headline") or "")[:500],
                    "target_id": user.get("id"),
                    "selector": f"peerlist-api:user:{handle}",
                    "verified_profile": bool(user.get("verified")),
                    "relationship": {
                        "following": bool(user.get("following")),
                        "follower": bool(user.get("follower")),
                        "peer": bool(user.get("peer")),
                    },
                    "verified": False,
                }
            )
    return candidates


def normalize_relationship(relation: dict[str, Any]) -> dict[str, bool]:
    return {
        "following": bool(relation.get("following") or relation.get("isFollowing")),
        "follower": bool(relation.get("follower") or relation.get("isFollower")),
        "peer": bool(relation.get("peer") or relation.get("isPeers")),
    }


def refresh_candidate_relationships(client: PeerlistClient, candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    refreshed: list[dict[str, Any]] = []
    for candidate in candidates:
        handle = str(candidate.get("target_handle") or "")
        target_id = candidate.get("target_id")
        if not handle:
            refreshed.append(candidate)
            continue
        try:
            relation = relationship_for(client, handle, target_id=target_id if isinstance(target_id, str) else None)
        except Exception as exc:
            refreshed.append({**candidate, "relationship_refresh_error": str(exc)[:500]})
            continue
        if relation:
            refreshed.append(
                {
                    **candidate,
                    "relationship": normalize_relationship(relation),
                    "relationship_detail": relation,
                }
            )
        else:
            refreshed.append(candidate)
    return refreshed


def filter_candidates(
    candidates: list[dict[str, Any]],
    *,
    args: argparse.Namespace,
    self_handle: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    accepted: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    blacklist = {item.lower() for item in args.profile_blacklist}
    whitelist = {item.lower() for item in args.profile_whitelist}
    for candidate in candidates:
        handle = str(candidate.get("target_handle") or "")
        relationship = candidate.get("relationship") if isinstance(candidate.get("relationship"), dict) else {}
        lower = handle.lower()
        if lower == self_handle.lower():
            skipped.append({**candidate, "reason": "self_profile"})
        elif whitelist and lower not in whitelist:
            skipped.append({**candidate, "reason": "not_in_profile_whitelist"})
        elif lower in blacklist:
            skipped.append({**candidate, "reason": "profile_blacklisted"})
        elif args.require_verified_profile and not candidate.get("verified_profile"):
            skipped.append({**candidate, "reason": "unverified_profile"})
        elif args.skip_peers and relationship.get("peer"):
            skipped.append({**candidate, "reason": "is_peer"})
        elif args.skip_existing_following and relation_me_follows_target(relationship):
            skipped.append({**candidate, "reason": "already_following"})
        elif args.skip_existing_followers and relation_target_follows_me(relationship):
            skipped.append({**candidate, "reason": "already_follower"})
        else:
            accepted.append(candidate)
    return accepted, skipped


def relationship_for(client: PeerlistClient, handle: str, *, target_id: str | None = None) -> dict[str, Any]:
    if target_id:
        path = f"/api/v1/users/peers?id={urllib.parse.quote(target_id)}"
    else:
        path = f"/api/v1/users/peers?username={urllib.parse.quote(handle)}"
    payload = client.request_json("GET", path)
    data = payload.get("data") if isinstance(payload, dict) else None
    return data if isinstance(data, dict) else {}


def relation_me_follows_target(relation: dict[str, Any]) -> bool:
    # Peerlist's follow-list detail names are from the viewed user's perspective:
    # `follower` means the actor follows the target, while `following` means the
    # target follows the actor.
    return bool(relation.get("follower") or relation.get("isFollower") or relation.get("peer") or relation.get("isPeers"))


def relation_target_follows_me(relation: dict[str, Any]) -> bool:
    return bool(relation.get("following") or relation.get("isFollowing") or relation.get("peer") or relation.get("isPeers"))


def relation_verified_as_followed(relation: dict[str, Any]) -> bool:
    return relation_me_follows_target(relation)


def relation_verified_as_unfollowed(relation: dict[str, Any]) -> bool:
    return not relation_me_follows_target(relation)


def day_window_utc(timezone_name: str) -> tuple[datetime, datetime]:
    timezone = ZoneInfo(timezone_name)
    start_local = datetime.now(timezone).replace(hour=0, minute=0, second=0, microsecond=0)
    end_local = start_local + timedelta(days=1)
    return start_local.astimezone(UTC), end_local.astimezone(UTC)


def verified_actions_today(*, profile_name: str, action_type: str, timezone_name: str = DEFAULT_TIMEZONE) -> int:
    database_url = os.environ.get("AUTOMATION_ANALYTICS_DATABASE_URL") or os.environ.get("DATABASE_URL")
    if not database_url:
        raise RuntimeError("AUTOMATION_ANALYTICS_DATABASE_URL or DATABASE_URL is required for live daily cap checks")
    try:
        import psycopg
    except ImportError as exc:
        raise RuntimeError("psycopg is required for live daily cap checks") from exc
    start_utc, end_utc = day_window_utc(timezone_name)
    with psycopg.connect(database_url) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                select count(*)
                from automation_action_events_v1
                where automation_name = %s
                  and platform = %s
                  and profile_name = %s
                  and action_type = %s
                  and verified is true
                  and action_ts::timestamptz >= %s
                  and action_ts::timestamptz < %s
                """,
                (
                    PEERLIST_FOLLOW_WORKFLOW,
                    "peerlist",
                    profile_name,
                    action_type,
                    start_utc,
                    end_utc,
                ),
            )
            value = cur.fetchone()[0]
    return int(value or 0)


def verified_follows_today(*, profile_name: str, timezone_name: str = DEFAULT_TIMEZONE) -> int:
    return verified_actions_today(
        profile_name=profile_name,
        action_type="peerlist_profile_followed",
        timezone_name=timezone_name,
    )


def verified_unfollows_today(*, profile_name: str, timezone_name: str = DEFAULT_TIMEZONE) -> int:
    return verified_actions_today(
        profile_name=profile_name,
        action_type="peerlist_profile_unfollowed",
        timezone_name=timezone_name,
    )


def discover_unfollow_candidates(
    *,
    profile_name: str,
    unfollow_after_days: int,
    limit: int,
) -> list[dict[str, Any]]:
    database_url = os.environ.get("AUTOMATION_ANALYTICS_DATABASE_URL") or os.environ.get("DATABASE_URL")
    if not database_url:
        raise RuntimeError("AUTOMATION_ANALYTICS_DATABASE_URL or DATABASE_URL is required to find unfollow candidates")
    try:
        import psycopg
        from psycopg.rows import dict_row
    except ImportError as exc:
        raise RuntimeError("psycopg is required to find unfollow candidates") from exc

    cutoff = datetime.now(UTC) - timedelta(days=max(1, unfollow_after_days))
    with psycopg.connect(database_url, row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                WITH followed AS (
                  SELECT
                    target_name,
                    action_event_json->>'target_handle' AS target_handle,
                    target_url,
                    target_excerpt,
                    action_event_json->>'target_id' AS target_id,
                    min(action_ts::timestamptz) AS first_followed_at
                  FROM automation_action_events_v1
                  WHERE automation_name = %s
                    AND platform = %s
                    AND profile_name = %s
                    AND action_type = %s
                    AND verified IS TRUE
                    AND action_ts::timestamptz <= %s
                  GROUP BY target_name, target_handle, target_url, target_excerpt, target_id
                ),
                unfollowed AS (
                  SELECT DISTINCT COALESCE(action_event_json->>'target_id', action_event_json->>'target_handle', target_url) AS target_key
                  FROM automation_action_events_v1
                  WHERE automation_name = %s
                    AND platform = %s
                    AND profile_name = %s
                    AND action_type = %s
                    AND verified IS TRUE
                )
                SELECT followed.*
                FROM followed
                LEFT JOIN unfollowed
                  ON unfollowed.target_key = COALESCE(followed.target_id, followed.target_handle, followed.target_url)
                WHERE unfollowed.target_key IS NULL
                  AND COALESCE(followed.target_id, '') <> ''
                  AND COALESCE(followed.target_handle, '') <> ''
                ORDER BY followed.first_followed_at ASC
                LIMIT %s
                """,
                (
                    PEERLIST_FOLLOW_WORKFLOW,
                    "peerlist",
                    profile_name,
                    "peerlist_profile_followed",
                    cutoff,
                    PEERLIST_FOLLOW_WORKFLOW,
                    "peerlist",
                    profile_name,
                    "peerlist_profile_unfollowed",
                    max(0, limit),
                ),
            )
            rows = cur.fetchall()

    candidates: list[dict[str, Any]] = []
    for row in rows:
        handle = str(row.get("target_handle") or "")
        candidates.append(
            {
                "type": "unfollow",
                "target_name": row.get("target_name") or handle,
                "target_handle": handle,
                "target_url": row.get("target_url") or f"{BASE_URL}/{handle}",
                "target_excerpt": row.get("target_excerpt"),
                "target_id": row.get("target_id"),
                "first_followed_at": row.get("first_followed_at").isoformat()
                if hasattr(row.get("first_followed_at"), "isoformat")
                else row.get("first_followed_at"),
                "selector": f"peerlist-api:user:{handle}",
                "verified": False,
            }
        )
    return candidates


def discover_current_following_candidates(
    client: PeerlistClient,
    *,
    args: argparse.Namespace,
    limit: int,
) -> tuple[list[dict[str, Any]], int]:
    candidates: list[dict[str, Any]] = []
    seen: set[str] = set()
    scanned = 0
    page_start = max(1, args.following_page_start)
    page_limit = max(1, args.following_page_limit)
    for page in range(page_start, page_start + page_limit):
        payload = client.request_json("GET", f"{FOLLOWING_URL}?page={page}")
        data = payload.get("data") if isinstance(payload, dict) else None
        rows = data.get("following") if isinstance(data, dict) else None
        if not isinstance(rows, list) or not rows:
            break
        scanned += len(rows)
        for raw in rows:
            user = _as_user(raw)
            if not user:
                continue
            handle = str(user["profileHandle"])
            if handle in seen:
                continue
            seen.add(handle)
            relationship = {
                "follower": bool(user.get("follower")),
                "following": bool(user.get("following")),
                "peer": bool(user.get("peer")),
                "isPeers": bool(user.get("peer")),
            }
            candidates.append(
                {
                    "type": "unfollow",
                    "target_name": user.get("displayName") or handle,
                    "target_handle": handle,
                    "target_url": f"{BASE_URL}/{handle}",
                    "target_excerpt": str(user.get("headline") or "")[:500],
                    "target_id": user.get("id"),
                    "selector": f"peerlist-api:following:{handle}",
                    "verified_profile": bool(user.get("verified")),
                    "relationship": relationship,
                    "relationship_detail": raw,
                    "source": "current_following",
                    "source_page": page,
                    "verified": False,
                }
            )
            if len(candidates) >= limit:
                return candidates, scanned
    return candidates, scanned


def peers_preserved_reason(candidate: dict[str, Any], *, args: argparse.Namespace) -> dict[str, Any] | None:
    relationship = candidate.get("relationship") if isinstance(candidate.get("relationship"), dict) else {}
    if args.do_not_unfollow_peers and relationship.get("peer"):
        return {**candidate, "reason": "peer_preserved"}
    if args.do_not_unfollow_followers and relation_target_follows_me(relationship):
        return {**candidate, "reason": "follower_preserved"}
    return None


def run_workflow(args: argparse.Namespace) -> dict[str, Any]:
    started_at = datetime.now(UTC).isoformat()
    run_id = f"peerlist-follow-{int(datetime.now(UTC).timestamp())}"
    parameters = build_parameters(args)
    actions: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    blockers: list[dict[str, Any]] = []
    events: list[dict[str, Any]] = []
    followers_before = None
    followers_after = None
    following_before = None
    following_after = None
    candidates: list[dict[str, Any]] = []
    raw_unfollow_candidates_scanned = 0
    daily_follows_before = 0
    daily_unfollows_before = 0
    daily_follows_remaining = args.follows_per_day
    daily_unfollows_remaining = args.unfollows_per_day

    try:
        client = PeerlistClient.from_env()
        count_payload = client.request_json("GET", NETWORK_COUNT_URL)
        count_data = count_payload.get("data") if isinstance(count_payload, dict) else None
        if isinstance(count_data, dict):
            followers_before = count_data.get("followers")
            followers_after = followers_before
            following_before = count_data.get("following")
            following_after = following_before
        actor_verified = isinstance(followers_before, int) and int(followers_before) >= 0

        if not actor_verified:
            blockers.append(
                {
                    "type": "actor_not_verified",
                    "reason": "Peerlist network count did not verify authenticated actor",
                    "verified": False,
                    "ts": datetime.now(UTC).isoformat(),
                }
            )

        if args.live:
            try:
                daily_follows_before = verified_follows_today(
                    profile_name=args.profile_name,
                    timezone_name=os.environ.get("PHANTOMCLAW_TIMEZONE", DEFAULT_TIMEZONE),
                )
                daily_unfollows_before = verified_unfollows_today(
                    profile_name=args.profile_name,
                    timezone_name=os.environ.get("PHANTOMCLAW_TIMEZONE", DEFAULT_TIMEZONE),
                )
                daily_follows_remaining = max(0, args.follows_per_day - daily_follows_before)
                daily_unfollows_remaining = max(0, args.unfollows_per_day - daily_unfollows_before)
            except Exception as exc:
                blockers.append(
                    {
                        "type": "daily_cap_check_failed",
                        "reason": str(exc)[:500],
                        "verified": False,
                        "ts": datetime.now(UTC).isoformat(),
                    }
                )
            if daily_follows_remaining <= 0:
                skipped.append(
                    {
                        "type": "daily_follow_cap_reached",
                        "reason": f"Daily follow cap reached: {daily_follows_before}/{args.follows_per_day}",
                        "verified": True,
                        "ts": datetime.now(UTC).isoformat(),
                    }
                )
            if daily_unfollows_remaining <= 0:
                skipped.append(
                    {
                        "type": "daily_unfollow_cap_reached",
                        "reason": f"Daily unfollow cap reached: {daily_unfollows_before}/{args.unfollows_per_day}",
                        "verified": True,
                        "ts": datetime.now(UTC).isoformat(),
                    }
                )

        if args.workflow_type in {"follow", "rebalance"}:
            feed_payload = client.request_json("GET", SCROLL_FEED_URL)
            raw_candidates = discover_candidates(feed_payload)[: max(0, args.candidate_pool_limit)]
            raw_candidates = refresh_candidate_relationships(client, raw_candidates)
            follow_candidates, filter_skips = filter_candidates(raw_candidates, args=args, self_handle=args.profile_handle)
            candidates.extend(follow_candidates)
            skipped.extend(filter_skips)

        unfollow_candidates: list[dict[str, Any]] = []
        if args.workflow_type in {"unfollow", "rebalance"}:
            try:
                if args.unfollow_source == "current_following":
                    raw_unfollow_candidates, raw_unfollow_candidates_scanned = discover_current_following_candidates(
                        client,
                        args=args,
                        limit=args.candidate_pool_limit,
                    )
                else:
                    raw_unfollow_candidates = discover_unfollow_candidates(
                        profile_name=args.profile_name,
                        unfollow_after_days=args.unfollow_after_days,
                        limit=args.candidate_pool_limit,
                    )
                    raw_unfollow_candidates_scanned = len(raw_unfollow_candidates)
                raw_unfollow_candidates = refresh_candidate_relationships(client, raw_unfollow_candidates)
                for candidate in raw_unfollow_candidates:
                    preserved = peers_preserved_reason(candidate, args=args)
                    if preserved:
                        skipped.append(preserved)
                    elif not relation_me_follows_target(candidate.get("relationship") if isinstance(candidate.get("relationship"), dict) else {}):
                        skipped.append({**candidate, "reason": "already_unfollowed"})
                    else:
                        unfollow_candidates.append(candidate)
                candidates.extend(unfollow_candidates)
            except Exception as exc:
                blockers.append(
                    {
                        "type": "unfollow_candidate_lookup_failed",
                        "reason": str(exc)[:500],
                        "verified": False,
                        "ts": datetime.now(UTC).isoformat(),
                    }
                )

        if not blockers and args.live:
            follow_cap = max(
                0,
                min(
                    daily_follows_remaining,
                    args.max_follows_per_run,
                    len([candidate for candidate in candidates if candidate.get("type") == "follow"]),
                ),
            )
            for index, candidate in enumerate([candidate for candidate in candidates if candidate.get("type") == "follow"][:follow_cap]):
                handle = str(candidate.get("target_handle") or "")
                if not handle:
                    skipped.append({**candidate, "reason": "missing_target_handle"})
                    continue
                if index > 0 and args.max_delay_seconds > 0:
                    delay = random.randint(args.min_delay_seconds, args.max_delay_seconds)
                    time.sleep(delay)
                try:
                    response = client.request_json("POST", FOLLOW_URL, {"followerUsername": [handle]})
                    target_id = candidate.get("target_id")
                    relation = relationship_for(client, handle, target_id=target_id if isinstance(target_id, str) else None)
                    verified = relation_verified_as_followed(relation)
                except Exception as exc:
                    skipped.append({**candidate, "reason": "follow_request_failed", "message": str(exc)[:500]})
                    continue
                action = {
                    **candidate,
                    "type": "follow",
                    "verified": verified,
                    "api_success": bool(response.get("success")),
                    "relationship_after": relation,
                    "ts": datetime.now(UTC).isoformat(),
                }
                if verified:
                    actions.append(action)
                    events.append(
                        {
                            "type": "peerlist_profile_followed",
                            "target_name": action.get("target_name"),
                            "target_handle": action.get("target_handle"),
                            "target_id": action.get("target_id"),
                            "target_url": action.get("target_url"),
                            "target_excerpt": action.get("target_excerpt"),
                            "selector": action.get("selector"),
                            "verified": True,
                            "ts": action["ts"],
                        }
                    )
                else:
                    skipped.append({**action, "reason": "follow_not_verified"})

            unfollow_cap = max(
                0,
                min(
                    daily_unfollows_remaining,
                    args.max_unfollows_per_run,
                    len([candidate for candidate in candidates if candidate.get("type") == "unfollow"]),
                ),
            )
            for index, candidate in enumerate([candidate for candidate in candidates if candidate.get("type") == "unfollow"][:unfollow_cap]):
                handle = str(candidate.get("target_handle") or "")
                target_id = candidate.get("target_id")
                if not handle or not isinstance(target_id, str) or not target_id:
                    skipped.append({**candidate, "reason": "missing_unfollow_target_identity"})
                    continue
                if index > 0 and args.max_delay_seconds > 0:
                    delay = random.randint(args.min_delay_seconds, args.max_delay_seconds)
                    time.sleep(delay)
                try:
                    before_relation = relationship_for(client, handle, target_id=target_id)
                    if args.do_not_unfollow_peers and normalize_relationship(before_relation).get("peer"):
                        skipped.append({**candidate, "reason": "peer_preserved", "relationship_before": before_relation})
                        continue
                    response = client.request_json("POST", UNFOLLOW_URL, {"followerUsername": handle})
                    relation = relationship_for(client, handle, target_id=target_id)
                    verified = relation_verified_as_unfollowed(relation)
                except Exception as exc:
                    skipped.append({**candidate, "reason": "unfollow_request_failed", "message": str(exc)[:500]})
                    continue
                action = {
                    **candidate,
                    "type": "unfollow",
                    "verified": verified,
                    "api_success": bool(response.get("success")),
                    "relationship_after": relation,
                    "ts": datetime.now(UTC).isoformat(),
                }
                if verified:
                    actions.append(action)
                    events.append(
                        {
                            "type": "peerlist_profile_unfollowed",
                            "target_name": action.get("target_name"),
                            "target_handle": action.get("target_handle"),
                            "target_id": action.get("target_id"),
                            "target_url": action.get("target_url"),
                            "target_excerpt": action.get("target_excerpt"),
                            "selector": action.get("selector"),
                            "verified": True,
                            "ts": action["ts"],
                        }
                    )
                else:
                    skipped.append({**action, "reason": "unfollow_not_verified"})
            if actions:
                after_payload = client.request_json("GET", NETWORK_COUNT_URL)
                after_data = after_payload.get("data") if isinstance(after_payload, dict) else None
                if isinstance(after_data, dict):
                    followers_after = after_data.get("followers")
                    following_after = after_data.get("following")
        else:
            skipped.extend(
                {**candidate, "reason": "dry_run" if not args.live else "blocked"}
                for candidate in candidates
            )
    except Exception as exc:
        actor_verified = False
        blockers.append(
            {
                "type": "peerlist_http_error",
                "reason": str(exc)[:500],
                "verified": False,
                "ts": datetime.now(UTC).isoformat(),
            }
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
        "profile_name": args.profile_name if actor_verified else None,
        "actor_verified": actor_verified,
        "workflow_type": args.workflow_type,
        "workflow_parameters": parameters,
        "peerlist_profile_followers_before": followers_before,
        "peerlist_profile_followers_after": followers_after,
        "peerlist_profile_following_before": following_before,
        "peerlist_profile_following_after": following_after,
        "profiles_scanned": max(len(candidates), raw_unfollow_candidates_scanned),
        "profiles_considered": len(candidates),
        "follows_count": sum(1 for action in actions if action.get("type") == "follow"),
        "unfollows_count": sum(1 for action in actions if action.get("type") == "unfollow"),
        "peers_preserved_count": sum(1 for item in skipped if item.get("reason") in {"is_peer", "peer_preserved"}),
        "followers_preserved_count": sum(1 for item in skipped if item.get("reason") == "follower_preserved"),
        "daily_follows_before": daily_follows_before,
        "daily_unfollows_before": daily_unfollows_before,
        "daily_follows_remaining": daily_follows_remaining,
        "daily_unfollows_remaining": daily_unfollows_remaining,
        "actions": actions,
        "skipped": skipped,
        "blockers": blockers,
        "events": events,
        "browser_provider": "peerlist-http",
        "search_url": f"{BASE_URL}{SCROLL_FEED_URL}",
    }


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def csv_arg(value: str | None) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run Peerlist follow workflow through authenticated Peerlist HTTP APIs")
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--workflow-type", choices=("follow", "unfollow", "rebalance"), default="follow")
    parser.add_argument("--follows-per-day", type=int, default=20)
    parser.add_argument("--max-follows-per-run", type=int, default=int(os.getenv("PEERLIST_MAX_FOLLOWS_PER_RUN", "1")))
    parser.add_argument("--unfollows-per-day", type=int, default=10)
    parser.add_argument("--max-unfollows-per-run", type=int, default=int(os.getenv("PEERLIST_MAX_UNFOLLOWS_PER_RUN", "1")))
    parser.add_argument(
        "--unfollow-source",
        choices=("workflow_history", "current_following"),
        default=os.getenv("PEERLIST_UNFOLLOW_SOURCE", "workflow_history"),
    )
    parser.add_argument("--unfollow-after-days", type=int, default=14)
    parser.add_argument("--do-not-unfollow-peers", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--do-not-unfollow-followers", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--active-window-start", default=os.getenv("PEERLIST_ACTIVE_WINDOW_START", "09:00"))
    parser.add_argument("--active-window-end", default=os.getenv("PEERLIST_ACTIVE_WINDOW_END", "18:00"))
    parser.add_argument("--min-delay-seconds", type=int, default=int(os.getenv("PEERLIST_MIN_DELAY_SECONDS", "90")))
    parser.add_argument("--max-delay-seconds", type=int, default=int(os.getenv("PEERLIST_MAX_DELAY_SECONDS", "240")))
    parser.add_argument("--error-backoff-seconds", type=int, default=int(os.getenv("PEERLIST_ERROR_BACKOFF_SECONDS", "900")))
    parser.add_argument("--candidate-pool-limit", type=int, default=int(os.getenv("PEERLIST_CANDIDATE_POOL_LIMIT", "50")))
    parser.add_argument("--require-verified-profile", action=argparse.BooleanOptionalAction, default=os.getenv("PEERLIST_REQUIRE_VERIFIED_PROFILE", "0") == "1")
    parser.add_argument("--skip-existing-following", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--skip-existing-followers", action=argparse.BooleanOptionalAction, default=False)
    parser.add_argument("--skip-peers", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--profile-blacklist", type=csv_arg, default=csv_arg(os.getenv("PEERLIST_PROFILE_BLACKLIST")))
    parser.add_argument("--profile-whitelist", type=csv_arg, default=csv_arg(os.getenv("PEERLIST_PROFILE_WHITELIST")))
    parser.add_argument("--following-page-start", type=int, default=int(os.getenv("PEERLIST_FOLLOWING_PAGE_START", "1")))
    parser.add_argument("--following-page-limit", type=int, default=int(os.getenv("PEERLIST_FOLLOWING_PAGE_LIMIT", "30")))
    parser.add_argument("--profile-name", default=os.getenv("PEERLIST_PROFILE_NAME", "Daniel"))
    parser.add_argument("--profile-handle", default=os.getenv("PEERLIST_PROFILE_HANDLE", "danielsinewe"))
    parser.add_argument("--report-output", type=Path)
    parser.add_argument("--bundle-output", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = run_workflow(args)
    bundle = build_run_bundle(
        automation_name=PEERLIST_FOLLOW_WORKFLOW,
        report=report,
        artifact_path=str(args.report_output) if args.report_output else None,
        search_url=f"{BASE_URL}{SCROLL_FEED_URL}",
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
