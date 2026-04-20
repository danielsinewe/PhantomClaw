import fs from "node:fs";
import path from "node:path";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || "playwright");

const OPENCLAW_CONFIG =
  process.env.OPENCLAW_CONFIG_PATH || "/data/.openclaw/openclaw.json";
const LOG_PATH =
  process.env.PEERLIST_LOG_PATH ||
  "/data/workspace/memory/peerlist-growth-log.jsonl";
const REPORT_PATH =
  process.env.PEERLIST_REPORT_PATH ||
  "/data/workspace/artifacts/peerlist-scroll-engagement/latest-report.json";
const BUNDLE_PATH =
  process.env.PEERLIST_BUNDLE_PATH ||
  "/data/workspace/artifacts/peerlist-scroll-engagement/latest.bundle.json";
const ARTIFACT_DIR = path.dirname(REPORT_PATH);
const MAX_UPVOTES = Number.parseInt(process.env.PEERLIST_MAX_UPVOTES || "1", 10);
const ENABLE_COMMENTS = process.env.PEERLIST_ENABLE_COMMENTS === "1";
const CLICK_STREAK = process.env.PEERLIST_CLICK_STREAK === "1";
const HEALTHCHECK = process.env.PEERLIST_HEALTHCHECK === "1";
const RECENT_ACTION_WINDOW_HOURS = Number.parseInt(
  process.env.PEERLIST_RECENT_ACTION_WINDOW_HOURS || "72",
  10,
);

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
const CHALLENGE_PATTERN =
  /Cloudflare|captcha|verify you are human|checking your browser|access denied/i;

function readBrowserUseCdpUrls() {
  const config = JSON.parse(fs.readFileSync(OPENCLAW_CONFIG, "utf8"));
  const cdpUrl = config.browser?.profiles?.["browser-use"]?.cdpUrl;
  if (!cdpUrl) {
    throw new Error("browser-use CDP URL is not configured in OpenClaw config");
  }
  const candidates = [cdpUrl];
  try {
    const url = new URL(cdpUrl);
    if (url.searchParams.has("proxyCountryCode")) {
      url.searchParams.delete("proxyCountryCode");
      candidates.push(url.toString());
    }
  } catch {
    // Keep the configured URL as the only candidate when it is not parseable by URL.
  }
  return Array.from(new Set(candidates));
}

function browserCandidates() {
  const providers = (process.env.PEERLIST_BROWSER_PROVIDER_ORDER || "browserbase,browser-use")
    .split(",")
    .map((provider) => provider.trim())
    .filter(Boolean);
  const candidates = [];
  const pushProvider = (provider) => {
    if (provider === "browser-use") {
      for (const cdpUrl of readBrowserUseCdpUrls()) {
        candidates.push({
          provider: "browser-use",
          cdpUrl,
          cookies: null,
        });
      }
      return;
    }

    if (provider === "browserbase" && process.env.BROWSERBASE_API_KEY) {
      candidates.push({
        provider: "browserbase",
        cdpUrl: `wss://connect.browserbase.com?apiKey=${process.env.BROWSERBASE_API_KEY}`,
        cookies: readPeerlistCookies(),
      });
    }
  };

  providers.forEach(pushProvider);
  if (!providers.includes("browser-use")) pushProvider("browser-use");
  if (!providers.includes("browserbase")) pushProvider("browserbase");

  return candidates;
}

function readPeerlistCookies() {
  const raw = process.env.PEERLIST_COOKIES_JSON;
  if (!raw) return null;
  try {
    const cookies = JSON.parse(raw);
    if (!Array.isArray(cookies)) return null;
    return cookies
      .filter((cookie) => cookie && typeof cookie.name === "string" && typeof cookie.value === "string")
      .map((cookie) => {
        const normalized = {
          name: cookie.name,
          value: cookie.value,
          domain: cookie.domain,
          path: cookie.path || "/",
          secure: Boolean(cookie.secure),
          httpOnly: Boolean(cookie.httpOnly),
        };
        if (typeof cookie.expires === "number") {
          normalized.expires = Math.floor(cookie.expires);
        }
        if (cookie.sameSite && ["Strict", "Lax", "None"].includes(cookie.sameSite)) {
          normalized.sameSite = cookie.sameSite;
        }
        return normalized;
      });
  } catch {
    return null;
  }
}

