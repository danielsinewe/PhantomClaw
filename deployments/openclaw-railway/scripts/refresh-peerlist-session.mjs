import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { spawnSync } from "node:child_process";

const LOCAL_CHROME_PROFILE = process.env.PEERLIST_LOCAL_CHROME_PROFILE || "danielsinewe.com";
const SESSION_NAME = process.env.PEERLIST_BROWSER_USE_SESSION || "peerlist-cookie-export";
const COOKIE_FILE =
  process.env.PEERLIST_COOKIE_FILE || path.join(os.tmpdir(), "peerlist-cookies.json");
const RUN_HEALTHCHECK = process.argv.includes("--healthcheck");
const SKIP_PROFILE_SYNC = process.argv.includes("--skip-profile-sync");

function run(command, args, options = {}) {
  const result = spawnSync(command, args, {
    encoding: "utf8",
    maxBuffer: 20 * 1024 * 1024,
    ...options,
  });
  if (result.status !== 0) {
    throw new Error(`${command} ${args.join(" ")} failed: ${result.stderr || result.stdout}`);
  }
  return result.stdout;
}

function railwayVariables() {
  return JSON.parse(run("railway", ["variables", "-s", "OpenClaw", "--json"], {
    cwd: "/Users/danielsinewe/Documents/GitHub/Automations",
    stdio: ["ignore", "pipe", "pipe"],
  }));
}

function setRailwayVariable(name, value) {
  run("railway", ["variables", "-s", "OpenClaw", "--set", `${name}=${value}`], {
    cwd: "/Users/danielsinewe/Documents/GitHub/Automations",
    stdio: ["ignore", "pipe", "pipe"],
  });
}

function requiredAuthCookieNames(cookies) {
  const names = new Set(cookies.map((cookie) => cookie.name));
  return [
    "__Secure-next-auth.session-token",
    "token",
    "ctoken",
    "idtoken",
    "pltoken",
  ].filter((name) => names.has(name));
}

const vars = railwayVariables();
const browserUseApiKey = vars.BROWSER_USE_API_KEY;
if (!browserUseApiKey) {
  throw new Error("BROWSER_USE_API_KEY is missing from Railway OpenClaw variables");
}

let browserUseProfileId = vars.BROWSER_USE_PROFILE_ID;
if (!SKIP_PROFILE_SYNC) {
  const syncOutput = run(
    "browser-use",
    ["profile", "sync", "--browser", "Google Chrome", "--profile", LOCAL_CHROME_PROFILE],
    {
      cwd: "/Users/danielsinewe/Documents/GitHub/Automations",
      env: { ...process.env, BROWSER_USE_API_KEY: browserUseApiKey },
      stdio: ["ignore", "pipe", "pipe"],
    },
  );
  const profileMatch = syncOutput.match(/Profile created:\s*([0-9a-f-]+)/i);
  if (!profileMatch) {
    throw new Error("Browser Use profile sync did not print a profile id");
  }
  browserUseProfileId = profileMatch[1];
  const proxyCountryCode = vars.BROWSER_USE_PROXY_COUNTRY_CODE || "de";
  const cdpUrl = `wss://connect.browser-use.com?apiKey=${encodeURIComponent(
    browserUseApiKey,
  )}&profileId=${encodeURIComponent(browserUseProfileId)}&proxyCountryCode=${encodeURIComponent(proxyCountryCode)}&timeout=240`;
  setRailwayVariable("BROWSER_USE_PROFILE_ID", browserUseProfileId);
  setRailwayVariable("BROWSER_USE_CDP_URL", cdpUrl);
}

spawnSync("browser-use", ["--session", SESSION_NAME, "close"], {
  cwd: "/Users/danielsinewe/Documents/GitHub/Automations",
  encoding: "utf8",
  stdio: ["ignore", "pipe", "pipe"],
});
run("browser-use", ["--session", SESSION_NAME, "--profile", LOCAL_CHROME_PROFILE, "open", "https://peerlist.io/scroll"], {
  cwd: "/Users/danielsinewe/Documents/GitHub/Automations",
});
run("browser-use", ["--session", SESSION_NAME, "cookies", "export", COOKIE_FILE, "--url", "https://peerlist.io"], {
  cwd: "/Users/danielsinewe/Documents/GitHub/Automations",
});
spawnSync("browser-use", ["--session", SESSION_NAME, "close"], {
  cwd: "/Users/danielsinewe/Documents/GitHub/Automations",
  encoding: "utf8",
  stdio: ["ignore", "pipe", "pipe"],
});

const cookies = JSON.parse(fs.readFileSync(COOKIE_FILE, "utf8"));
const authCookieNames = requiredAuthCookieNames(cookies);
if (authCookieNames.length < 3) {
  throw new Error(`Peerlist cookie export looks unauthenticated; found auth cookies: ${authCookieNames.join(", ")}`);
}
setRailwayVariable("PEERLIST_COOKIES_JSON", JSON.stringify(cookies));

let healthcheck = null;
if (RUN_HEALTHCHECK) {
  const remote = [
    "NODE_PATH=/opt/openclaw/node_modules/.pnpm/playwright@1.58.2/node_modules:/opt/openclaw/node_modules/.pnpm/playwright-core@1.58.2/node_modules",
    "PEERLIST_HEALTHCHECK=1",
    "PEERLIST_MAX_UPVOTES=0",
    "node /data/workspace/scripts/peerlist-browser-use-direct.mjs >/tmp/peerlist-healthcheck.out 2>/tmp/peerlist-healthcheck.err",
    "node -e 'const fs=require(\"fs\"); const r=JSON.parse(fs.readFileSync(\"/data/workspace/artifacts/peerlist-scroll-engagement/latest-report.json\",\"utf8\")); console.log(JSON.stringify({run_id:r.run_id,status:r.status,provider:r.browser_provider,actor_verified:r.actor_verified,page_shape_ok:r.page_shape_ok,items_scanned:r.items_scanned,provider_failures:r.provider_failures,healthcheck:r.healthcheck}, null, 2));'",
  ].join(" && ");
  healthcheck = JSON.parse(run("railway", ["ssh", "-s", "OpenClaw", "--", remote], {
    cwd: "/Users/danielsinewe/Documents/GitHub/Automations",
  }));
}

console.log(JSON.stringify({
  browser_use_profile_id: browserUseProfileId,
  cookie_count: cookies.length,
  auth_cookie_names: authCookieNames,
  railway_updated: [
    ...(SKIP_PROFILE_SYNC ? [] : ["BROWSER_USE_PROFILE_ID", "BROWSER_USE_CDP_URL"]),
    "PEERLIST_COOKIES_JSON",
  ],
  healthcheck,
}, null, 2));
