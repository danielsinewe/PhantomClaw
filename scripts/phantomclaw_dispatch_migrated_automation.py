from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parent.parent
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

from phantomclaw_bundle import validate_run_bundle
from phantomclaw_codex_migration import automation_from_registry, build_dispatch_bundle, load_registry


def default_outbox_path(automation_id: str, run_id: str) -> Path:
    return Path.home() / ".config" / "phantomclaw" / "automation-outbox" / automation_id / f"{run_id}.bundle.json"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Dispatch a migrated Codex automation through PhantomClaw bundle handling")
    parser.add_argument("--registry", type=Path, help="PhantomClaw automation registry path")
    parser.add_argument("--automation-id", required=True)
    parser.add_argument("--run-id")
    parser.add_argument("--output", type=Path, help="Bundle output path")
    parser.add_argument("--sync", action="store_true", help="Sync the generated bundle with phantomclaw-cli")
    parser.add_argument("--phantomclaw-cli", default=str(Path.home() / "Documents" / "GitHub" / "phantomclaw-cli" / "dist" / "cli.js"))
    args = parser.parse_args(argv)

    registry = load_registry(args.registry)
    automation = automation_from_registry(registry, args.automation_id)
    bundle = build_dispatch_bundle(automation, run_id=args.run_id)
    validate_run_bundle(bundle)

    output_path = args.output or default_outbox_path(args.automation_id, bundle["run"]["run_id"])
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(bundle, indent=2, sort_keys=True) + "\n")

    result: dict[str, object] = {"ok": True, "bundle": str(output_path), "automation_id": args.automation_id}
    if args.sync:
        completed = subprocess.run(
            ["node", args.phantomclaw_cli, "bundle", "sync", str(output_path)],
            check=False,
            text=True,
            capture_output=True,
        )
        result["sync_exit_code"] = completed.returncode
        result["sync_stdout"] = completed.stdout.strip()
        result["sync_stderr"] = completed.stderr.strip()
        if completed.returncode != 0:
            result["ok"] = False
            print(json.dumps(result, indent=2, sort_keys=True))
            return completed.returncode

    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
