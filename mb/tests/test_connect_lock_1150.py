"""One mb process at a time saves a credential (#1150).

Temporary stores, no network, no real keychain.
"""

# ruff: noqa: F811
from __future__ import annotations

import errno
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from mb import connect as connect_mod
from mb.cli import app
from mb.credential_store import _read_local_secrets
from tests.test_google_connect import (  # noqa: F401 (fixtures are used by name)
    google_env,
    loopback_only_network,
    repo,
)

OLD = "sk_live_" + "O" * 28
FIRST = "sk_live_" + "F" * 28
LATER = "sk_live_" + "L" * 28


def _items() -> list[str]:
    return list(dict(_read_local_secrets()).values())


def _fail_record_then(monkeypatch: pytest.MonkeyPatch, during: Any) -> None:
    """Make the first writer's record write fail, running ``during`` first."""

    real = connect_mod._write_user_scope_provider

    def write(*args: Any, **kwargs: Any) -> Path:
        monkeypatch.setattr(connect_mod, "_write_user_scope_provider", real)
        during()
        raise OSError(errno.EIO, "synthetic")

    monkeypatch.setattr(connect_mod, "_write_user_scope_provider", write)


def test_a_writer_between_the_rollback_comparison_and_delete_keeps_its_credential(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    connect_mod.connect_provider("stripe", repo=repo, scope="user")
    real_compare = connect_mod.hmac.compare_digest
    real_write = connect_mod._write_user_scope_provider
    seen: dict[str, Any] = {}

    def interleave(a: Any, b: Any) -> bool:
        matched = real_compare(a, b)
        monkeypatch.setattr(connect_mod.hmac, "compare_digest", real_compare)
        monkeypatch.setattr(connect_mod, "_write_user_scope_provider", real_write)
        seen["second"] = connect_mod.connect_provider(
            "stripe", repo=repo, token=LATER, scope="user"
        )
        return matched

    def fail(*args: Any, **kwargs: Any) -> Path:
        raise OSError(errno.EIO, "synthetic")

    monkeypatch.setattr(connect_mod, "_write_user_scope_provider", fail)
    monkeypatch.setattr(connect_mod.hmac, "compare_digest", interleave)
    with pytest.raises(connect_mod.MetadataWriteError) as caught:
        connect_mod.connect_provider("stripe", repo=repo, token=FIRST, scope="user")
    assert seen["second"]["ok"]
    assert LATER in _items()
    assert "The new credential was removed" not in str(caught.value)


def test_a_third_writer_survives_the_restore_of_a_present_snapshot(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    connect_mod.connect_provider("stripe", repo=repo, token=OLD, scope="user")
    _fail_record_then(
        monkeypatch,
        lambda: connect_mod.connect_provider("stripe", repo=repo, token=LATER, scope="user"),
    )
    with pytest.raises(connect_mod.MetadataWriteError) as caught:
        connect_mod.connect_provider("stripe", repo=repo, token=FIRST, scope="user")
    assert _items() == [LATER]
    assert "previous credential was restored" not in str(caught.value)


_HOLDER = """
import errno, os, sys, time
from pathlib import Path
from mb import connect as c
real = c._write_user_scope_provider
ready, release = Path(sys.argv[1]), Path(sys.argv[2])
def write(*a, **k):
    ready.write_text("held")
    deadline = time.time() + 60
    while not release.exists() and time.time() < deadline:
        time.sleep(0.05)
    return real(*a, **k)
c._write_user_scope_provider = write
c.connect_provider("stripe", repo=sys.argv[3], token=sys.argv[4], scope="user")
"""


def test_a_second_process_is_refused_while_the_first_holds_the_credential(
    repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from mb import credential_lock

    monkeypatch.setattr(credential_lock, "LOCK_WAIT_SECONDS", 0.3)
    ready, release = tmp_path / "ready", tmp_path / "release"
    holder = subprocess.Popen(
        [sys.executable, "-c", _HOLDER, str(ready), str(release), str(repo), FIRST],
        env={**os.environ, "PYTHONPATH": os.pathsep.join(sys.path)},
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        deadline = time.time() + 30
        while not ready.exists() and time.time() < deadline:
            time.sleep(0.05)
        assert ready.exists(), "the first process never reached its record write"
        for as_json in (False, True):
            result = CliRunner().invoke(
                app,
                ["connect", "stripe", "--token-stdin", "--scope", "user", "--repo", str(repo)]
                + (["--json"] if as_json else []),
                input=LATER + "\n",
            )
            assert result.exit_code == 1
            assert "Another mb connect is saving the Stripe credential" in result.output
            assert "Nothing was stored" in result.output
            assert "Traceback" not in result.output
            assert LATER not in result.output
            if as_json:
                assert (
                    json.loads(result.output[result.output.index("{") :])["state"]
                    == "credential_busy"
                )
        assert LATER not in _items()
    finally:
        release.write_text("go")
        try:
            holder.wait(timeout=30)
        except subprocess.TimeoutExpired:
            holder.kill()
    assert holder.returncode == 0
    assert _items() == [FIRST]


def test_an_unwritable_lock_folder_refuses_and_stores_nothing(repo: Path, tmp_path: Path) -> None:
    if os.geteuid() == 0:
        pytest.skip("root ignores directory permissions")
    home = Path(os.environ["MAINBRANCH_HOME"])
    home.mkdir(parents=True, exist_ok=True)
    home.chmod(0o500)
    try:
        for as_json in (False, True):
            result = CliRunner().invoke(
                app,
                ["connect", "stripe", "--token-stdin", "--repo", str(repo)]
                + (["--json"] if as_json else []),
                input=LATER + "\n",
            )
            assert result.exit_code == 1
            assert "Nothing was stored" in result.output
            assert "Traceback" not in result.output
            assert str(tmp_path) not in result.output
            if as_json:
                assert (
                    json.loads(result.output[result.output.index("{") :])["state"]
                    == "credential_lock_unavailable"
                )
    finally:
        home.chmod(0o700)
    assert LATER not in _items()
