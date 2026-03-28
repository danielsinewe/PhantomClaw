from __future__ import annotations

import json
import re
from dataclasses import asdict

from .models import CommentSnapshot, FeedSnapshot, PostSnapshot


CHALLENGE_PATTERNS = (
    "captcha",
    "checkpoint",
    "unusual activity",
    "temporary restriction",
    "verify your identity",
    "security check",
)

SEARCH_MARKERS = (
    ("keyword:opportunities", ("opportunities",)),
    ("content-view", ("posts",)),
    ("latest-sort", ("latest",)),
    ("photo-filter", ("photo", "images")),
    ("org-filter", ("organization filter", "mentions organization", "company filter")),
)


def canonical_post_url(post_id: str | None, raw_url: str | None = None) -> str | None:
    if raw_url:
        return raw_url
    if not post_id:
        return None
    if re.fullmatch(r"urn:li:activity:\d+", post_id):
        return f"https://www.linkedin.com/feed/update/{post_id}"
    if re.fullmatch(r"activity:\d+", post_id):
        return f"https://www.linkedin.com/feed/update/urn:li:{post_id}"
    return None


def _clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _first(items: list[str]) -> str | None:
    return items[0] if items else None


def parse_feed_html(html: str, actor_name: str) -> FeedSnapshot:
    lower = html.lower()
    challenge_signals = [pattern for pattern in CHALLENGE_PATTERNS if pattern in lower]
    search_markers = [name for name, needles in SEARCH_MARKERS if any(needle in lower for needle in needles)]
    actor_patterns = [
        rf'acting as\s*{re.escape(actor_name.lower())}',
        rf'commenting as\s*{re.escape(actor_name.lower())}',
        rf'current actor[^<]*{re.escape(actor_name.lower())}',
        rf'identity[^<]*{re.escape(actor_name.lower())}',
    ]
    actor_verified = any(re.search(pattern, lower) for pattern in actor_patterns)
    actor_candidates = re.findall(r'data-actor-name="([^"]+)"', html, flags=re.IGNORECASE)
    if not actor_candidates:
        actor_candidates = re.findall(r'acting as\s*([^<]+)', html, flags=re.IGNORECASE)
    actor_candidate = _first([_clean_text(item) for item in actor_candidates]) or actor_name if actor_verified else None
    posts = _extract_posts(html)
    return FeedSnapshot(
        actor_name=actor_candidate,
        actor_verified=actor_verified,
        search_shape_ok=len(search_markers) == len(SEARCH_MARKERS),
        search_markers=search_markers,
        challenge_signals=challenge_signals,
        posts=posts,
    )


def _extract_posts(html: str) -> list[PostSnapshot]:
    posts: list[PostSnapshot] = []
    pattern = re.compile(
        r'(?P<open_tag><article[^>]*data-post-id="(?P<post_id>[^"]+)"[^>]*>)(?P<body>.*?)</article>',
        flags=re.IGNORECASE | re.DOTALL,
    )
    for match in pattern.finditer(html):
        open_tag = match.group("open_tag")
        body = match.group("body")
        text = _clean_text(re.sub(r"<[^>]+>", " ", body))
        post_id = match.group("post_id")
        sponsored = 'data-sponsored="true"' in open_tag.lower() or "sponsored" in text.lower() or "promoted" in text.lower()
        interactable = 'data-interactable="false"' not in open_tag.lower()
        already_liked = 'data-liked="true"' in open_tag.lower()
        like_selector = _match_attr(body, "data-post-like-selector")
        comments_expanded = 'data-comments-expanded="true"' in open_tag.lower()
        comment_toggle_selector = _match_attr(body, "data-comment-toggle-selector")
        reply_toggle_selectors = re.findall(r'data-reply-toggle-selector="([^"]+)"', body, flags=re.IGNORECASE)
        comments = _extract_comments(body, post_id)
        posts.append(
            PostSnapshot(
                post_id=post_id,
                post_url=canonical_post_url(post_id, _match_attr(open_tag, "data-post-url")),
                text=text,
                sponsored=sponsored,
                already_liked=already_liked,
                already_reposted='data-reposted="true"' in open_tag.lower(),
                interactable=interactable,
                like_selector=like_selector,
                repost_selector=_match_attr(body, "data-post-repost-selector"),
                comments_expanded=comments_expanded,
                comment_toggle_selector=comment_toggle_selector,
                reply_toggle_selectors=reply_toggle_selectors,
                comments=comments,
            )
        )
    return posts


