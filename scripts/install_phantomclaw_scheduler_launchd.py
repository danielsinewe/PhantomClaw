from __future__ import annotations

import argparse
import os
import plistlib
import subprocess
import sys
from pathlib import Path


def default_plist_path() -> Path:
    return Path.home() / "Library" / "LaunchAgents" / "ai.phantomclaw.migrated-automations.plist"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Install the PhantomClaw migrated-automation launchd scheduler")
    parser.add_argument("--plist", type=Path, default=default_plist_path())
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parent.parent)
    parser.add_argument("--interval-seconds", type=int, default=300)
    parser.add_argument("--sync", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--load", action=argparse.BooleanOptionalAction, default=True)
    args = parser.parse_args(argv)

    logs_dir = Path.home() / ".config" / "phantomclaw" / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    program_arguments = [
        "/opt/homebrew/bin/node",
        str(args.repo / "scripts" / "phantomclaw-run-due-automations.mjs"),
    ]
    if args.sync:
        program_arguments.append("--sync")

    plist = {
        "Label": "ai.phantomclaw.migrated-automations",
        "ProgramArguments": program_arguments,
        "WorkingDirectory": str(args.repo),
        "StartInterval": args.interval_seconds,
        "RunAtLoad": True,
        "StandardOutPath": str(logs_dir / "migrated-automations.out.log"),
        "StandardErrorPath": str(logs_dir / "migrated-automations.err.log"),
        "EnvironmentVariables": {
            "HOME": str(Path.home()),
            "PATH": "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin",
            "PYTHONUNBUFFERED": "1",
        },
    }

    args.plist.parent.mkdir(parents=True, exist_ok=True)
    with args.plist.open("wb") as handle:
        plistlib.dump(plist, handle, sort_keys=True)

    result = {"ok": True, "plist": str(args.plist), "loaded": False}
    if args.load:
        domain = f"gui/{os.getuid()}"
        subprocess.run(["launchctl", "bootout", domain, str(args.plist)], check=False, capture_output=True)
        bootstrap = subprocess.run(["launchctl", "bootstrap", domain, str(args.plist)], check=False, text=True, capture_output=True)
        if bootstrap.returncode != 0:
            result["ok"] = False
            result["launchctl_error"] = bootstrap.stderr.strip() or bootstrap.stdout.strip()
        else:
            subprocess.run(["launchctl", "enable", f"{domain}/ai.phantomclaw.migrated-automations"], check=False)
            subprocess.run(["launchctl", "kickstart", "-k", f"{domain}/ai.phantomclaw.migrated-automations"], check=False)
            result["loaded"] = True

    import json

    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
