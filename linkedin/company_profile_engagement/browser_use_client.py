from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from urllib.parse import parse_qsl, urlparse


COLLECTOR_SCRIPT = r"""
(() => {
  const text = document.body ? document.body.innerText.toLowerCase() : "";
  const url = window.location.href.toLowerCase();
  const challengeSignals = [
    "captcha",
    "checkpoint",
    "unusual activity",
    "temporary restriction",
    "verify your identity",
    "security check",
  ].filter((signal) => text.includes(signal));

  let actorName = null;
  const actorDataNode = Array.from(document.querySelectorAll("[data-actor-name]"))
    .find((node) => {
      const value = (node.getAttribute("data-actor-name") || "").replace(/\s+/g, " ").trim();
      return value && value.length <= 120;
    });
  if (actorDataNode) {
    actorName = (actorDataNode.getAttribute("data-actor-name") || "").replace(/\s+/g, " ").trim() || null;
  }
  if (!actorName) {
    const actorText = Array.from(
      document.querySelectorAll('div[aria-label="Open actor selection screen"], button, span, div')
    )
      .map((node) => (node.textContent || "").replace(/\s+/g, " ").trim())
      .find((value) => value && value.length <= 120 && /acting as|commenting as|current actor/i.test(value));
    if (actorText) {
      const actorMatch = actorText.match(/(?:acting as|commenting as|current actor)\s*:?\s*(.+)$/i);
      actorName = (actorMatch ? actorMatch[1] : actorText) || null;
    }
  }

  const searchMarkers = [];
  if (text.includes("opportunities") || url.includes("keywords=opportunities")) searchMarkers.push("keyword:opportunities");
  if (text.includes("posts")) searchMarkers.push("content-view");
  if (text.includes("latest")) searchMarkers.push("latest-sort");
  if (text.includes("photo") || text.includes("images") || url.includes("contenttype=%5b%22photos%22%5d")) searchMarkers.push("photo-filter");
  if (text.includes("organization filter") || text.includes("mentions organization") || url.includes("mentionsorganization=")) searchMarkers.push("org-filter");

  const normalizeId = (value) => {
    if (!value) return null;
    const match = String(value).match(/(urn:li:[^"'\\s>]+|activity:\\d+|comment-[\\w-]+)/i);
    return match ? match[1] : String(value);
  };

  const normalizeUrl = (value) => {
    if (!value) return null;
    try {
      return new URL(String(value), window.location.origin).toString();
    } catch (_) {
      return null;
    }
  };

  const reactionControlFor = (scope) => {
    return Array.from(scope.querySelectorAll("button,[role='button'],p[role='button']"))
      .find((candidate) => /Reaction button state|(^|\s)like(\s|$)|react/i.test((candidate.innerText || candidate.textContent || candidate.getAttribute("aria-label") || "").trim()));
  };

  const commentRootsFor = (scope) => {
    const candidates = Array.from(scope.querySelectorAll(
      '[componentkey^="replaceableComment_"], [data-id*="urn:li:comment:"], [data-urn*="urn:li:comment:"], article.comments-comment-item, li.comments-comment-item'
    ));
    return candidates
      .filter((node, idx, all) => !all.some((other) => other !== node && other.contains(node)))
      .filter((node) => {
        const content = (node.innerText || node.textContent || "").replace(/\s+/g, " ").trim();
        if (!content || content.length < 8) return false;
        return Array.from(node.querySelectorAll("button,[role='button'],p[role='button'],a"))
          .some((candidate) => /Reaction button state|(^|\s)like(\s|$)|reply|react/i.test((candidate.innerText || candidate.textContent || candidate.getAttribute("aria-label") || "").trim()));
      });
  };

  const fingerprint = (value) => {
    let hash = 0;
    const input = String(value || "");
    for (let i = 0; i < input.length; i += 1) {
      hash = ((hash << 5) - hash + input.charCodeAt(i)) | 0;
    }
    return `fp-${Math.abs(hash)}`;
  };

  const postRoots = Array.from(document.querySelectorAll("article, div.feed-shared-update-v2, div[role='listitem']"))
    .filter((node) => {
      const hasReaction = node.querySelector("button[aria-label*='Reaction button state']");
      const hasActorPicker = node.querySelector("div[aria-label='Open actor selection screen']");
      return hasReaction || hasActorPicker;
    });

  const posts = postRoots.map((root, index) => {
    const rootText = (root.innerText || root.textContent || "").trim();
    const authorLink = root.querySelector("a[href*='/in/'], a[href*='/company/']");
    const canonicalLink = root.querySelector("a[href*='activity:'], a[href*='/posts/']");
    const canonicalUrl = normalizeUrl(canonicalLink?.href);
    const postId = normalizeId(
      root.getAttribute("data-urn") ||
      root.getAttribute("data-id") ||
      root.getAttribute("data-post-id") ||
      canonicalLink?.href
    ) || fingerprint(`${authorLink?.href || "unknown"}|${rootText.slice(0, 240)}|${index}`);
    const likeButton = Array.from(root.querySelectorAll("button, [role='button']")).find((node) => /like|react/i.test(node.getAttribute("aria-label") || node.textContent || ""));
    const repostButton = Array.from(root.querySelectorAll("button, [role='button']")).find((node) => /repost/i.test((node.getAttribute("aria-label") || node.textContent || "").trim()));
    const reactionButtons = Array.from(root.querySelectorAll("button, [role='button']")).filter((node) => /Reaction button state/i.test(node.getAttribute("aria-label") || ""));
    const commentToggle = Array.from(root.querySelectorAll("button, [role='button']")).find((node) => /comment/i.test(node.getAttribute("aria-label") || node.textContent || ""));
    const replyToggles = Array.from(root.querySelectorAll("button, [role='button']")).filter((node) => /reply|repl(y|ies)/i.test(node.getAttribute("aria-label") || node.textContent || ""));
    const comments = commentRootsFor(root)
      .map((node, commentIndex) => {
      const componentKey = node.getAttribute("componentkey") || "";
      const commentMatch = componentKey.match(/replaceableComment_(urn:li:comment:\([^)]+\))/i);
      const explicitId = node.getAttribute("data-id") || node.getAttribute("data-urn") || "";
      const explicitMatch = explicitId.match(/(urn:li:comment:\([^)]+\))/i);
      const commentId = explicitMatch?.[1] || commentMatch?.[1] || `comment-${postId}-${commentIndex}`;
      const commentLikeButton = reactionControlFor(node);
      return {
        comment_id: commentId,
        parent_comment_id: node.getAttribute("data-parent-comment-id"),
        text: (node.textContent || "").trim(),
        liked: /reaction button state:\s*like/i.test((commentLikeButton?.innerText || commentLikeButton?.textContent || commentLikeButton?.getAttribute("aria-label") || "").trim()) || (node.getAttribute("data-liked") === "true"),
        like_selector: commentLikeButton ? `card:${index}:comment:${commentIndex}:like` : null,
      };
    });

    return {
      post_id: postId,
      post_url: canonicalUrl,
      text: rootText,
      sponsored: /sponsored|promoted/i.test(root.textContent || ""),
      already_liked: (likeButton?.getAttribute("aria-pressed") || "").toLowerCase() === "true" || root.getAttribute("data-liked") === "true",
      already_reposted: /reposted/i.test((repostButton?.textContent || repostButton?.getAttribute("aria-label") || "").trim()) || root.getAttribute("data-reposted") === "true",
      interactable: !root.matches("[aria-hidden='true']"),
      like_selector: likeButton ? `card:${index}:like` : null,
      repost_selector: repostButton ? `card:${index}:repost` : null,
      comments_expanded: comments.length > 0,
      comment_toggle_selector: commentToggle ? `card:${index}:comment-toggle` : null,
      reply_toggle_selectors: [],
      comments,
    };
  });

  return JSON.stringify({
    actor_name: actorName,
    actor_verified: Boolean(actorName),
    search_shape_ok: searchMarkers.length === 5,
    search_markers: searchMarkers,
    challenge_signals: challengeSignals,
    posts,
  });
})()
"""