function classifyFailure(reason) {
  if (!reason) return "unknown";
  if (/ERR_TUNNEL_CONNECTION_FAILED|connectOverCDP|ECONNREFUSED|timed? out|WebSocket/i.test(reason)) {
    return "provider_connection_failed";
  }
  if (/actor_not_verified|logged out|Log in|Sign in|session/i.test(reason)) {
    return "peerlist_auth_missing";
  }
  if (CHALLENGE_PATTERN.test(reason)) {
    return "cloudflare_challenge";
  }
  if (/page_shape|upvote button|selector|locator|not visible/i.test(reason)) {
    return "page_shape_changed";
  }
  if (/click_not_verified|not_verified/i.test(reason)) {
    return "action_not_verified";
  }
  if (/sync|run-bundles|PHANTOMCLAW/i.test(reason)) {
    return "sync_failed";
  }
  return "unknown";
}

function failureEntry(reason, extra = {}) {
  return {
    ...extra,
    category: extra.category || classifyFailure(reason),
    reason,
  };
}

function appendJsonl(entry) {
  fs.mkdirSync(path.dirname(LOG_PATH), { recursive: true });
  fs.appendFileSync(LOG_PATH, `${JSON.stringify(entry)}\n`);
}

function writeJson(filePath, payload) {
  fs.mkdirSync(path.dirname(filePath), { recursive: true });
  fs.writeFileSync(filePath, `${JSON.stringify(payload, null, 2)}\n`);
}

function readRecentActionKeys() {
  const keys = new Set();
  if (!fs.existsSync(LOG_PATH)) return keys;

  const cutoff = Date.now() - RECENT_ACTION_WINDOW_HOURS * 60 * 60 * 1000;
  const lines = fs.readFileSync(LOG_PATH, "utf8").split("\n").filter(Boolean).slice(-500);
  for (const line of lines) {
    try {
      const entry = JSON.parse(line);
      const finishedAt = Date.parse(entry.finished_at || entry.ts || "");
      if (Number.isFinite(finishedAt) && finishedAt < cutoff) continue;
      for (const action of entry.actions || []) {
        if (action.type !== "upvote" || !action.verified) continue;
        const key = action.post_key || action.target_url || action.target_excerpt;
        if (key) keys.add(key);
      }
    } catch {
      // Ignore older malformed log entries.
    }
  }
  return keys;
}

async function describeUpvoteButton(button, index) {
  return button
    .evaluate((element, buttonIndex) => {
      let container =
        element.closest("article") ||
        element.closest("[data-scroll-id]") ||
        element.closest("[data-testid]");
      let probe = element;
      for (let depth = 0; !container && probe?.parentElement && depth < 8; depth += 1) {
        probe = probe.parentElement;
        const text = (probe.innerText || "").replace(/\s+/g, " ").trim();
        if (text.length > 80) container = probe;
      }
      container = container || element.closest("div");
      const text = (container?.innerText || element.innerText || "")
        .replace(/\s+/g, " ")
        .trim()
        .slice(0, 500);
      const link = container?.querySelector('a[href*="/scroll/"], a[href*="/post/"], a[href^="/"]');
      const href = link?.href || "";
      const explicitId =
        container?.getAttribute("data-scroll-id") ||
        container?.getAttribute("data-post-id") ||
        container?.getAttribute("data-testid") ||
        "";
      const authorMatch = text.match(/^([^@\n]{2,80})\s+@/) || text.match(/^([A-Z][A-Za-z0-9 ._-]{1,80})\b/);
      return {
        post_key: explicitId || href || text.slice(0, 160) || `visible_upvote_${buttonIndex}`,
        target_url: href || null,
        target_excerpt: text,
        target_name: authorMatch ? authorMatch[1].trim() : `Peerlist visible upvote ${buttonIndex}`,
      };
    }, index)
    .catch(() => ({
      post_key: `visible_upvote_${index}`,
      target_url: null,
      target_excerpt: "",
      target_name: `Peerlist visible upvote ${index}`,
    }));
}

