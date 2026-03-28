from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parent.parent
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

from phantomclaw_bundle import build_run_bundle_from_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Export a PhantomClaw run bundle for hosted sync")
    parser.add_argument("--automation-name", required=True)
    parser.add_argument("--report-path", type=Path, required=True)
    parser.add_argument("--platform")
    parser.add_argument("--search-url")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)

    bundle = build_run_bundle_from_path(
        automation_name=args.automation_name,
        report_path=args.report_path,
        platform=args.platform,
        search_url=args.search_url,
    )
    payload = json.dumps(bundle, indent=2, sort_keys=True)
    if args.output:
        args.output.write_text(payload + "\n")
    else:
        print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