FOLLOW_COLLECTOR_SCRIPT = r"""
(() => {
  const text = document.body ? document.body.innerText.toLowerCase() : "";
  const challengeSignals = [
    "captcha",
    "checkpoint",
    "unusual activity",
    "temporary restriction",
    "verify your identity",
    "security check",
  ].filter((signal) => text.includes(signal));

  const modal = document.querySelector(".org-page-follows-modal");
  const followingTab = modal
    ? Array.from(modal.querySelectorAll("[role='tab']")).find((node) => /following/i.test((node.textContent || "").trim()))
    : null;
  const activeTab = modal
    ? Array.from(modal.querySelectorAll("[role='tab']")).find((node) => node.getAttribute("aria-selected") === "true")
    : null;
  const followingCountMatch = (followingTab?.textContent || "").match(/\((\d+)\)/);

  const normalizeUrl = (value) => {
    if (!value) return null;
    try {
      return new URL(String(value), window.location.origin).toString();
    } catch (_) {
      return null;
    }
  };

  const companyIdFromUrl = (value) => {
    if (!value) return null;
    const match = String(value).match(/\/company\/(\d+)/i);
    return match ? match[1] : null;
  };

  const labelText = (node) => (node?.getAttribute("aria-label") || node?.textContent || "").replace(/\s+/g, " ").trim();

  const agencies = modal
    ? Array.from(modal.querySelectorAll(".org-page-follows-modal__follow-item")).map((item, index) => {
        const link = item.querySelector("a[href*='/company/']");
        const button = Array.from(item.querySelectorAll("button,[role='button']")).find((node) => /follow|following|unfollow/i.test(labelText(node)));
        const spans = Array.from(item.querySelectorAll("span"))
          .map((node) => (node.textContent || "").replace(/\s+/g, " ").trim())
          .filter(Boolean);
        const companyUrl = normalizeUrl(link?.href);
        const companyId = companyIdFromUrl(companyUrl) || `company-${index}`;
        const buttonLabel = labelText(button);
        const name = spans[0] || labelText(link) || companyId;
        const subtitle = spans.find((value, spanIndex) => spanIndex > 0 && !/followers?/i.test(value) && value !== buttonLabel) || null;
        const followersText = spans.find((value) => /followers?/i.test(value)) || null;
        const alreadyFollowing = /following|unfollow/i.test(buttonLabel) && !/^follow(\s|$)/i.test(buttonLabel);

        return {
          company_id: companyId,
          company_url: companyUrl || `https://www.linkedin.com/company/${companyId}/`,
          name,
          subtitle,
          followers_text: followersText,
          already_following: alreadyFollowing,
          follow_selector: button && /^follow(\s|$)/i.test(buttonLabel) ? `agency:${index}:follow` : null,
        };
      })
    : [];

  return JSON.stringify({
    page_shape_ok:
      !!modal &&
      /company page admin/i.test(document.title || "") &&
      /(find pages to follow|manage following)/i.test(modal.textContent || "") &&
      !!modal.querySelector("input[placeholder='Add Pages to follow']"),
    challenge_signals: challengeSignals,
    following_count: followingCountMatch ? Number(followingCountMatch[1]) : null,
    active_tab: activeTab ? (activeTab.textContent || "").replace(/\s+/g, " ").trim() : null,
    agencies,
  });
})()
"""


