#!/usr/bin/env node

import { spawnSync } from "node:child_process";
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import os from "node:os";
import path from "node:path";

const DAY_CODES = ["SU", "MO", "TU", "WE", "TH", "FR", "SA"];

function argValue(name, fallback = null) {
  const index = process.argv.indexOf(name);
  if (index === -1 || index + 1 >= process.argv.length) return fallback;
  return process.argv[index + 1];
}

function hasArg(name) {
  return process.argv.includes(name);
}

function defaultRegistryPath() {
  return path.join(os.homedir(), ".config", "phantomclaw", "automations", "registry.json");
}

function defaultStatePath() {
  return path.join(os.homedir(), ".config", "phantomclaw", "automations", "state.json");
}

function defaultOutboxDir() {
  return path.join(os.homedir(), ".config", "phantomclaw", "automation-outbox");
}

function parseRrule(rrule) {
  const parts = {};
  for (const part of String(rrule || "").split(";")) {
    const [key, ...rest] = part.split("=");
    if (!key || rest.length === 0) continue;
    parts[key.toUpperCase()] = rest.join("=");
  }
  return parts;
}

function intValues(value, fallback) {
  if (!value) return fallback;
  const values = String(value)
    .split(",")
    .map((item) => Number.parseInt(item, 10))
    .filter((item) => Number.isFinite(item));
  return values.length > 0 ? values : fallback;
}

function pad(value) {
  return String(value).padStart(2, "0");
}

function localParts(now) {
  const formatter = new Intl.DateTimeFormat("en-CA", {
    timeZone: "Europe/Berlin",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
    weekday: "short",
  });
  const parts = Object.fromEntries(formatter.formatToParts(now).map((part) => [part.type, part.value]));
  const weekdayMap = { Sun: "SU", Mon: "MO", Tue: "TU", Wed: "WE", Thu: "TH", Fri: "FR", Sat: "SA" };
  return {
    year: Number(parts.year),
    month: Number(parts.month),
    day: Number(parts.day),
    hour: Number(parts.hour),
    minute: Number(parts.minute),
    second: Number(parts.second),
    dayCode: weekdayMap[parts.weekday] ?? DAY_CODES[now.getDay()],
    date: `${parts.year}-${parts.month}-${parts.day}`,
  };
}

function dueOccurrenceKey(automation, now) {
  const parts = parseRrule(automation.rrule);
  const freq = String(parts.FREQ || "").toUpperCase();
  const local = localParts(now);
  if (parts.BYDAY) {
    const allowed = new Set(String(parts.BYDAY).split(",").map((item) => item.trim().toUpperCase()));
    if (!allowed.has(local.dayCode)) return null;
  }
  const minutes = intValues(parts.BYMINUTE, [0]);
  if (!minutes.includes(local.minute)) return null;

  if (freq === "HOURLY") {
    const interval = Math.max(1, intValues(parts.INTERVAL, [1])[0]);
    if (local.hour % interval !== 0) return null;
    return `${automation.id}:${local.date}T${pad(local.hour)}:${pad(local.minute)}`;
  }

  if (freq === "WEEKLY" || freq === "DAILY") {
    const hours = intValues(parts.BYHOUR, [0]);
    if (!hours.includes(local.hour)) return null;
    if (freq === "WEEKLY") {
      return `${automation.id}:${local.dayCode}:${local.date}:${pad(local.hour)}:${pad(local.minute)}`;
    }
    return `${automation.id}:${local.date}:${pad(local.hour)}:${pad(local.minute)}`;
  }

  return null;
}

function loadJson(filePath, fallback) {
  if (!existsSync(filePath)) return fallback;
  const text = readFileSync(filePath, "utf8").trim();
  return text ? JSON.parse(text) : fallback;
}

function slugText(value) {
  return String(value).toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "") || "automation";
}

function isoWithOffset(date) {
  return date.toISOString();
}

function runIdTimestamp(now) {
  const local = localParts(now);
  return `${local.year}${pad(local.month)}${pad(local.day)}T${pad(local.hour)}${pad(local.minute)}${pad(local.second)}+0200`;
}

