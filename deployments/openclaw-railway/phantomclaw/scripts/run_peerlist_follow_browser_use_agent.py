#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parent.parent
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

from peerlist.follow_workflow.browser_use_agent import main


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
