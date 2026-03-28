from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parent.parent
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

from phantomclaw_bundle import build_run_bundle_from_path, run_bundle_schema, validate_run_bundle


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Export a PhantomClaw run bundle for hosted sync")
    parser.add_argument("--automation-name")
    parser.add_argument("--report-path", type=Path)
    parser.add_argument("--platform")
    parser.add_argument("--search-url")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--print-schema", action="store_true")
    args = parser.parse_args(argv)

    if args.print_schema:
        print(json.dumps(run_bundle_schema(), indent=2, sort_keys=True))
        return 0

    if not args.automation_name:
        parser.error("--automation-name is required unless --print-schema is used")
    if args.report_path is None:
        parser.error("--report-path is required unless --print-schema is used")

    bundle = build_run_bundle_from_path(
        automation_name=args.automation_name,
        report_path=args.report_path,
        platform=args.platform,
        search_url=args.search_url,
    )
    validate_run_bundle(bundle)
    payload = json.dumps(bundle, indent=2, sort_keys=True)
    if args.output:
        args.output.write_text(payload + "\n")
    else:
        print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