async function upvoteVisiblePosts(page, actions, skipped, recentActionKeys) {
  let clicked = 0;
  let lastTotal = 0;

  if (MAX_UPVOTES <= 0 || HEALTHCHECK) {
    lastTotal = await page.locator("button[title='Upvote']").count();
    return { clicked, upvoteButtonsSeen: lastTotal };
  }

  for (let pass = 0; pass < 4 && clicked < MAX_UPVOTES; pass += 1) {
    const upvoteButtons = page.locator("button[title='Upvote']");
    const total = await upvoteButtons.count();
    lastTotal = Math.max(lastTotal, total);

    for (let index = 0; index < total && clicked < MAX_UPVOTES; index += 1) {
      const button = upvoteButtons.nth(index);
      const target = await describeUpvoteButton(button, index);
      const state = await button
        .evaluate((element) => {
          const rect = element.getBoundingClientRect();
          const hasActiveClass = (node) =>
            node.classList && Array.from(node.classList).includes("text-green-300");
          return {
            html: element.outerHTML,
            active:
              hasActiveClass(element) ||
              Array.from(element.querySelectorAll("*")).some((node) => hasActiveClass(node)),
            rect: { x: rect.x, y: rect.y, width: rect.width, height: rect.height },
          };
        })
        .catch(() => null);
      const box = state?.rect;
      if (!box || box.width < 5 || box.height < 5) {
        continue;
      }
      if (state.active) {
        skipped.push({
          type: "upvote",
          target: `visible_upvote_${index}`,
          ...target,
          reason: "already_upvoted",
        });
        continue;
      }
      if (target.post_key && recentActionKeys.has(target.post_key)) {
        skipped.push({
          type: "upvote",
          target: `visible_upvote_${index}`,
          ...target,
          reason: "recently_upvoted",
        });
        continue;
      }

      try {
        await button.scrollIntoViewIfNeeded({ timeout: 5000 });
        await sleep(800 + Math.floor(Math.random() * 1200));
        const freshBox = await button.boundingBox();
        if (!freshBox) {
          skipped.push({
            type: "upvote",
            target: `visible_upvote_${index}`,
            ...target,
            reason: "missing_bounding_box_after_scroll",
          });
          continue;
        }
        await page.mouse.move(freshBox.x + freshBox.width / 2, freshBox.y + freshBox.height / 2);
        await sleep(400 + Math.floor(Math.random() * 600));
        await page.mouse.click(freshBox.x + freshBox.width / 2, freshBox.y + freshBox.height / 2);
        await sleep(2500 + Math.floor(Math.random() * 1800));
        const afterState = await button
          .evaluate((element) => {
            const hasActiveClass = (node) =>
              node.classList && Array.from(node.classList).includes("text-green-300");
            return {
              active:
                hasActiveClass(element) ||
                Array.from(element.querySelectorAll("*")).some((node) => hasActiveClass(node)),
            };
          })
          .catch(() => ({ active: false }));
        const bodyText = await page.locator("body").innerText().catch(() => "");
        const verified =
          afterState.active ||
          /You\s*&\s*\d+\s+others?\s+upvoted|You\s+upvoted/i.test(bodyText);

        if (!verified) {
          skipped.push({
            type: "upvote",
            target: `visible_upvote_${index}`,
            ...target,
            reason: "click_not_verified",
          });
          continue;
        }

        actions.push({
          type: "upvote",
          target: `visible_upvote_${index}`,
          ...target,
          verified: true,
        });
        if (target.post_key) recentActionKeys.add(target.post_key);
        clicked += 1;
      } catch (error) {
        skipped.push({
          type: "upvote",
          target: `visible_upvote_${index}`,
          ...target,
          reason: error.message.split("\n")[0],
        });
      }
    }

    if (clicked < MAX_UPVOTES) {
      await page.mouse.wheel(0, 700);
      await sleep(1200 + Math.floor(Math.random() * 1200));
    }
  }

  if (clicked === 0 && MAX_UPVOTES > 0) {
    skipped.push({ type: "upvote", reason: `no_clickable_unvoted_upvote_found_count_${lastTotal}` });
  }

  return { clicked, upvoteButtonsSeen: lastTotal };
}

