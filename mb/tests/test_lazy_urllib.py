"""``mb`` must not load ``urllib.request`` (and on macOS ``_scproxy``) at start (#1156)."""

from __future__ import annotations

import subprocess
import sys

_PROBE = """
import sys
import mb.cli
from mb.cli import app

try:
    app(["--version"], standalone_mode=False)
except SystemExit:
    pass

loaded = sorted(m for m in ("urllib.request", "_scproxy") if m in sys.modules)
print("LOADED:" + ",".join(loaded))
"""


def test_mb_start_does_not_load_urllib_request() -> None:
    result = subprocess.run(
        [sys.executable, "-c", _PROBE],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    loaded = result.stdout.rsplit("LOADED:", 1)[1].strip().split(",")
    assert "urllib.request" not in loaded
    if sys.platform == "darwin":
        assert "_scproxy" not in loaded
