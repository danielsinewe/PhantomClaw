from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from urllib.parse import parse_qsl, urlparse


COLLECTOR_SCRIPT = r"""
(() => {
  const text = document.body ? document.body.innerText.toLowerCase() : "";
  const url = window.location.href.toLowerCase();
  const challengeSignals = ["captcha", "checkpoint", "unusual activity", "security check"].filter((s) => text.includes(s));
  const pageTitle = document.title || null;
  const loggedIn = !/sign in|login/i.test(pageTitle || "") && !/logged out/i.test(text);
  const itemRoots = Array.from(document.querySelectorAll("article, [role='listitem'], li"))
    .filter((node) => (node.innerText || node.textContent || "").trim().length > 40);

  const normalize = (value, fallback) => {
    const text = String(value || fallback || "").replace(/\s+/g, " ").trim();
    return text || fallback;
  };

  const cssEscape = (value) => String(value || "")
    .replace(/\\/g, "\\\\")
    .replace(/"/g, '\\"')
    .replace(/\[/g, "\\[")
    .replace(/\]/g, "\\]");

  const items = itemRoots.slice(0, 20).map((root, index) => {
    const raw = normalize(root.innerText || root.textContent, "");
    const rootTag = (root.tagName || "article").toLowerCase();
    const heading = Array.from(root.querySelectorAll("h1,h2,h3,h4,strong,span,div"))
      .map((node) => normalize(node.textContent, ""))
      .find((value) => value.length > 0 && value.length < 120) || raw.slice(0, 120);
    const buttons = Array.from(root.querySelectorAll("button,[role='button'],a"))
      .map((node, buttonIndex) => {
        const label = normalize(node.getAttribute("aria-label") || node.textContent, "");
        const tag = (node.tagName || "").toLowerCase() || "button";
        const aria = node.getAttribute("aria-label");
        const selector = aria ? `${tag}[aria-label="${cssEscape(aria)}"]` : `${tag}`;
        return { label, selector, buttonIndex };
      })
      .filter((entry) => entry.label);
    const action = buttons.find((entry) => /^like$|^react$|^recommend$|^follow$|^save$/i.test(entry.label) || /like|react|recommend|follow/i.test(entry.label));
    const highSignal =
      /leaderboard|rank|top member|top contributor|most active|featured|spotlight/i.test(raw) ||
      /leaderboard|rank|top/i.test(heading) ||
      /community resources|explore onboarding|visit the sales assistant hub|join a language hub|submit it here|product idea/i.test(raw) ||
      /community|hub|onboarding|submit|language/i.test(heading) ||
      /explore|visit|join|submit/i.test(action?.label || "");
    return {
      item_id: `item-${index}-${Math.abs((heading + raw).split("").reduce((h, ch) => ((h << 5) - h + ch.charCodeAt(0)) | 0, 0))}`,
      title: heading,
      subtitle: null,
      detail: raw.slice(0, 500),
      action_label: action ? action.label : null,
      action_selector: action ? `${rootTag}:nth-of-type(${index + 1}) ${action.selector}` : null,
      high_signal: highSignal,
    };
  });

  const knownSelectors = Array.from(document.querySelectorAll("a"))
    .map((node) => {
      const text = normalize(node.getAttribute("title") || node.textContent, "");
      const href = node.getAttribute("href") || "";
      const id = node.id || null;
      const selector = id ? `#${id}` : href ? `a[href="${cssEscape(href)}"]` : null;
      return { text, href, id, selector };
    })
    .filter((entry) => entry.selector && (
      /community onboarding|competitions & challenges|recently active conversations|help answer questions|sales assistant hub|language hub|product idea|submit it here|community resources/i.test(entry.text) ||
      /community-onboarding|competitions-challenges|recent|unanswered|topic\/new|language/i.test(entry.href)
    ));

  for (const item of items) {
    if (item.action_selector) continue;
    const match = knownSelectors.find((entry) => /community onboarding|competitions & challenges|recently active conversations|help answer questions|sales assistant hub|language hub|product idea|submit it here|community resources/i.test(`${entry.text} ${entry.href}`));
    if (match) {
      item.action_label = match.text;
      item.action_selector = match.selector;
      item.high_signal = true;
      break;
    }
  }

  return JSON.stringify({
    page_title: pageTitle,
    logged_in: loggedIn,
    page_shape_ok: /community|sales/i.test(pageTitle || "") || /leaderboard|rank|member/i.test(text),
    challenge_signals: challengeSignals,
    items,
  });
})()
"""


