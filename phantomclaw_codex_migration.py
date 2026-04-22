from __future__ import annotations

import hashlib
import json
import os
import re
import tomllib
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

PHANTOMCLAW_REGISTRY_VERSION = "phantomclaw.automation-registry.v1"
PHANTOMCLAW_RUN_BUNDLE_VERSION = "phantomclaw.run-bundle.v1"

NATIVE_RUNNERS: dict[str, dict[str, Any]] = {
    "trustoutreach-linkedin": {
        "status": "native",
        "command": [
            "python3",
            "-m",
            "linkedin.company_profile_engagement.runner",
        ],
        "notes": "Native PhantomClaw LinkedIn company profile engagement runner exists.",
    },
    "linkedin-sales-community": {
        "status": "native",
        "command": [
            "python3",
            "-m",
            "linkedin.sales_community_engagement.runner",
        ],
        "notes": "Native PhantomClaw LinkedIn Sales Community runner exists.",
    },
    "peerlist-1footer-random-push": {
        "status": "native_candidate",
        "command": [
            "python3",
            "peerlist/follow_workflow/browser_use_agent.py",
        ],
        "notes": "Peerlist PhantomClaw workflow exists, but the old Codex prompt must be mapped to concrete follow/unfollow parameters before enabling live actions.",
    },
}


@dataclass(frozen=True)
class MigratedAutomation:
    id: str
    name: str
    status: str
    source_status: str
    kind: str
    rrule: str
    cwds: list[str]
    execution_environment: str | None
    model: str | None
    reasoning_effort: str | None
    prompt: str
    memory: str | None
    platform: str
    surface: str
    runner: dict[str, Any]
    source: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "status": self.status,
            "source_status": self.source_status,
            "kind": self.kind,
            "rrule": self.rrule,
            "timezone": "Europe/Berlin",
            "cwds": self.cwds,
            "execution_environment": self.execution_environment,
            "model": self.model,
            "reasoning_effort": self.reasoning_effort,
            "prompt": self.prompt,
            "memory": self.memory,
            "platform": self.platform,
            "surface": self.surface,
            "runner": self.runner,
            "source": self.source,
            "processing_system": "phantomclaw",
            "codex_processing_enabled": False,
        }


def default_codex_automation_root() -> Path:
    return Path(os.environ.get("CODEX_HOME", Path.home() / ".codex")) / "automations"


def default_phantomclaw_registry_path() -> Path:
    return Path(os.environ.get("PHANTOMCLAW_CONFIG_DIR", Path.home() / ".config" / "phantomclaw")) / "automations" / "registry.json"


def normalize_rrule(value: str | None) -> str:
    if not value:
        return ""
    cleaned = value.strip()
    if "RRULE:" in cleaned:
        cleaned = cleaned.split("RRULE:", 1)[1].strip()
    return cleaned