function actionEventsFromActions(actions, startedAt) {
  return actions
    .map((action, index) => {
      if (action.type === "upvote") {
        return {
          ts: action.ts || startedAt,
          type: "peerlist_post_upvoted",
          target_name: action.target_name || action.target || `Peerlist upvote ${index}`,
          target_url: action.target_url,
          target_excerpt: action.target_excerpt,
          post_key: action.post_key,
          selector: action.target,
          verified: Boolean(action.verified),
        };
      }
      return null;
    })
    .filter(Boolean);
}

function buildRunBundle(result) {
  const upvotesCount = Number(result.upvotes_count || 0);
  const commentsCount = Number(result.comments_count || 0);
  const followsCount = Number(result.follows_count || 0);
  const skippedCount = Array.isArray(result.skipped) ? result.skipped.length : 0;
  const blockersCount = Array.isArray(result.blockers) ? result.blockers.length : 0;
  return {
    schema_version: "phantomclaw.run-bundle.v1",
    generated_at: new Date().toISOString(),
    source: {
      project: "phantomclaw",
      channel: "railway-openclaw",
      artifact_path: REPORT_PATH,
      search_url: result.search_url || "https://peerlist.io/scroll",
    },
    automation: {
      name: "peerlist-scroll-engagement",
      label: "Peerlist Scroll Engagement",
      platform: "peerlist",
      surface: "scroll",
    },
    run: {
      run_id: result.run_id,
      started_at: result.started_at,
      finished_at: result.finished_at,
      status: result.status,
      stop_reason: result.stop_reason,
      profile_name: result.profile_name || result.actor_name || null,
      action_events: Array.isArray(result.events)
        ? result.events.filter((event) => event && event.type === "peerlist_post_upvoted")
        : [],
      screenshot_path: result.screenshot_path || null,
    },
    metrics: {
      items_scanned: Number(result.items_scanned || 0),
      items_considered: Number(result.items_considered || 0),
      actions_total: upvotesCount + commentsCount + followsCount,
      likes_count: upvotesCount,
      reposts_count: 0,
      comments_liked_count: 0,
      follows_count: followsCount,
      metrics_json: {
        upvotes_count: upvotesCount,
        comments_count: commentsCount,
        follows_count: followsCount,
        skipped_count: skippedCount,
        blockers_count: blockersCount,
        browser_profile: result.browser_profile,
        browser_provider: result.browser_provider,
        provider_failures: result.provider_failures,
        healthcheck: Boolean(result.healthcheck),
        failure_category: result.failure_category || null,
      },
    },
    report: result,
  };
}

async function syncRunBundle(bundle) {
  const token = process.env.PHANTOMCLAW_ACCESS_TOKEN;
  if (!token) {
    return { status: "skipped_missing_token" };
  }

  const baseUrl = (process.env.PHANTOMCLAW_API_BASE_URL || "https://phantomclaw.ai").replace(/\/+$/, "");
  const headers = {
    Authorization: `Bearer ${token}`,
    "Content-Type": "application/json",
    "X-PhantomClaw-Client": "openclaw-railway-peerlist",
  };
  if (process.env.PHANTOMCLAW_WORKSPACE) {
    headers["X-PhantomClaw-Workspace"] = process.env.PHANTOMCLAW_WORKSPACE;
  }

  const response = await fetch(`${baseUrl}/v1/run-bundles`, {
    method: "POST",
    headers,
    body: JSON.stringify(bundle),
  });
  const responseText = await response.text();
  if (!response.ok) {
    return {
      status: "failed",
      status_code: response.status,
      message: responseText.slice(0, 500),
    };
  }
  return {
    status: "stored",
    response: responseText ? JSON.parse(responseText) : null,
  };
}

