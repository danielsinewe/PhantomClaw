from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parent.parent
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

from phantomclaw_codex_migration import build_registry, load_codex_automations, validate_registry, write_registry


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Migrate Codex automation definitions into PhantomClaw's local registry")
    parser.add_argument("--codex-root", type=Path, help="Path containing Codex automation directories")
    parser.add_argument("--output", type=Path, help="Registry output path")
    parser.add_argument("--dry-run", action="store_true", help="Validate and print a summary without writing")
    args = parser.parse_args(argv)

    automations = load_codex_automations(args.codex_root)
    registry = build_registry(automations)
    validate_registry(registry)

    if args.dry_run:
        print(
            json.dumps(
                {
                    "ok": True,
                    "count": len(registry["automations"]),
                    "active": sum(1 for item in registry["automations"] if item["status"] == "ACTIVE"),
                    "native": sum(1 for item in registry["automations"] if item["runner"]["status"] == "native"),
                    "native_candidate": sum(1 for item in registry["automations"] if item["runner"]["status"] == "native_candidate"),
                    "needs_native_runner": sum(1 for item in registry["automations"] if item["runner"]["status"] == "needs_native_runner"),
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 0

    output_path = write_registry(registry, args.output)
    print(json.dumps({"ok": True, "path": str(output_path), "count": len(registry["automations"])}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
