from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

PACKAGE_ROOT = Path(__file__).resolve().parent.parent
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

from phantomclaw_codex_migration import build_dispatch_bundle, load_registry, validate_registry

DAY_CODES = ["MO", "TU", "WE", "TH", "FR", "SA", "SU"]


def default_state_path() -> Path:
    return Path.home() / ".config" / "phantomclaw" / "automations" / "state.json"


def default_outbox_dir() -> Path:
    return Path.home() / ".config" / "phantomclaw" / "automation-outbox"


def parse_rrule(rrule: str) -> dict[str, str]:
    parts: dict[str, str] = {}
    for part in (rrule or "").split(";"):
        if "=" not in part:
            continue
        key, value = part.split("=", 1)
        parts[key.upper()] = value
    return parts


def int_values(value: str | None, default: list[int]) -> list[int]:
    if not value:
        return default
    values: list[int] = []
    for item in value.split(","):
        try:
            values.append(int(item))
        except ValueError:
            continue
    return values or default


def day_allowed(parts: dict[str, str], now: datetime) -> bool:
    byday = parts.get("BYDAY")
    if not byday:
        return True
    allowed = {day.strip().upper() for day in byday.split(",") if day.strip()}
    return DAY_CODES[now.weekday()] in allowed


def due_occurrence_key(automation: dict, now: datetime) -> str | None:
    parts = parse_rrule(str(automation.get("rrule") or ""))
    freq = parts.get("FREQ", "").upper()
    if not day_allowed(parts, now):
        return None

    minutes = int_values(parts.get("BYMINUTE"), [0])
    if now.minute not in minutes:
        return None

    if freq == "HOURLY":
        interval = int_values(parts.get("INTERVAL"), [1])[0]
        if interval <= 0:
            interval = 1
        if now.hour % interval != 0:
            return None
        return f"{automation['id']}:{now.strftime('%Y-%m-%dT%H')}:{now.minute:02d}"

    if freq in {"WEEKLY", "DAILY"}:
        hours = int_values(parts.get("BYHOUR"), [0])
        if now.hour not in hours:
            return None
        if freq == "WEEKLY":
            return f"{automation['id']}:{DAY_CODES[now.weekday()]}:{now.strftime('%Y-%m-%d')}:{now.hour:02d}:{now.minute:02d}"
        return f"{automation['id']}:{now.strftime('%Y-%m-%d')}:{now.hour:02d}:{now.minute:02d}"

    return None


def load_state(path: Path) -> dict:
    if not path.exists():
        return {"schema_version": "phantomclaw.scheduler-state.v1", "last_occurrences": {}}
    text = path.read_text().strip()
    if not text:
        return {"schema_version": "phantomclaw.scheduler-state.v1", "last_occurrences": {}}
    return json.loads(text)


def write_state(path: Path, state: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n")


def write_bundle(bundle: dict, outbox_dir: Path) -> Path:
    automation_id = bundle["report"]["automation_id"]
    path = outbox_dir / automation_id / f"{bundle['run']['run_id']}.bundle.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(bundle, indent=2, sort_keys=True) + "\n")
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run due migrated automations through PhantomClaw dispatch bundles")
    parser.add_argument("--registry", type=Path)
    parser.add_argument("--state", type=Path, default=default_state_path())
    parser.add_argument("--outbox", type=Path, default=default_outbox_dir())
    parser.add_argument("--now", help="ISO timestamp override for tests")
    parser.add_argument("--sync", action="store_true")
    parser.add_argument("--phantomclaw-cli", default=str(Path.home() / "Documents" / "GitHub" / "phantomclaw-cli" / "dist" / "cli.js"))
    args = parser.parse_args(argv)

    registry = load_registry(args.registry)
    validate_registry(registry)
    tz = ZoneInfo("Europe/Berlin")
    now = datetime.fromisoformat(args.now).astimezone(tz) if args.now else datetime.now(tz)
    state = load_state(args.state)
    last_occurrences = state.setdefault("last_occurrences", {})

    dispatched: list[dict[str, object]] = []
    skipped: list[dict[str, object]] = []
    for automation in registry["automations"]:
        if automation.get("status") != "ACTIVE":
            skipped.append({"id": automation["id"], "reason": "paused"})
            continue
        occurrence_key = due_occurrence_key(automation, now)
        if not occurrence_key:
            skipped.append({"id": automation["id"], "reason": "not_due"})
            continue
        if last_occurrences.get(automation["id"]) == occurrence_key:
            skipped.append({"id": automation["id"], "reason": "already_dispatched", "occurrence": occurrence_key})
            continue

        run_id = f"{automation['id']}-{now.strftime('%Y%m%dT%H%M%S%z')}"
        bundle = build_dispatch_bundle(automation, run_id=run_id)
        bundle_path = write_bundle(bundle, args.outbox)
        last_occurrences[automation["id"]] = occurrence_key
        entry: dict[str, object] = {"id": automation["id"], "bundle": str(bundle_path), "occurrence": occurrence_key}
        if args.sync:
            completed = subprocess.run(
                ["node", args.phantomclaw_cli, "bundle", "sync", str(bundle_path)],
                check=False,
                capture_output=True,
                text=True,
            )
            entry["sync_exit_code"] = completed.returncode
            if completed.returncode != 0:
                entry["sync_stderr"] = completed.stderr.strip()
        dispatched.append(entry)

    state["updated_at"] = now.isoformat()
    write_state(args.state, state)
    print(json.dumps({"ok": True, "now": now.isoformat(), "dispatched": dispatched, "skipped_count": len(skipped)}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