def _extract_comments(body: str, post_id: str) -> list[CommentSnapshot]:
    comments: list[CommentSnapshot] = []
    pattern = re.compile(
        r'(?P<open_tag><div[^>]*data-comment-id="(?P<comment_id>[^"]+)"[^>]*>)(?P<body>.*?)</div>',
        flags=re.IGNORECASE | re.DOTALL,
    )
    for match in pattern.finditer(body):
        open_tag = match.group("open_tag")
        comment_body = match.group("body")
        comment_id = match.group("comment_id")
        parent_comment_id = _match_attr(open_tag, "data-parent-comment-id")
        comments.append(
            CommentSnapshot(
                comment_id=comment_id,
                parent_post_id=post_id,
                parent_comment_id=parent_comment_id,
                text=_clean_text(re.sub(r"<[^>]+>", " ", comment_body)),
                liked='data-liked="true"' in open_tag.lower(),
                like_selector=_match_attr(comment_body, "data-comment-like-selector"),
            )
        )
    return comments


def _match_attr(text: str, attr_name: str) -> str | None:
    match = re.search(rf'{re.escape(attr_name)}="([^"]+)"', text, flags=re.IGNORECASE)
    return match.group(1) if match else None


def extract_activity_ids_from_html(html: str) -> list[str]:
    ids = re.findall(r"commentsSectionAnchor-(urn:li:activity:\d+)", html)
    unique: list[str] = []
    for item in ids:
        if item not in unique:
            unique.append(item)
    return unique


def parse_browser_payload(payload: str, actor_name: str, html: str | None = None) -> FeedSnapshot:
    data = json.loads(payload)
    if "html" in data:
        return parse_feed_html(data["html"], actor_name)
    ordered_ids = extract_activity_ids_from_html(html or "")
    posts = []
    for index, raw_post in enumerate(data.get("posts", [])):
        resolved_post_id = raw_post["post_id"]
        if resolved_post_id.startswith("fp-") and index < len(ordered_ids):
            resolved_post_id = ordered_ids[index]
        comments = [
            CommentSnapshot(
                comment_id=item["comment_id"],
                parent_post_id=resolved_post_id,
                parent_comment_id=item.get("parent_comment_id"),
                text=item.get("text", ""),
                liked=item.get("liked", False),
                like_selector=item.get("like_selector"),
            )
            for item in raw_post.get("comments", [])
        ]
        posts.append(
            PostSnapshot(
                post_id=resolved_post_id,
                post_url=canonical_post_url(resolved_post_id, raw_post.get("post_url")),
                text=raw_post.get("text", ""),
                sponsored=raw_post.get("sponsored", False),
                already_liked=raw_post.get("already_liked", False),
                already_reposted=raw_post.get("already_reposted", False),
                interactable=raw_post.get("interactable", True),
                like_selector=raw_post.get("like_selector"),
                repost_selector=raw_post.get("repost_selector"),
                comments_expanded=raw_post.get("comments_expanded", False),
                comment_toggle_selector=raw_post.get("comment_toggle_selector"),
                reply_toggle_selectors=raw_post.get("reply_toggle_selectors", []),
                comments=comments,
            )
        )
    payload_actor_name = data.get("actor_name")
    actor_verified = bool(data.get("actor_verified", False))
    if payload_actor_name and actor_name:
        actor_verified = payload_actor_name.strip().lower() == actor_name.strip().lower()
    return FeedSnapshot(
        actor_name=payload_actor_name,
        actor_verified=actor_verified,
        search_shape_ok=data.get("search_shape_ok", False),
        search_markers=data.get("search_markers", []),
        challenge_signals=data.get("challenge_signals", []),
        posts=posts,
    )


def snapshot_to_json(snapshot: FeedSnapshot) -> str:
    return json.dumps(snapshot.to_dict(), indent=2, sort_keys=True)