async function run() {
  const startedAt = new Date().toISOString();
  const runId = `peerlist-scroll-${Date.now()}`;
  const actions = [];
  const skipped = [];
  const blockers = [];
  let scanStats = { clicked: 0, upvoteButtonsSeen: 0 };
  let browser;
  let page;
  let activeProvider = "unknown";
  const providerFailures = [];
  const screenshots = {};

  try {
    let lastNavigationError;
    for (const candidate of browserCandidates()) {
      activeProvider = candidate.provider;
      try {
        browser = await chromium.connectOverCDP(candidate.cdpUrl, {
          timeout: 60000,
        });
      } catch (error) {
        providerFailures.push({
          provider: candidate.provider,
          category: classifyFailure(error.message),
          reason: error.message.split("\n")[0],
        });
        lastNavigationError = error;
        browser = undefined;
        continue;
      }

      const context = browser.contexts()[0] || (await browser.newContext());
      if (candidate.cookies?.length) {
        await context.addCookies(candidate.cookies);
      }
      page = context.pages()[0] || (await context.newPage());
      page.setDefaultTimeout(15000);

      try {
        await page.goto("https://peerlist.io/scroll", {
          waitUntil: "domcontentloaded",
          timeout: 90000,
        });
        lastNavigationError = null;
        break;
      } catch (error) {
        lastNavigationError = error;
        providerFailures.push({
          provider: candidate.provider,
          category: classifyFailure(error.message),
          reason: error.message.split("\n")[0],
        });
        await browser.close().catch(() => {});
        browser = undefined;
        if (!/ERR_TUNNEL_CONNECTION_FAILED/i.test(error.message)) {
          throw error;
        }
      }
    }
    if (lastNavigationError) {
      throw lastNavigationError;
    }
    if (!browser || !page) {
      throw new Error("failed to create Browser Use page");
    }
    await sleep(7000);
    fs.mkdirSync(ARTIFACT_DIR, { recursive: true });
    const screenshotBase = path.join(ARTIFACT_DIR, runId);
    screenshots.before_path = `${screenshotBase}-before.png`;
    await page.screenshot({ path: screenshots.before_path, fullPage: false }).catch(() => {
      delete screenshots.before_path;
    });

    const beforeText = await page.locator("body").innerText();
    const profileHeaderVerified =
      /\bDaniel\b/i.test(beforeText) &&
      /followers/i.test(beforeText) &&
      /following/i.test(beforeText);
    const authenticatedComposerVisible =
      /What are you working on\?|Ask a question to the community\?|Write Article|Post/i.test(beforeText) &&
      !/Log in|Sign in|Sign up/i.test(beforeText);
    const actorVerified = profileHeaderVerified || authenticatedComposerVisible;
    const challenged = CHALLENGE_PATTERN.test(beforeText);

    if (!actorVerified) blockers.push(failureEntry("actor_not_verified"));
    if (challenged) blockers.push(failureEntry("challenge_detected", { category: "cloudflare_challenge" }));

    if (blockers.length === 0) {
      const recentActionKeys = readRecentActionKeys();
      scanStats = await upvoteVisiblePosts(page, actions, skipped, recentActionKeys);

      if (CLICK_STREAK) {
        const streak = page.getByRole("button", { name: /Streak button/i }).first();
        try {
          await streak.click({ timeout: 12000 });
          await sleep(2000);
          actions.push({ type: "streak_inspection", target: "streak_button" });
        } catch (error) {
          skipped.push({
            type: "streak_inspection",
            target: "streak_button",
            reason: error.message.split("\n")[0],
          });
        }
      } else {
        skipped.push({ type: "streak_inspection", reason: "disabled_by_default" });
      }

      if (!ENABLE_COMMENTS) {
        skipped.push({ type: "comment", reason: "comments_disabled_by_default" });
      }
    }

    const afterText = await page.locator("body").innerText().catch((error) => `ERR:${error.message}`);
    screenshots.after_path = `${screenshotBase}-after.png`;
    await page.screenshot({ path: screenshots.after_path, fullPage: false }).catch(() => {
      delete screenshots.after_path;
    });
    const finishedAt = new Date().toISOString();
    const finalStatus = blockers.length ? "blocked" : actions.length ? "ok" : "no_action";
    const stopReason = blockers[0]?.reason || null;
    const failureCategory = blockers[0]?.category || null;
    const upvotesCount = actions.filter((action) => action.type === "upvote" && action.verified).length;
    const result = {
      ts: new Date().toISOString(),
      run_id: runId,
      started_at: startedAt,
      finished_at: finishedAt,
      status: finalStatus,
      stop_reason: stopReason,
      failure_category: failureCategory,
      automation_name: "peerlist-scroll-engagement",
      healthcheck: HEALTHCHECK,
      platform: "peerlist",
      surface: "scroll",
      browser_profile: `${activeProvider}-direct-playwright`,
      browser_provider: activeProvider,
      url: page.url(),
      search_url: "https://peerlist.io/scroll",
      title: await page.title().catch(() => ""),
      profile_name: "Daniel",
      actor_name: "Daniel",
      actor_verified: actorVerified,
      has_challenge: CHALLENGE_PATTERN.test(afterText),
      page_shape_ok: scanStats.upvoteButtonsSeen > 0,
      items_scanned: scanStats.upvoteButtonsSeen,
      items_considered: scanStats.upvoteButtonsSeen,
      upvote_buttons_seen: scanStats.upvoteButtonsSeen,
      upvotes_count: upvotesCount,
      comments_count: 0,
      follows_count: 0,
      actions,
      skipped,
      blockers,
      provider_failures: providerFailures,
      events: [
        {
          ts: startedAt,
          type: "peerlist_scroll_loaded",
          url: page.url(),
          actor_verified: actorVerified,
        },
        ...actionEventsFromActions(actions, finishedAt),
      ],
      evidence: {
        upvote_confirmed:
          actions.some((action) => action.type === "upvote" && action.verified),
        existing_you_upvoted_text:
          /You\s*&\s*\d+\s+others?\s+upvoted|You\s+upvoted/i.test(afterText),
        body_preview: afterText.slice(0, 1200),
        screenshots,
      },
      screenshot_path: screenshots.after_path || screenshots.before_path || null,
      artifact_path: LOG_PATH,
      report_path: REPORT_PATH,
      bundle_path: BUNDLE_PATH,
      final_status: finalStatus,
    };

    const bundle = buildRunBundle(result);
    writeJson(BUNDLE_PATH, bundle);
    result.sync = await syncRunBundle(bundle);
    writeJson(REPORT_PATH, result);
    appendJsonl(result);
    console.log(JSON.stringify(result, null, 2));
  } finally {
    await browser?.close().catch(() => {});
  }
}

