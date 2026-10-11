"""One mb process at a time saves a credential (#1150).

Temporary stores, no network, no real keychain.
"""

# ruff: noqa: F811
from __future__ import annotations

import errno
import hmac
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
    client_file,
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
    real_compare = hmac.compare_digest
    real_write = connect_mod._write_user_scope_provider
    seen: dict[str, Any] = {}

    def interleave(a: Any, b: Any) -> bool:
        matched = bool(real_compare(a, b))
        monkeypatch.setattr(hmac, "compare_digest", real_compare)
        monkeypatch.setattr(connect_mod, "_write_user_scope_provider", real_write)
        seen["second"] = connect_mod.connect_provider(
            "stripe", repo=repo, token=LATER, scope="user"
        )
        return matched

    def fail(*args: Any, **kwargs: Any) -> Path:
        raise OSError(errno.EIO, "synthetic")

    monkeypatch.setattr(connect_mod, "_write_user_scope_provider", fail)
    monkeypatch.setattr(hmac, "compare_digest", interleave)
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
    try:  # absent on the base commit, where this test must fail on the race itself
        from mb import credential_lock

        monkeypatch.setattr(credential_lock, "LOCK_WAIT_SECONDS", 0.3)
    except ImportError:
        pass
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


def test_a_google_sign_in_is_refused_while_another_process_holds_its_credential(
    repo: Path, client_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import fcntl
    import hashlib

    from mb import credential_lock
    from mb import google_connect as gc
    from mb import google_oauth as go

    monkeypatch.setattr(credential_lock, "LOCK_WAIT_SECONDS", 0.3)
    monkeypatch.setattr(
        gc,
        "_sign_in",
        lambda *a, **k: {
            "refresh_token": "r",
            "access_token": "a",
            "scope": " ".join(go.SCOPES),
        },
    )
    config = connect_mod._read_config(repo)
    ref = connect_mod._secret_ref(
        connect_mod._ensure_repo_id(config, repo), "google", gc.GRANT_SLOT
    )
    lock_dir = connect_mod._home() / credential_lock.LOCK_DIR_NAME
    lock_dir.mkdir(parents=True)
    name = hashlib.sha256(ref.encode()).hexdigest()[:32] + ".lock"
    fd = os.open(lock_dir / name, os.O_CREAT | os.O_RDWR, 0o600)
    fcntl.flock(fd, fcntl.LOCK_EX)
    try:
        with pytest.raises(gc.GoogleConnectError) as caught:
            gc.bootstrap(repo, client_json=client_file.read_text(), scope="repo")
    finally:
        os.close(fd)
    assert caught.value.state == "credential_busy"
    assert "Nothing was stored" in str(caught.value)
    assert _items() == []


class _FakeFcntl:
    """A stand-in for the ``fcntl`` the lock module sees; the store keeps the real one."""

    LOCK_EX = 2
    LOCK_NB = 4
    LOCK_UN = 8

    def __init__(self, code: int) -> None:
        self.code = code
        self.calls: list[int] = []

    def flock(self, fd: int, op: int) -> None:
        if op & self.LOCK_UN:
            return
        self.calls.append(fd)
        raise OSError(self.code, os.strerror(self.code))


def _fake_flock(monkeypatch: pytest.MonkeyPatch, code: int) -> _FakeFcntl:
    from mb import credential_lock

    fake = _FakeFcntl(code)
    monkeypatch.setattr(credential_lock, "fcntl", fake)
    monkeypatch.setattr(credential_lock, "LOCK_WAIT_SECONDS", 0.3)
    return fake


def _fd_is_closed(fd: int) -> bool:
    try:
        os.fstat(fd)
    except OSError:
        return True
    return False


@pytest.mark.parametrize(
    "code",
    [errno.ENOLCK, errno.EINVAL, errno.EBADF, errno.EOPNOTSUPP, errno.EACCES],
)
def test_a_lock_error_that_is_not_a_held_lock_refuses_at_once(
    repo: Path, monkeypatch: pytest.MonkeyPatch, code: int
) -> None:
    # EACCES is an fcntl-lock error; flock(2) on macOS and Linux does not document it.
    fake = _fake_flock(monkeypatch, code)
    for as_json in (False, True):
        result = CliRunner().invoke(
            app,
            ["connect", "stripe", "--token-stdin", "--scope", "user", "--repo", str(repo)]
            + (["--json"] if as_json else []),
            input=LATER + "\n",
        )
        assert result.exit_code == 1
        assert "Nothing was stored" in result.output
        assert "Another mb connect" not in result.output
        assert "file locking" in result.output
        assert "Traceback" not in result.output
        assert LATER not in result.output
        if as_json:
            payload = json.loads(result.output[result.output.index("{") :])
            assert payload["state"] == "credential_lock_unavailable"
    assert len(fake.calls) == 2  # one attempt per command, no retry loop
    assert all(_fd_is_closed(fd) for fd in fake.calls)
    assert LATER not in _items()


@pytest.mark.parametrize("code", [errno.EWOULDBLOCK, errno.EAGAIN])
def test_a_held_lock_still_waits_then_reports_busy(
    repo: Path, monkeypatch: pytest.MonkeyPatch, code: int
) -> None:
    fake = _fake_flock(monkeypatch, code)
    result = CliRunner().invoke(
        app,
        ["connect", "stripe", "--token-stdin", "--scope", "user", "--repo", str(repo), "--json"],
        input=LATER + "\n",
    )
    assert result.exit_code == 1
    payload = json.loads(result.output[result.output.index("{") :])
    assert payload["state"] == "credential_busy"
    assert "Another mb connect is saving the Stripe credential" in result.output
    assert len(fake.calls) > 1
    assert _fd_is_closed(fake.calls[-1])
    assert LATER not in _items()


def test_a_google_sign_in_reports_a_lock_error_that_is_not_busy(
    repo: Path, client_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from mb import google_connect as gc
    from mb import google_oauth as go

    fake = _fake_flock(monkeypatch, errno.ENOLCK)
    monkeypatch.setattr(
        gc,
        "_sign_in",
        lambda *a, **k: {
            "refresh_token": "r",
            "access_token": "a",
            "scope": " ".join(go.SCOPES),
        },
    )
    with pytest.raises(gc.GoogleConnectError) as caught:
        gc.bootstrap(repo, client_json=client_file.read_text(), scope="repo")
    assert caught.value.state == "credential_lock_unavailable"
    assert "Another mb connect" not in str(caught.value)
    assert "Nothing was stored" in str(caught.value)
    assert len(fake.calls) == 1
    assert _fd_is_closed(fake.calls[0])
    assert _items() == []
