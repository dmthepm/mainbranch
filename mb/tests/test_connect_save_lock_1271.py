"""Two `mb connect` saves at once cannot lose each other's secret or record (#1271).

Real processes, no sleeps. The first process stops just before it writes, a
barrier file waits until the second has either finished or is blocked on the lock,
then the first writes. With the save lock that order is harmless. Without it
(``locked=False`` removes the new locks in the worker) the first write replaces
what the second saved, so each test also proves its race is real.

Temporary stores, fake values, no network, no real keychain.
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import pytest
import yaml

from mb import connect as connect_mod
from mb import credential_lock

STRIPE = "sk_live_" + "S" * 28
RESEND = "re_" + "R" * 30
GITHUB = "ghp_" + "G" * 36
STRIPE2 = "sk_live_" + "T" * 28

# argv: role provider token repo home signals pause_at scope locked [action]
_WORKER = r"""
import contextlib, os, sys, time, types
from pathlib import Path
role, provider, token, repo, home, signals, pause_at, scope, locked = sys.argv[1:10]
action = sys.argv[10] if len(sys.argv) > 10 else "connect"
os.environ["MAINBRANCH_HOME"] = home
os.environ["MB_CONNECT_SECRET_BACKEND"] = "local-file"
signals = Path(signals)
from mb import connect as c, credential_lock as cl, credential_store as cs, google_connect as gc

def signal(name):
    (signals / name).write_text("1")

def wait_for(*names):
    deadline = time.time() + 60
    while time.time() < deadline:
        if any((signals / n).exists() for n in names):
            return
        time.sleep(0.02)
    raise SystemExit("barrier timed out")

if locked != "1":
    none = contextlib.contextmanager(lambda *a, **k: (yield))
    for mod in (cl, c, gc):
        mod.save_transaction = none
    cs.local_store_lock = none
    cl.local_store_lock = none

if role == "first":
    targets = {
        "config": (c, "_write_config"),
        "user_scope": (c, "_write_user_scope"),
        "secrets": (cs, "_write_local_secrets"),
    }
    module, name = targets[pause_at]
    real = getattr(module, name)
    def paused(*a, **k):
        signal("first_at_write")
        wait_for("second_waiting", "second_done", "release")
        if (signals / "die").exists():
            os._exit(9)
        return real(*a, **k)
    setattr(module, name, paused)
else:
    wait_for("first_at_write")
    real_read = c._read_config
    def read(*a, **k):
        out = real_read(*a, **k)
        signal("second_read")
        return out
    c._read_config = read
    real_sleep = time.sleep
    def sleeping(seconds):
        signal("second_waiting")
        real_sleep(seconds)
    cl.time = types.SimpleNamespace(monotonic=time.monotonic, sleep=sleeping)

if action == "hydrate":
    c.hydrate(repo)
elif action == "metadata":
    c.connect_provider(provider, repo=repo, metadata_pairs=["note=kept"], scope=scope)
else:
    c.connect_provider(provider, repo=repo, token=token, scope=scope)
if role == "second":
    signal("second_done")