function buildBundle(automation, runId, now) {
  const runner = automation.runner && typeof automation.runner === "object" ? automation.runner : {};
  const nativeRunnerAvailable = runner.status === "native" || runner.status === "native_candidate";
  const status = nativeRunnerAvailable ? "queued" : "blocked";
  const stopReason = nativeRunnerAvailable ? "ready_for_native_runner" : "native_runner_missing";
  const nowIso = isoWithOffset(now);
  const report = {
    run_id: runId,
    started_at: nowIso,
    finished_at: nowIso,
    status,
    stop_reason: stopReason,
    automation_id: automation.id,
    automation_name: automation.name,
    source_system: "codex",
    processing_system: "phantomclaw",
    codex_processing_enabled: false,
    runner_status: runner.status ?? null,
    runner_dispatch: runner.dispatch ?? null,
    rrule: automation.rrule ?? null,
    cwds: automation.cwds ?? [],
  };
  return {
    schema_version: "phantomclaw.run-bundle.v1",
    generated_at: nowIso,
    source: {
      project: "phantomclaw",
      channel: "codex-migration",
      artifact_path: automation.source?.path ?? null,
      search_url: null,
    },
    automation: {
      name: slugText(automation.id),
      label: automation.name,
      kind: "workflow",
      platform: automation.platform,
      surface: automation.surface,
      north_star_metric: null,
      parameters: {
        source_status: automation.source_status,
        runner_status: runner.status ?? null,
        rrule: automation.rrule ?? null,
      },
    },
    run: {
      run_id: runId,
      started_at: nowIso,
      finished_at: nowIso,
      status,
      stop_reason: stopReason,
      profile_name: null,
      action_events: [],
      screenshot_path: null,
    },
    metrics: {
      items_scanned: 0,
      items_considered: 0,
      actions_total: 0,
      likes_count: 0,
      reposts_count: 0,
      comments_liked_count: 0,
      follows_count: 0,
      metrics_json: {
        migration_dispatch: true,
        native_runner_available: nativeRunnerAvailable,
        codex_processing_enabled: false,
      },
    },
    report,
  };
}

const registryPath = argValue("--registry", defaultRegistryPath());
const statePath = argValue("--state", defaultStatePath());
const outboxDir = argValue("--outbox", defaultOutboxDir());
const cliPath = argValue("--phantomclaw-cli", path.join(os.homedir(), "Documents", "GitHub", "phantomclaw-cli", "dist", "cli.js"));
const sync = hasArg("--sync");
const now = argValue("--now") ? new Date(argValue("--now")) : new Date();
const registry = loadJson(registryPath, null);
if (!registry || registry.schema_version !== "phantomclaw.automation-registry.v1") {
  throw new Error(`Invalid PhantomClaw registry: ${registryPath}`);
}
const state = loadJson(statePath, { schema_version: "phantomclaw.scheduler-state.v1", last_occurrences: {} });
state.last_occurrences ||= {};

const dispatched = [];
let skippedCount = 0;
for (const automation of registry.automations || []) {
  if (automation.status !== "ACTIVE") {
    skippedCount += 1;
    continue;
  }
  const occurrence = dueOccurrenceKey(automation, now);
  if (!occurrence) {
    skippedCount += 1;
    continue;
  }
  if (state.last_occurrences[automation.id] === occurrence) {
    skippedCount += 1;
    continue;
  }
  const runId = `${automation.id}-${runIdTimestamp(now)}`;
  const bundle = buildBundle(automation, runId, now);
  const bundlePath = path.join(outboxDir, automation.id, `${runId}.bundle.json`);
  mkdirSync(path.dirname(bundlePath), { recursive: true });
  writeFileSync(bundlePath, `${JSON.stringify(bundle, null, 2)}\n`);
  state.last_occurrences[automation.id] = occurrence;
  const entry = { id: automation.id, bundle: bundlePath, occurrence };
  if (sync) {
    const result = spawnSync("node", [cliPath, "bundle", "sync", bundlePath], { encoding: "utf8" });
    entry.sync_exit_code = result.status;
    if (result.status !== 0) entry.sync_stderr = result.stderr.trim();
  }
  dispatched.push(entry);
}

state.updated_at = now.toISOString();
mkdirSync(path.dirname(statePath), { recursive: true });
writeFileSync(statePath, `${JSON.stringify(state, null, 2)}\n`);
console.log(JSON.stringify({ ok: true, now: now.toISOString(), dispatched, skipped_count: skippedCount }, null, 2));