class BrowserUseError(RuntimeError):
    pass


class BrowserUseClient:
    def __init__(self, *, session_name: str, chrome_profile: str) -> None:
        self.session_name = session_name
        self.chrome_profile = chrome_profile
        self.binary = self._resolve_binary()

    def _resolve_binary(self) -> str:
        explicit_env = os.getenv("BROWSER_USE_BIN")
        explicit = Path.home().joinpath(".browser-use-env/bin/browser-use")
        candidates = [
            explicit_env,
            shutil.which("browser-use"),
            shutil.which("browseruse"),
            shutil.which("bu"),
            str(explicit),
            str(Path.home() / "Library/Python/3.11/bin/browser-use"),
        ]
        for candidate in candidates:
            if candidate and Path(candidate).exists():
                return str(Path(candidate))
        raise BrowserUseError(
            "`browser-use` is not installed or not on PATH. Set BROWSER_USE_BIN if it is installed in a custom location."
        )

    def _run(self, *args: str) -> str:
        cmd = [self.binary, "--session", self.session_name, "--profile", self.chrome_profile, *args]
        result = subprocess.run(cmd, check=False, capture_output=True, text=True)
        if result.returncode != 0:
            raise BrowserUseError(result.stderr.strip() or result.stdout.strip() or "browser-use command failed")
        return result.stdout.strip()

    def open(self, url: str) -> None:
        self._run("open", url)
        self._focus_tab_for_url(url)

    def _focus_tab_for_url(self, expected_url: str, max_tabs: int = 12) -> None:
        if self._page_matches_expected_url(expected_url):
            return
        for index in range(max_tabs):
            try:
                self._run("switch", str(index))
            except BrowserUseError as exc:
                if "Invalid tab index" in str(exc):
                    break
                raise
            if self._page_matches_expected_url(expected_url):
                return

    def _page_matches_expected_url(self, expected_url: str) -> bool:
        state = self.get_page_state()
        current_url = str(state.get("url") or "")
        if not current_url:
            return False
        return self._urls_match(current_url, expected_url)

    @staticmethod
    def _urls_match(current_url: str, expected_url: str) -> bool:
        current = urlparse(current_url)
        expected = urlparse(expected_url)
        if current.netloc.lower() != expected.netloc.lower():
            return False
        if current.path.rstrip("/") != expected.path.rstrip("/"):
            return False
        expected_query = dict(parse_qsl(expected.query, keep_blank_values=True))
        current_query = dict(parse_qsl(current.query, keep_blank_values=True))
        return all(current_query.get(key) == value for key, value in expected_query.items())

    def get_page_state(self) -> dict[str, object]:
        raw = self.eval(
            r"""
(() => {
  const text = document.body ? document.body.innerText.toLowerCase() : "";
  const title = document.title || "";
  const url = window.location.href || "";
  const hasActorSelector = !!document.querySelector('div[aria-label="Open actor selection screen"]');
  const loggedOut = /\/uas\/login|\/checkpoint\//i.test(url) ||
    /sign in|join now|forgot password/i.test(text) ||
    /linkedin login/i.test(title.toLowerCase());
  return JSON.stringify({
    url,
    title,
    has_actor_selector: hasActorSelector,
    logged_out: loggedOut,
  });
})()
"""
        )
        data = json.loads(raw)
        return {
            "url": data.get("url", ""),
            "title": data.get("title", ""),
            "has_actor_selector": bool(data.get("has_actor_selector")),
            "logged_out": bool(data.get("logged_out")),
        }

    def get_html(self) -> str:
        raw = self._run("get", "html", "--selector", "body")
        if raw.startswith("html: "):
            return raw.split("html: ", 1)[1]
        return raw

    def collect_payload(self) -> str:
        raw = self._run("eval", COLLECTOR_SCRIPT)
        if raw.startswith("result:"):
            return raw.split("result:", 1)[1].strip()
        return raw

    def collect_follow_payload(self) -> str:
        raw = self._run("eval", FOLLOW_COLLECTOR_SCRIPT)
        if raw.startswith("result:"):
            return raw.split("result:", 1)[1].strip()
        return raw

    def eval(self, script: str) -> str:
        raw = self._run("eval", script)
        if raw.startswith("result:"):
            return raw.split("result:", 1)[1].strip()
        return raw

    def ensure_actor(self, actor_name: str) -> bool:
        self.dismiss_noise_dialogs()
        open_script = r"""
(() => {{
  const openers = Array.from(document.querySelectorAll('div[aria-label="Open actor selection screen"]'));
  if (!openers.length) return "no-opener";
  openers[0].click();
  return "opened";
}})()
"""
        select_script = f"""
(() => {{
  const dialog = Array.from(document.querySelectorAll('dialog'))
    .find((node) => /Comment, react, and repost as/.test(node.innerText || ""));
  if (!dialog) return "no-dialog";
  if (dialog.querySelector('[data-testid="loader"]')) return "loading";
  const candidate = Array.from(dialog.querySelectorAll('label, button, div, span'))
    .find((node) => (node.textContent || "").trim() === {json.dumps(actor_name)});
  if (!candidate) return "missing-actor";
  candidate.click();
  const save = Array.from(dialog.querySelectorAll('button, div[role="button"], span'))
    .find((node) => /^save$/i.test((node.textContent || "").trim()));
  if (!save) return "missing-save";
  save.click();
  return "ok";
}})()
"""
        for _ in range(8):
            opened = self.eval(open_script)
            if opened == "no-opener":
                self.sleep(1.0)
                continue
            self.sleep(0.8)
            result = self.eval(select_script)
            if result == "ok":
                return True
            if result == "loading":
                self.sleep(1.0)
                continue
            self.dismiss_noise_dialogs()
            self.sleep(1.0)
        return False

    def dismiss_noise_dialogs(self) -> None:
        script = r"""
(() => {
  const dialogs = Array.from(document.querySelectorAll('dialog'));
  for (const dialog of dialogs) {
    const text = (dialog.innerText || "").trim();
    if (/Ad Options|Don’t want to see this|Don't want to see this/i.test(text)) {
      const dismiss = dialog.querySelector('button[aria-label="Dismiss"]');
      if (dismiss) dismiss.click();
    }
  }
  return "ok";
})()
"""
        self.eval(script)

    def screenshot(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._run("screenshot", str(path))

    def click_selector(self, selector: str) -> None:
        agency_match = re.fullmatch(r"agency:(\d+):follow", selector)
        if agency_match:
            return self._click_agency_follow(int(agency_match.group(1)))

        action_match = re.fullmatch(r"card:(\d+):(like|repost|comment-toggle|comment:(\d+):like)", selector)
        if action_match:
            card_index = int(action_match.group(1))
            action = action_match.group(2)
            comment_index = action_match.group(3)
            if action == "like":
                return self._click_card_like(card_index)
            if action == "repost":
                return self._click_card_repost(card_index)
            if action == "comment-toggle":
                return self._click_card_comment_toggle(card_index)
            if comment_index is not None:
                return self._click_comment_like(card_index, int(comment_index))
        script = f"""
(() => {{
  const node = document.querySelector({json.dumps(selector)});
  if (!node) throw new Error("selector not found: {selector}");
  node.click();
  return "clicked";
}})()
"""
        self._run("eval", script)

    def _click_card_like(self, card_index: int) -> None:
        script = f"""
(() => {{
  const cards = Array.from(document.querySelectorAll("div[role='listitem']")).filter((node) => /Feed post/.test(node.innerText || ""));
  const card = cards[{card_index}];
  if (!card) throw new Error("card not found");
  const button = Array.from(card.querySelectorAll("button,[role='button']")).find((node) => /Reaction button state/i.test(node.getAttribute("aria-label") || ""));
  if (!button) throw new Error("like button not found");
  button.click();
  return "clicked";
}})()
"""
        self.eval(script)

    def _click_agency_follow(self, agency_index: int) -> None:
        script = f"""
(() => {{
  const modal = document.querySelector(".org-page-follows-modal");
  if (!modal) throw new Error("follow modal not found");
  const items = Array.from(modal.querySelectorAll(".org-page-follows-modal__follow-item"));
  const item = items[{agency_index}];
  if (!item) throw new Error("agency row not found");
  const button = Array.from(item.querySelectorAll("button,[role='button']")).find((node) => /^follow(\\s|$)/i.test((node.getAttribute("aria-label") || node.textContent || "").trim()));
  if (!button) throw new Error("follow button not found");
  button.click();
  return "clicked";
}})()
"""
        self.eval(script)

    def _click_card_comment_toggle(self, card_index: int) -> None:
        script = f"""
(() => {{
  const cards = Array.from(document.querySelectorAll("div[role='listitem']")).filter((node) => /Feed post/.test(node.innerText || ""));
  const card = cards[{card_index}];
  if (!card) throw new Error("card not found");
  const button = Array.from(card.querySelectorAll("button,[role='button']")).find((node) => /comment/i.test((node.getAttribute("aria-label") || node.textContent || "").trim()));
  if (!button) throw new Error("comment toggle not found");
  button.click();
  return "clicked";
}})()
"""
        self.eval(script)

    def _click_card_repost(self, card_index: int) -> None:
        script = f"""
(() => {{
  const cards = Array.from(document.querySelectorAll("div[role='listitem']")).filter((node) => /Feed post/.test(node.innerText || ""));
  const card = cards[{card_index}];
  if (!card) throw new Error("card not found");
  const button = Array.from(card.querySelectorAll("button,[role='button']")).find((node) => /^repost$/i.test((node.textContent || node.getAttribute("aria-label") || "").trim()));
  if (!button) throw new Error("repost button not found");
  button.click();

  const candidates = Array.from(document.querySelectorAll("button,[role='button'],a,div[role='menuitem']"))
    .filter((node) => !card.contains(node))
    .find((node) => /repost to feed|repost now|repost$/i.test((node.textContent || node.getAttribute("aria-label") || "").trim()));

  if (candidates) {{
    candidates.click();
    return "reposted";
  }}

  const inlineReposted = /^reposted$/i.test((button.textContent || button.getAttribute("aria-label") || "").trim());
  if (inlineReposted) {{
    return "reposted";
  }}
  throw new Error("repost confirmation not found");
}})()
"""
        self.eval(script)

    def _click_comment_like(self, card_index: int, comment_index: int) -> None:
        script = f"""
(() => {{
  const cards = Array.from(document.querySelectorAll("div[role='listitem']")).filter((node) => /Feed post/.test(node.innerText || ""));
  const card = cards[{card_index}];
  if (!card) throw new Error("card not found");
  const commentBlocks = Array.from(card.querySelectorAll('[componentkey^="replaceableComment_"], [data-id*="urn:li:comment:"], [data-urn*="urn:li:comment:"], article.comments-comment-item, li.comments-comment-item'))
    .filter((node, idx, all) => !all.some((other) => other !== node && other.contains(node)))
    .filter((node) => {{
      const content = (node.innerText || node.textContent || "").replace(/\\s+/g, " ").trim();
      if (!content || content.length < 8) return false;
      return Array.from(node.querySelectorAll("button,[role='button'],p[role='button'],a"))
        .some((candidate) => /Reaction button state|(^|\\s)like(\\s|$)|reply|react/i.test((candidate.innerText || candidate.textContent || candidate.getAttribute("aria-label") || "").trim()));
    }});
  const block = commentBlocks[{comment_index}];
  if (!block) throw new Error("comment block not found");
  const button = Array.from(block.querySelectorAll("button,[role='button'],p[role='button']"))
    .find((candidate) => /Reaction button state|(^|\\s)like(\\s|$)|react/i.test((candidate.innerText || candidate.textContent || candidate.getAttribute("aria-label") || "").trim()));
  if (!button) throw new Error("comment like button not found");
  button.click();
  return "clicked";
}})()
"""
        self.eval(script)

    def load_more_comments(self, card_index: int) -> bool:
        script = f"""
(() => {{
  const cards = Array.from(document.querySelectorAll("div[role='listitem']")).filter((node) => /Feed post/.test(node.innerText || ""));
  const card = cards[{card_index}] || document.body;
  const buttons = Array.from(card.querySelectorAll("button,[role='button'],a,span[role='button']"));
  const target = buttons.find((node) => /load more comments|view more comments|see more comments|more comments|previous comments/i.test((node.textContent || node.getAttribute("aria-label") || "").trim()));
  if (!target) return "missing";
  target.click();
  return "clicked";
}})()
"""
        try:
            raw = self.eval(script)
        except BrowserUseError:
            return False
        return "clicked" in raw

    def sleep(self, seconds: float) -> None:
        script = f"""
(() => new Promise((resolve) => setTimeout(() => resolve("ok"), {int(seconds * 1000)})))()
"""
        self._run("eval", script)

    def scroll_down(self, amount: int = 1400) -> None:
        self._run("scroll", "down", "--amount", str(amount))

    def scroll_results(self, amount: int = 1400) -> None:
        script = f"""
(() => {{
  const candidates = Array.from(document.querySelectorAll("main, section, div"))
    .filter((node) => node instanceof HTMLElement)
    .filter((node) => node.scrollHeight > node.clientHeight + 200)
    .filter((node) => node.clientHeight > 250)
    .map((node) => {{
      const text = (node.className || "") + " " + (node.getAttribute("aria-label") || "");
      const postCount = node.querySelectorAll("article, div.feed-shared-update-v2, div[role='listitem']").length;
      const score =
        postCount * 100 +
        (/search|results|feed|scaffold|main/i.test(text) ? 25 : 0) +
        Math.min(node.clientHeight, 1200);
      return {{ node, score, postCount, scrollTop: node.scrollTop }};
    }})
    .sort((a, b) => b.score - a.score);

  const target = candidates[0]?.node;
  if (!target) {{
    window.scrollBy(0, {amount});
    return "window";
  }}

  target.scrollBy({{ top: {amount}, behavior: "instant" }});
  return JSON.stringify({{
    mode: "container",
    tag: target.tagName,
    className: target.className || "",
    scrollTop: target.scrollTop,
    scrollHeight: target.scrollHeight,
    clientHeight: target.clientHeight
  }});
}})()
"""
        try:
            self.eval(script)
        except BrowserUseError:
            self.scroll_down(amount)

    def load_more_results(self) -> bool:
        script = r"""
(() => {
  const buttons = Array.from(document.querySelectorAll("button, a, div[role='button'], span[role='button']"));
  const target = buttons.find((node) => /load more|show more results|see more results|more results/i.test(
    (node.textContent || node.getAttribute("aria-label") || "").trim()
  ));
  if (!target) return "missing";

  target.scrollIntoView({ block: "center", inline: "nearest" });
  const beforeText = (target.textContent || target.getAttribute("aria-label") || "").trim();
  target.click();
  return JSON.stringify({ status: "clicked", text: beforeText });
})()
"""
        try:
            raw = self.eval(script)
        except BrowserUseError:
            return False
        return "clicked" in raw

    def scroll_follow_modal(self, amount: int = 900) -> bool:
        script = f"""
(() => {{
  const modalContent = document.querySelector(".org-page-follows-modal__content");
  if (!(modalContent instanceof HTMLElement)) return "missing";
  const before = modalContent.scrollTop;
  modalContent.scrollBy({{ top: {amount}, behavior: "instant" }});
  return JSON.stringify({{ before, after: modalContent.scrollTop, scrollHeight: modalContent.scrollHeight, clientHeight: modalContent.clientHeight }});
}})()
"""
        try:
            raw = self.eval(script)
        except BrowserUseError:
            return False
        match = re.search(r'"after"\s*:\s*(\d+)', raw)
        before_match = re.search(r'"before"\s*:\s*(\d+)', raw)
        if not match or not before_match:
            return False
        return int(match.group(1)) > int(before_match.group(1))

    def select_follow_tab(self, label: str) -> bool:
        script = f"""
(() => {{
  const modal = document.querySelector(".org-page-follows-modal");
  if (!modal) return "missing";
  const target = Array.from(modal.querySelectorAll("[role='tab']")).find((node) => (node.textContent || "").trim().toLowerCase().startsWith({json.dumps(label.lower())}));
  if (!target) return "missing";
  if (target.getAttribute("aria-selected") === "true") return "selected";
  target.click();
  return "clicked";
}})()
"""
        try:
            raw = self.eval(script)
        except BrowserUseError:
            return False
        return raw in {"clicked", "selected"}

    def close(self) -> None:
        try:
            self._run("close")
        except BrowserUseError:
            return
