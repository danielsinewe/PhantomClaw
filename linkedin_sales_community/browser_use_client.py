from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path


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


class BrowserUseClient:
    def __init__(self, *, session_name: str, chrome_profile: str) -> None:
        self.session_name = session_name
        self.chrome_profile = chrome_profile
        self.binary = self._resolve_binary()

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
        result = subprocess.run(cmd, check=False, capture_output=True, text=True)
        if result.returncode != 0:
            raise BrowserUseError(result.stderr.strip() or result.stdout.strip() or "browser-use command failed")
        return result.stdout.strip()

    def open(self, url: str) -> None:
        self._run("open", url)

    def get_html(self) -> str:
        raw = self._run("get", "html", "--selector", "body")
        return raw.split("html: ", 1)[1] if raw.startswith("html: ") else raw

    def collect_payload(self) -> str:
        raw = self._run("eval", COLLECTOR_SCRIPT)
        return raw.split("result:", 1)[1].strip() if raw.startswith("result:") else raw

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