"""


class Pair:
    """A first and second worker with a barrier directory."""

    def __init__(self, tmp_path: Path) -> None:
        self.signals = tmp_path / "signals"
        self.signals.mkdir()
        self.procs: list[subprocess.Popen[bytes]] = []

    def start(self, role: str, provider: str, token: str, repo: Path, home: Path, **kw: Any) -> Any:
        proc = subprocess.Popen(
            [
                sys.executable,
                "-c",
                _WORKER,
                role,
                provider,
                token,
                str(repo),
                str(home),
                str(self.signals),
                kw.get("pause_at", "config"),
                kw.get("scope", "repo"),
                "1" if kw.get("locked", True) else "0",
                kw.get("action", "connect"),
            ],
            env={
                **os.environ,
                "PYTHONPATH": os.pathsep.join(sys.path),
                **({"TMPDIR": kw["tmpdir"]} if "tmpdir" in kw else {}),
            },
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
        self.procs.append(proc)
        return proc

    def wait_for(self, name: str) -> None:
        deadline = time.time() + 60
        while not (self.signals / name).exists() and time.time() < deadline:
            time.sleep(0.02)
        assert (self.signals / name).exists(), name

    def finish(self) -> list[int]:
        codes = []
        for proc in self.procs:
            try:
                proc.wait(timeout=60)
            except subprocess.TimeoutExpired:
                proc.kill()
            codes.append(proc.returncode)
        return codes


@pytest.fixture(autouse=True)
def isolated_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / "home"
    monkeypatch.setenv("MAINBRANCH_HOME", str(home))
    monkeypatch.setenv("MB_CONNECT_SECRET_BACKEND", "local-file")
    return home


def _repos(tmp_path: Path, count: int = 1) -> list[Path]:
    paths = []
    for index in range(count):
        path = tmp_path / f"biz{index}"
        path.mkdir()
        paths.append(path)
    return paths


def _race(pair: Pair, first: dict[str, Any], second: dict[str, Any]) -> list[int]:
    pair.start("first", **first)
    pair.wait_for("first_at_write")
    pair.start("second", **second)
    return pair.finish()


def _config(repo: Path) -> dict[str, Any]:
    data: dict[str, Any] = yaml.safe_load((repo / ".mb" / "connect.yaml").read_text())
    return data


def _secrets(home: Path) -> list[str]:
    return sorted(json.loads((home / "secrets" / "connect.json").read_text()).values())


def _user_scope(home: Path) -> dict[str, Any]:
    data: dict[str, Any] = yaml.safe_load(connect_mod._user_scope_path().read_text())
    return data


def _providers(repo: Path) -> set[str]:
    return set(_config(repo)["providers"])


def _user_scope_providers(data: dict[str, Any]) -> set[str]:
    return {
        provider
        for repo_entry in data["repos"].values()
        for provider in repo_entry.get("providers", {})
    }


@pytest.mark.parametrize("locked", [True, False])
def test_distinct_providers_in_one_repo_keep_both_records(
    tmp_path: Path, isolated_home: Path, locked: bool
) -> None:
    (repo,) = _repos(tmp_path)
    codes = _race(
        Pair(tmp_path),
        dict(provider="stripe", token=STRIPE, repo=repo, home=isolated_home, locked=locked),
        dict(provider="resend", token=RESEND, repo=repo, home=isolated_home, locked=locked),
    )
    assert codes == [0, 0]
    both = _providers(repo) == {"stripe", "resend"}
    assert both is locked
    if locked:
        assert _secrets(isolated_home) == sorted([STRIPE, RESEND])


@pytest.mark.parametrize("locked", [True, False])
def test_distinct_refs_do_not_lose_a_secret_in_the_shared_secret_file(
    tmp_path: Path, isolated_home: Path, locked: bool
) -> None:
    repo_a, repo_b = _repos(tmp_path, 2)
    codes = _race(
        Pair(tmp_path),
        dict(
            provider="stripe",
            token=STRIPE,
            repo=repo_a,
            home=isolated_home,
            pause_at="secrets",
            locked=locked,
        ),
        dict(
            provider="stripe",
            token=STRIPE2,
            repo=repo_b,
            home=isolated_home,
            pause_at="secrets",
            locked=locked,
        ),
    )
    assert codes == [0, 0]
    assert (len(_secrets(isolated_home)) == 2) is locked


@pytest.mark.parametrize("locked", [True, False])
def test_separate_repos_sharing_user_scope_keep_both_records(
    tmp_path: Path, isolated_home: Path, locked: bool
) -> None:
    repo_a, repo_b = _repos(tmp_path, 2)
    codes = _race(
        Pair(tmp_path),
        dict(
            provider="stripe",
            token=STRIPE,
            repo=repo_a,
            home=isolated_home,
            pause_at="user_scope",
            scope="user",
            locked=locked,
        ),
        dict(
            provider="resend",
            token=RESEND,
            repo=repo_b,
            home=isolated_home,
            pause_at="user_scope",
            scope="user",
            locked=locked,
        ),
    )
    assert codes == [0, 0]
    assert (_user_scope_providers(_user_scope(isolated_home)) == {"stripe", "resend"}) is locked
    if locked:
        assert _secrets(isolated_home) == sorted([STRIPE, RESEND])


@pytest.mark.parametrize("locked", [True, False])
def test_a_metadata_only_edit_and_a_connect_keep_both_records(
    tmp_path: Path, isolated_home: Path, locked: bool
) -> None:
    (repo,) = _repos(tmp_path)
    codes = _race(
        Pair(tmp_path),
        dict(provider="stripe", token=STRIPE, repo=repo, home=isolated_home, locked=locked),
        dict(
            provider="github",
            token="",
            repo=repo,
            home=isolated_home,
            action="metadata",
            locked=locked,
        ),
    )
    assert codes == [0, 0]
    assert (_providers(repo) == {"stripe", "github"}) is locked


@pytest.mark.parametrize("locked", [True, False])
def test_hydrate_and_a_connect_keep_both_records(
    tmp_path: Path, isolated_home: Path, locked: bool
) -> None:
    (repo,) = _repos(tmp_path)
    connect_mod.connect_provider("resend", repo=repo, token=RESEND, scope="user")
    # Hydration copies the user-scope record; a repo copy will be absent on a new clone.
    (repo / ".mb" / "connect.yaml").unlink()
    codes = _race(
        Pair(tmp_path),
        dict(provider="stripe", token=STRIPE, repo=repo, home=isolated_home, locked=locked),
        dict(
            provider="",
            token="",
            repo=repo,
            home=isolated_home,
            action="hydrate",
            locked=locked,
        ),
    )
    assert codes == [0, 0]
    assert (_providers(repo) == {"stripe", "resend"}) is locked


@pytest.mark.parametrize("locked", [True, False])
def test_two_homes_sharing_one_repo_keep_both_records(tmp_path: Path, locked: bool) -> None:
    (repo,) = _repos(tmp_path)
    home_a, home_b = tmp_path / "home_a", tmp_path / "home_b"
    codes = _race(
        Pair(tmp_path),
        dict(provider="stripe", token=STRIPE, repo=repo, home=home_a, locked=locked),
        dict(provider="resend", token=RESEND, repo=repo, home=home_b, locked=locked),
    )
    assert codes == [0, 0]
    assert (_providers(repo) == {"stripe", "resend"}) is locked


def test_a_held_save_lock_gives_the_busy_error_and_stores_nothing(
    tmp_path: Path, isolated_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (repo,) = _repos(tmp_path)
    monkeypatch.setattr(credential_lock, "LOCK_WAIT_SECONDS", 0.3)
    holder_code = (
        "import sys, time\nfrom pathlib import Path\n"
        "from mb import credential_lock as cl\n"
        "with cl.save_transaction(Path(sys.argv[1]), None):\n"
        "    Path(sys.argv[2]).write_text('1')\n"
        "    while not Path(sys.argv[3]).exists():\n"
        "        time.sleep(0.02)\n"
    )
    ready, release = tmp_path / "ready", tmp_path / "release"
    holder = subprocess.Popen(
        [sys.executable, "-c", holder_code, str(isolated_home), str(ready), str(release)],
        env={**os.environ, "PYTHONPATH": os.pathsep.join(sys.path)},
    )
    try:
        deadline = time.time() + 30
        while not ready.exists() and time.time() < deadline:
            time.sleep(0.02)
        assert ready.exists()
        with pytest.raises(credential_lock.CredentialBusyError) as caught:
            connect_mod.connect_provider("stripe", repo=repo, token=STRIPE)
        assert caught.value.state == "credential_busy"
        assert "Nothing was stored" in str(caught.value)
        assert STRIPE not in str(caught.value)
    finally:
        release.write_text("go")
        holder.wait(timeout=30)
    assert not (repo / ".mb" / "connect.yaml").exists()
    assert not (isolated_home / "secrets" / "connect.json").exists()


def test_a_crash_during_a_save_leaves_the_config_readable_and_the_lock_free(
    tmp_path: Path, isolated_home: Path
) -> None:
    (repo,) = _repos(tmp_path)
    connect_mod.connect_provider("resend", repo=repo, token=RESEND)
    before = (repo / ".mb" / "connect.yaml").read_text()
    pair = Pair(tmp_path)
    first = pair.start("first", "stripe", STRIPE, repo, isolated_home)
    pair.wait_for("first_at_write")
    first.send_signal(signal.SIGKILL)
    first.wait(timeout=30)
    assert (repo / ".mb" / "connect.yaml").read_text() == before
    assert set(connect_mod._read_config(repo)["providers"]) == {"resend"}
    # The dead process's locks are gone: a later save is not blocked.
    result = connect_mod.connect_provider("github", repo=repo, token=GITHUB)
    assert result["ok"]
    assert _providers(repo) == {"resend", "github"}
    # The killed save had stored its key before the record (no rollback runs on SIGKILL).
    # The file still reads, and the later saves' keys are in it.
    assert {RESEND, GITHUB} <= set(_secrets(isolated_home))


def test_unknown_config_keys_survive_a_validation_recording(
    tmp_path: Path, isolated_home: Path
) -> None:
    (repo,) = _repos(tmp_path)
    connect_mod.connect_provider("stripe", repo=repo, token=STRIPE)
    path = repo / ".mb" / "connect.yaml"
    data = yaml.safe_load(path.read_text())
    data["owner_note"] = {"keep": "me"}
    data["providers"]["stripe"]["custom_field"] = "kept"
    path.write_text(yaml.safe_dump(data, sort_keys=False))
    config = connect_mod._read_config(repo)
    entry = dict(config["providers"]["stripe"])
    entry["validation"] = {"state": "ready"}
    entry["last_checked_at"] = "2026-01-01T00:00:00+00:00"
    assert connect_mod._record_validation(repo, config, "stripe", entry) == {}
    after = yaml.safe_load(path.read_text())
    assert after["owner_note"] == {"keep": "me"}
    assert after["providers"]["stripe"]["custom_field"] == "kept"
    assert after["providers"]["stripe"]["validation"] == {"state": "ready"}


@pytest.mark.parametrize("locked", [True, False])
def test_processes_with_different_tmpdirs_still_serialize_on_one_repo(
    tmp_path: Path, locked: bool
) -> None:
    (repo,) = _repos(tmp_path)
    home_a, home_b = tmp_path / "home_a", tmp_path / "home_b"
    tmp_a, tmp_b = tmp_path / "tmp_a", tmp_path / "tmp_b"
    tmp_a.mkdir()
    tmp_b.mkdir()
    codes = _race(
        Pair(tmp_path),
        dict(
            provider="stripe",
            token=STRIPE,
            repo=repo,
            home=home_a,
            tmpdir=str(tmp_a),
            locked=locked,
        ),
        dict(
            provider="resend",
            token=RESEND,
            repo=repo,
            home=home_b,
            tmpdir=str(tmp_b),
            locked=locked,
        ),
    )
    assert codes == [0, 0]
    assert (_providers(repo) == {"stripe", "resend"}) is locked


def test_a_save_leaves_only_the_config_in_the_repo_state_folder(
    tmp_path: Path, isolated_home: Path
) -> None:
    (repo,) = _repos(tmp_path)
    connect_mod.connect_provider("stripe", repo=repo, token=STRIPE)
    connect_mod.connect_provider("resend", repo=repo, token=RESEND, scope="user")
    connect_mod.hydrate(repo)
    assert sorted(path.name for path in (repo / ".mb").iterdir()) == ["connect.yaml"]
    assert sorted(path.name for path in repo.iterdir()) == [".mb"]


def test_a_symlinked_repo_path_meets_the_same_lock(tmp_path: Path, isolated_home: Path) -> None:
    (repo,) = _repos(tmp_path)
    link = tmp_path / "link"
    link.symlink_to(repo, target_is_directory=True)
    (repo / ".mb").mkdir()
    with credential_lock.save_transaction(isolated_home, repo / ".mb"):
        pass
    holder = subprocess.Popen(
        [
            sys.executable,
            "-c",
            "import sys, time\nfrom pathlib import Path\nfrom mb import credential_lock as cl\n"
            "with cl.save_transaction(Path(sys.argv[1]), Path(sys.argv[2])):\n"
            "    Path(sys.argv[3]).write_text('1')\n"
            "    while not Path(sys.argv[4]).exists():\n        time.sleep(0.02)\n",
            str(tmp_path / "other_home"),
            str(repo / ".mb"),
            str(tmp_path / "ready"),
            str(tmp_path / "release"),
        ],
        env={**os.environ, "PYTHONPATH": os.pathsep.join(sys.path)},
    )
    try:
        deadline = time.time() + 30
        while not (tmp_path / "ready").exists() and time.time() < deadline:
            time.sleep(0.02)
        assert (tmp_path / "ready").exists()
        credential_lock.LOCK_WAIT_SECONDS = 0.3
        with (
            pytest.raises(credential_lock.CredentialBusyError),
            credential_lock.save_transaction(tmp_path / "third_home", link / ".mb"),
        ):
            pass
    finally:
        credential_lock.LOCK_WAIT_SECONDS = 5.0
        (tmp_path / "release").write_text("go")
        holder.wait(timeout=30)