def slug_text(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "automation"


def prompt_hash(prompt: str) -> str:
    return hashlib.sha256(prompt.encode("utf-8")).hexdigest()


def infer_platform_and_surface(automation_id: str, name: str, cwds: list[str]) -> tuple[str, str]:
    haystack = " ".join([automation_id, name, *cwds]).lower()
    if "linkedin" in haystack:
        if "sales-community" in haystack or "sales community" in haystack:
            return "linkedin", "sales-community"
        if "salesnav" in haystack or "sales-nav" in haystack or "sales navigator" in haystack:
            return "linkedin", "sales-navigator"
        return "linkedin", "core"
    if "peerlist" in haystack:
        return "peerlist", "network"
    if "twitter" in haystack or "x-" in automation_id or " x " in f" {haystack} ":
        return "x", "timeline"
    if "gsc" in haystack or "seo" in haystack or "ahrefs" in haystack:
        return "seo", "audit"
    if "hubspot" in haystack:
        return "hubspot", "crm"
    if "posthog" in haystack:
        return "posthog", "analytics"
    if "leetcode" in haystack:
        return "leetcode", "practice"
    if "product-hunt" in haystack or "product hunt" in haystack:
        return "producthunt", "forums"
    if "malt" in haystack:
        return "malt", "profile"
    if "docs" in haystack:
        return "docs", "sync"
    if "openclaw" in haystack or "clawhub" in haystack:
        return "phantomclaw", "openclaw"
    return "phantomclaw", "generic"


def runner_for(automation_id: str, prompt: str) -> dict[str, Any]:
    native = NATIVE_RUNNERS.get(automation_id)
    if native:
        return {
            **native,
            "dispatch": "phantomclaw_native",
            "codex_fallback_allowed": False,
        }
    return {
        "status": "needs_native_runner",
        "dispatch": "phantomclaw_bundle_only",
        "command": None,
        "codex_fallback_allowed": False,
        "notes": "Migrated from a Codex prompt. PhantomClaw will preserve schedule, prompt, memory, and emit run bundles, but live task execution needs a native PhantomClaw runner before this job can mutate external systems.",
        "prompt_sha256": prompt_hash(prompt),
    }


def load_codex_automation(path: Path) -> MigratedAutomation:
    data = tomllib.loads(path.read_text())
    automation_id = path.parent.name
    name = str(data.get("name") or automation_id)
    source_status = str(data.get("status") or "PAUSED")
    cwds = [str(item) for item in data.get("cwds", [])]
    prompt = str(data.get("prompt") or "")
    memory_path = path.parent / "memory.md"
    memory = memory_path.read_text() if memory_path.exists() else None
    platform, surface = infer_platform_and_surface(automation_id, name, cwds)
    return MigratedAutomation(
        id=automation_id,
        name=name,
        status=source_status,
        source_status=source_status,
        kind=str(data.get("kind") or "cron"),
        rrule=normalize_rrule(data.get("rrule")),
        cwds=cwds,
        execution_environment=data.get("executionEnvironment"),
        model=data.get("model"),
        reasoning_effort=data.get("reasoningEffort"),
        prompt=prompt,
        memory=memory,
        platform=platform,
        surface=surface,
        runner=runner_for(automation_id, prompt),
        source={
            "system": "codex",
            "path": str(path),
            "memory_path": str(memory_path) if memory_path.exists() else None,
        },
    )


def load_codex_automations(root: Path | None = None) -> list[MigratedAutomation]:
    automation_root = root or default_codex_automation_root()
    return [
        load_codex_automation(path)
        for path in sorted(automation_root.glob("*/automation.toml"))
        if path.is_file()
    ]


def build_registry(automations: list[MigratedAutomation]) -> dict[str, Any]:
    generated_at = datetime.now(UTC).isoformat()
    return {
        "schema_version": PHANTOMCLAW_REGISTRY_VERSION,
        "generated_at": generated_at,
        "source": {
            "system": "codex",
            "imported_count": len(automations),
        },
        "policy": {
            "processing_system": "phantomclaw",
            "codex_processing_enabled": False,
            "preserve_source_status": True,
        },
        "automations": [automation.as_dict() for automation in automations],
    }


def validate_registry(registry: dict[str, Any]) -> None:
    if registry.get("schema_version") != PHANTOMCLAW_REGISTRY_VERSION:
        raise ValueError("unsupported registry schema_version")
    automations = registry.get("automations")
    if not isinstance(automations, list):
        raise ValueError("registry.automations must be a list")
    seen: set[str] = set()
    for automation in automations:
        if not isinstance(automation, dict):
            raise ValueError("automation entry must be an object")
        automation_id = automation.get("id")
        if not isinstance(automation_id, str) or not automation_id:
            raise ValueError("automation.id must be a non-empty string")
        if automation_id in seen:
            raise ValueError(f"duplicate automation id: {automation_id}")
        seen.add(automation_id)
        if automation.get("processing_system") != "phantomclaw":
            raise ValueError(f"{automation_id}: processing_system must be phantomclaw")
        if automation.get("codex_processing_enabled") is not False:
            raise ValueError(f"{automation_id}: codex processing must be disabled")
        runner = automation.get("runner")
        if not isinstance(runner, dict):
            raise ValueError(f"{automation_id}: runner must be an object")
        if runner.get("codex_fallback_allowed") is not False:
            raise ValueError(f"{automation_id}: codex fallback must be disabled")


def write_registry(registry: dict[str, Any], output_path: Path | None = None) -> Path:
    path = output_path or default_phantomclaw_registry_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    validate_registry(registry)
    path.write_text(json.dumps(registry, indent=2, sort_keys=True) + "\n")
    return path


def load_registry(path: Path | None = None) -> dict[str, Any]:
    registry_path = path or default_phantomclaw_registry_path()
    registry = json.loads(registry_path.read_text())
    validate_registry(registry)
    return registry


def automation_from_registry(registry: dict[str, Any], automation_id: str) -> dict[str, Any]:
    for automation in registry["automations"]:
        if automation["id"] == automation_id:
            return automation
    raise KeyError(f"automation not found: {automation_id}")


def build_dispatch_bundle(automation: dict[str, Any], *, run_id: str | None = None, status: str = "blocked", stop_reason: str = "native_runner_missing") -> dict[str, Any]:
    now = datetime.now(UTC).isoformat()
    resolved_run_id = run_id or f"{automation['id']}-{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}"
    runner = automation.get("runner") if isinstance(automation.get("runner"), dict) else {}
    has_native_runner = runner.get("status") in {"native", "native_candidate"}
    if has_native_runner and status == "blocked" and stop_reason == "native_runner_missing":
        status = "queued"
        stop_reason = "ready_for_native_runner"

    report = {
        "run_id": resolved_run_id,
        "started_at": now,
        "finished_at": now,
        "status": status,
        "stop_reason": stop_reason,
        "automation_id": automation["id"],
        "automation_name": automation["name"],
        "source_system": "codex",
        "processing_system": "phantomclaw",
        "codex_processing_enabled": False,
        "runner_status": runner.get("status"),
        "runner_dispatch": runner.get("dispatch"),
        "rrule": automation.get("rrule"),
        "cwds": automation.get("cwds", []),
    }
    return {
        "schema_version": PHANTOMCLAW_RUN_BUNDLE_VERSION,
        "generated_at": now,
        "source": {
            "project": "phantomclaw",
            "channel": "codex-migration",
            "artifact_path": automation.get("source", {}).get("path"),
            "search_url": None,
        },
        "automation": {
            "name": slug_text(automation["id"]),
            "label": automation["name"],
            "kind": "workflow",
            "platform": automation["platform"],
            "surface": automation["surface"],
            "north_star_metric": None,
            "parameters": {
                "source_status": automation.get("source_status"),
                "runner_status": runner.get("status"),
                "rrule": automation.get("rrule"),
            },
        },
        "run": {
            "run_id": resolved_run_id,
            "started_at": now,
            "finished_at": now,
            "status": status,
            "stop_reason": stop_reason,
            "profile_name": None,
            "action_events": [],
            "screenshot_path": None,
        },
        "metrics": {
            "items_scanned": 0,
            "items_considered": 0,
            "actions_total": 0,
            "likes_count": 0,
            "reposts_count": 0,
            "comments_liked_count": 0,
            "follows_count": 0,
            "metrics_json": {
                "migration_dispatch": True,
                "native_runner_available": has_native_runner,
                "codex_processing_enabled": False,
            },
        },
        "report": report,
    }