class BrowserUseError(RuntimeError):
    pass


DEFAULT_COMMAND_TIMEOUT_SECONDS = 45.0


class BrowserUseClient:
    def __init__(self, *, session_name: str, chrome_profile: str, command_timeout_seconds: float | None = None) -> None:
        self.session_name = session_name
        self.chrome_profile = chrome_profile
        self.binary = self._resolve_binary()
        self.command_timeout_seconds = self._resolve_timeout_seconds(command_timeout_seconds)

    def _resolve_binary(self) -> str:
        candidates = [
            os.getenv("BROWSER_USE_BIN"),
            shutil.which("browser-use"),
            shutil.which("browseruse"),
            shutil.which("bu"),
            str(Path.home() / ".browser-use-env/bin/browser-use"),
        ]
        for candidate in candidates:
            if candidate and Path(candidate).exists():
                return str(Path(candidate))
        raise BrowserUseError("browser-use is not installed or not on PATH")

    def _run(self, *args: str) -> str:
        cmd = [self.binary, "--session", self.session_name, "--profile", self.chrome_profile, *args]
        try:
            result = subprocess.run(
                cmd,
                check=False,
                capture_output=True,
                text=True,
                timeout=self.command_timeout_seconds,
            )
        except subprocess.TimeoutExpired as exc:
            suffix = ""
            detail = (exc.stderr or exc.stdout or "").strip() if isinstance(exc.stderr or exc.stdout or "", str) else ""
            if detail:
                suffix = f" ({detail})"
            raise BrowserUseError(
                f"browser-use command timed out after {self.command_timeout_seconds:g}s: {' '.join(args)}{suffix}"
            ) from exc
        if result.returncode != 0:
            raise BrowserUseError(result.stderr.strip() or result.stdout.strip() or "browser-use command failed")
        return result.stdout.strip()

    @staticmethod
    def _resolve_timeout_seconds(command_timeout_seconds: float | None) -> float:
        if command_timeout_seconds is None:
            raw = os.getenv("BROWSER_USE_COMMAND_TIMEOUT_SECONDS", "").strip()
            if not raw:
                return DEFAULT_COMMAND_TIMEOUT_SECONDS
            try:
                command_timeout_seconds = float(raw)
            except ValueError as exc:
                raise BrowserUseError(
                    f"Invalid BROWSER_USE_COMMAND_TIMEOUT_SECONDS value: {raw!r}"
                ) from exc
        if command_timeout_seconds <= 0:
            raise BrowserUseError("BROWSER_USE_COMMAND_TIMEOUT_SECONDS must be greater than zero")
        return float(command_timeout_seconds)

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

    def get_html(self) -> str:
        raw = self._run("get", "html", "--selector", "body")
        return raw.split("html: ", 1)[1] if raw.startswith("html: ") else raw

    def collect_payload(self) -> str:
        raw = self._run("eval", COLLECTOR_SCRIPT)
        return raw.split("result:", 1)[1].strip() if raw.startswith("result:") else raw

    def get_page_state(self) -> dict[str, object]:
        raw = self._run(
            "eval",
            r"""
(() => {
  return JSON.stringify({
    url: window.location.href || "",
    title: document.title || "",
  });
})()
""",
        )
        if raw.startswith("result:"):
            raw = raw.split("result:", 1)[1].strip()
        return json.loads(raw)

    def click_selector(self, selector: str) -> None:
        self._run("click", selector)

    def click_index(self, index: int) -> None:
        self._run("click", str(index))

    def sleep(self, seconds: float) -> None:
        _ = seconds
        return None

    def state(self) -> str:
        return self._run("state")

    def screenshot(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._run("screenshot", str(path))

    def close(self) -> None:
        try:
            self._run("close")
        except Exception:
            pass
