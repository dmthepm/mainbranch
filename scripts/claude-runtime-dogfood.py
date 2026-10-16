#!/usr/bin/env python3
"""Run the Main Branch Claude Code runtime dogfood harness."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

try:
    importlib.import_module("yaml")
except ImportError:
    print(
        "dogfood harness needs PyYAML: install pyyaml in the harness venv first",
        file=sys.stderr,
    )
    raise SystemExit(2) from None

ROOT = Path(__file__).resolve().parents[1]
PACKAGE_ROOT = ROOT / "mb"
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

main = importlib.import_module("mb.dogfood_harness").main


if __name__ == "__main__":
    raise SystemExit(main())