run().catch(async (error) => {
  const reason = error.message.split("\n")[0];
  const result = {
    ts: new Date().toISOString(),
    run_id: `peerlist-scroll-${Date.now()}`,
    started_at: new Date().toISOString(),
    finished_at: new Date().toISOString(),
    status: "error",
    stop_reason: reason,
    failure_category: classifyFailure(reason),
    automation_name: "peerlist-scroll-engagement",
    healthcheck: HEALTHCHECK,
    platform: "peerlist",
    surface: "scroll",
    browser_profile: "browser-use-direct-playwright",
    browser_provider: "unknown",
    profile_name: "Daniel",
    actor_name: "Daniel",
    actions: [],
    skipped: [],
    blockers: [failureEntry(reason)],
    provider_failures: [],
    events: [],
    artifact_path: LOG_PATH,
    report_path: REPORT_PATH,
    bundle_path: BUNDLE_PATH,
    final_status: "error",
  };
  const bundle = buildRunBundle(result);
  writeJson(BUNDLE_PATH, bundle);
  result.sync = await syncRunBundle(bundle).catch((syncError) => ({
    status: "failed",
    message: syncError.message,
  }));
  writeJson(REPORT_PATH, result);
  appendJsonl(result);
  console.error(JSON.stringify(result, null, 2));
  process.exit(1);
});
