"""Follow-ups to the user-scope write handling: restore naming, notes, folder wording (#1129).

Temporary stores, stub token endpoint, no network.
"""

# ruff: noqa: F811
from __future__ import annotations

import errno
import json
import shutil
import sys
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest
import yaml

from mb import connect as connect_mod
from mb import google_connect as gc
from mb.cli import app
from mb.credential_store import SecretStore
from tests.test_connect_followups_1076 import _user_scope_cloudflare
from tests.test_connect_followups_1116 import DETAIL, _fail_user_write, _run
from tests.test_google_connect import (  # noqa: F401 (fixtures are used by name)
    MINTED,
    _config,
    _local_secrets,
    _oauth,
    _signin_args,
    client_file,
    google,
    google_env,
    loopback_only_network,
    repo,
    runner,
)
from tests.test_google_mint import _mint_with, _signed_in, _token


@pytest.fixture(autouse=True)
def offline(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(shutil, "which", lambda name: f"/usr/bin/{name}")


def _expire_and_fail_write(
    repo: Path, client_file: Path, google: Any, monkeypatch: pytest.MonkeyPatch
) -> Path:
    """A signed-in repo whose recorded state would change, with the user file unwritable."""

    _signed_in(repo, client_file, google, "--scope", "user")
    _mint_with(monkeypatch, status=400, payload={"error": "invalid_grant"})
    gc.forget_minted()
    path = connect_mod._user_scope_path()
    _fail_user_write(path, "write", errno.ENOSPC, monkeypatch)
    return path


# --- 1. home-relative recovery commands ---------------------------------------------------


def test_recovery_commands_show_a_repo_under_home_with_a_tilde(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    writes = gc._Writes(fresh=False, replaced_access_token=False, repo=tmp_path / "biz")

    command = gc._recovery_command(writes, "mb connect hydrate")
    message = gc._partial_message(
        gc._Writes(fresh=True, replaced_access_token=False, repo=tmp_path / "my biz"),
        "metadata",
    )

    assert command == "mb connect hydrate --repo ~/biz"
    assert "--repo ~/'my biz'" in message
    assert str(tmp_path) not in message


# --- 3. which slot stayed changed ---------------------------------------------------------


@pytest.mark.parametrize(
    ("failing", "named"),
    [
        (("oauth_grant",), "(the Google grant stayed changed)"),
        (("access_token",), "(the access token stayed changed)"),
        (("oauth_grant", "access_token"), "(the Google grant and the access token stayed changed)"),
    ],
)
def test_a_failed_google_restore_names_the_slot_that_stayed_changed(
    repo: Path,
    client_file: Path,
    google: Any,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    failing: tuple[str, ...],
    named: str,
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    _signed_in(repo, client_file, google, "--scope", "user")
    slots = _config(repo)["providers"]["google"]["secrets"]
    failing_refs = {slots[name]["ref"] for name in failing}
    real_set = SecretStore.set
    sign_in_writes = 0

    def set_(self: SecretStore, ref: str, *args: Any, **kwargs: Any) -> None:
        nonlocal sign_in_writes
        sign_in_writes += 1
        # The two sign-in writes land; the restores of the chosen slots fail.
        if sign_in_writes > 2 and ref in failing_refs:
            raise OSError(DETAIL)
        real_set(self, ref, *args, **kwargs)

    monkeypatch.setattr(SecretStore, "set", set_)
    _fail_user_write(connect_mod._user_scope_path(), "write", errno.ENOSPC, monkeypatch)

    result = _oauth(repo, "--reauth", "--client-file", str(client_file), "--json")

    assert result.exit_code == 1, result.output
    summary = json.loads(result.stdout)["summary"]
    assert "previous credential state could not be restored " + named in summary
    assert DETAIL not in result.output
    assert str(tmp_path) not in summary


@pytest.mark.parametrize("as_json", [False, True])
def test_a_failed_provider_secret_restore_names_it(
    repo: Path, monkeypatch: pytest.MonkeyPatch, as_json: bool
) -> None:
    _user_scope_cloudflare(repo)
    real_set = SecretStore.set
    writes = 0

    def set_(self: SecretStore, *args: Any, **kwargs: Any) -> None:
        nonlocal writes
        writes += 1
        if writes > 1:  # the connect's own write lands, the restore fails
            raise OSError(DETAIL)
        real_set(self, *args, **kwargs)

    monkeypatch.setattr(SecretStore, "set", set_)
    _fail_user_write(connect_mod._user_scope_path(), "write", errno.ENOSPC, monkeypatch)

    result = _run(repo, "reconnect", as_json)

    assert result.exit_code == 1, result.output
    text = json.loads(result.stdout)["summary"] if as_json else result.output
    assert "could not be restored (the Cloudflare credential stayed changed)" in text
    assert DETAIL not in result.output


def test_the_replay_command_leaves_out_a_secret_shaped_recorded_key(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Built at run time so no secret-shaped literal sits in the source.
    sentinel_key = "ghp_" + "E" * 36
    sentinel_value = "ghp_" + "F" * 36
    _user_scope_cloudflare(repo)
    path = connect_mod._user_scope_path()

    def plant(node: Any) -> int:
        planted = 0
        if isinstance(node, dict):
            meta = node.get("metadata")
            if isinstance(meta, dict) and meta.get("zone_id") == "abc123":
                meta[sentinel_key] = "legacy"
                meta["note"] = sentinel_value
                planted += 1
            for child in node.values():
                planted += plant(child)
        return planted

    planted = 0
    # Plant in whichever file holds the recorded metadata (repo or user scope).
    for config in (repo / ".mb" / "connect.yaml", path):
        if config.exists():
            data = yaml.safe_load(config.read_text(encoding="utf-8"))
            planted += plant(data)
            config.write_text(yaml.safe_dump(data), encoding="utf-8")
    assert planted >= 1
    real_set = SecretStore.set
    writes = 0

    def set_(self: SecretStore, *args: Any, **kwargs: Any) -> None:
        nonlocal writes
        writes += 1
        if writes > 1:  # the connect's own write lands, the restore fails
            raise OSError(DETAIL)
        real_set(self, *args, **kwargs)

    monkeypatch.setattr(SecretStore, "set", set_)
    _fail_user_write(path, "write", errno.ENOSPC, monkeypatch)

    result = _run(repo, "reconnect", True)

    assert result.exit_code == 1, result.output
    summary = json.loads(result.stdout)["summary"]
    assert "stayed changed" in summary
    assert "--metadata zone_id=abc123" in summary
    assert sentinel_key not in result.output
    assert sentinel_value not in result.output


# --- 1 (late read-only). the sign-in is restored, with a `~/` path -----------------------


def test_a_google_sign_in_that_turns_read_only_late_is_restored(
    repo: Path,
    client_file: Path,
    google: Any,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    google()
    secrets_before = dict(_local_secrets())

    def late(*args: Any, **kwargs: Any) -> Path:
        raise connect_mod.UserScopeReadOnlyError(connect_mod._user_scope_path())

    monkeypatch.setattr(connect_mod, "_write_user_scope_provider", late)

    result = _oauth(repo, *_signin_args(client_file), "--scope", "user", "--json")

    assert result.exit_code == 1, result.output
    payload = json.loads(result.stdout)
    assert payload["state"] == "metadata_write_failed"
    assert "is read-only" in payload["summary"]
    assert "Make that file writable" in payload["summary"]
    assert "The new sign-in was removed, so nothing was stored" in payload["summary"]
    assert "~/" in payload["summary"]
    assert str(tmp_path) not in result.output
    assert bool(_local_secrets() == secrets_before)


# --- 2. not_recorded_note in token and exec ------------------------------------------------


def test_token_says_when_it_could_not_record_an_expired_sign_in(
    repo: Path, client_file: Path, google: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    _expire_and_fail_write(repo, client_file, google, monkeypatch)

    result = _token(repo)

    assert result.exit_code == 1
    assert result.stdout == ""
    assert "mb connect token: recorded: no (" in result.stderr
    assert "the disk is full" in result.stderr
    assert DETAIL not in result.output


def test_token_keeps_stdout_to_the_token_when_a_note_fires(
    repo: Path, client_file: Path, google: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    _signed_in(repo, client_file, google, "--scope", "user")
    _mint_with(monkeypatch, status=400, payload={"error": "invalid_grant"})
    assert connect_mod.read_token("google", repo)["ok"] is False
    gc.forget_minted()
    _mint_with(monkeypatch)
    _fail_user_write(connect_mod._user_scope_path(), "write", errno.ENOSPC, monkeypatch)

    result = _token(repo)

    assert result.exit_code == 0
    assert bool(result.stdout == MINTED)
    assert "mb connect token: recorded: no (" in result.stderr
    assert MINTED not in result.stderr


def test_token_has_no_note_when_nothing_failed(
    repo: Path, client_file: Path, google: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    _signed_in(repo, client_file, google, "--scope", "user")
    _mint_with(monkeypatch)

    result = _token(repo)

    assert bool(result.stdout == MINTED)
    assert "recorded" not in result.stderr


def test_exec_says_so_on_stderr_and_never_in_the_child_output(
    repo: Path, client_file: Path, google: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    _expire_and_fail_write(repo, client_file, google, monkeypatch)

    result = runner.invoke(
        app,
        ["connect", "exec", "google", "--repo", str(repo), "--", sys.executable, "-c", "pass"],
    )

    assert result.exit_code == 1
    assert result.stdout == ""
    assert "mb connect exec: recorded: no (" in result.stderr
    assert "the disk is full" in result.stderr


def test_exec_outcome_carries_the_note_only_when_it_fires(
    repo: Path, client_file: Path, google: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    _signed_in(repo, client_file, google, "--scope", "user")
    _mint_with(monkeypatch)
    quiet = connect_mod.exec_with_secret("google", ["true"], repo, runner=_ok_runner)
    assert "not_recorded_note" not in quiet

    _mint_with(monkeypatch, status=400, payload={"error": "invalid_grant"})
    gc.forget_minted()
    _fail_user_write(connect_mod._user_scope_path(), "write", errno.ENOSPC, monkeypatch)
    noisy = connect_mod.exec_with_secret("google", ["true"], repo, runner=_ok_runner)

    assert "the disk is full" in noisy["not_recorded_note"]


def _ok_runner(*args: Any, **kwargs: Any) -> Any:
    import subprocess

    return subprocess.CompletedProcess(args, 0)


# --- 4. the read write-back's own restore fails -------------------------------------------


def test_a_failed_config_put_back_is_reported_in_the_read_note(
    repo: Path, client_file: Path, google: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    _expire_and_fail_write(repo, client_file, google, monkeypatch)

    def refuse(*args: Any, **kwargs: Any) -> None:
        raise OSError(errno.EIO, DETAIL)

    monkeypatch.setattr(gc, "atomic_write_text", refuse)

    result = connect_mod.read_token("google", repo)

    assert result["rule"] == "reauth_required"
    assert result["ok"] is False
    note = result["not_recorded_note"]
    assert "the disk is full" in note
    assert ".mb/connect.yaml could not be put back either" in note
    assert DETAIL not in note
    # The note is true: the repo metadata still records the check.
    assert _config(repo)["providers"]["google"]["validation"]["state"] == "reauth_required"


def test_mb_connect_test_google_reports_the_failed_config_put_back(
    repo: Path, client_file: Path, google: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    _expire_and_fail_write(repo, client_file, google, monkeypatch)

    def refuse(*args: Any, **kwargs: Any) -> None:
        raise OSError(errno.EIO, DETAIL)

    monkeypatch.setattr(gc, "atomic_write_text", refuse)

    result = runner.invoke(app, ["connect", "test", "google", "--repo", str(repo), "--json"])

    detail = json.loads(result.stdout)["not_recorded_detail"]
    assert ".mb/connect.yaml could not be put back either" in detail
    assert DETAIL not in result.output


def test_a_successful_config_put_back_adds_nothing_to_the_note(
    repo: Path, client_file: Path, google: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    _expire_and_fail_write(repo, client_file, google, monkeypatch)

    note = connect_mod.read_token("google", repo)["not_recorded_note"]

    assert "could not be put back" not in note


# --- 5. a closed folder is named, not a read-only file ------------------------------------


@pytest.fixture
def close_folder(monkeypatch: pytest.MonkeyPatch) -> Iterator[Callable[[], None]]:
    """Close the user-scope file's folder to writing for real (mode 0500), on demand."""

    folder = connect_mod._user_scope_path().parent
    real_chmod = Path.chmod

    def chmod(self: Path, mode: int, *args: Any, **kwargs: Any) -> None:
        if self != folder:  # the writer's own `chmod 0700` would undo the setup
            real_chmod(self, mode, *args, **kwargs)

    monkeypatch.setattr(Path, "chmod", chmod)
    try:
        yield lambda: real_chmod(folder, 0o500)
    finally:
        real_chmod(folder, 0o700)


def test_a_check_over_a_closed_folder_names_the_folder(
    repo: Path, close_folder: Callable[[], None]
) -> None:
    _user_scope_cloudflare(repo)
    close_folder()

    result = runner.invoke(app, ["connect", "test", "cloudflare", "--repo", str(repo), "--json"])

    payload = json.loads(result.stdout)
    assert payload["not_recorded_reason"] == "user_scope_write_failed"
    assert "permission to write in its folder" in payload["not_recorded_detail"]
    assert "Make that folder writable" in payload["not_recorded_detail"]
    assert "read-only" not in result.output


def test_a_reconnect_over_a_closed_folder_names_the_folder(
    repo: Path, close_folder: Callable[[], None]
) -> None:
    _user_scope_cloudflare(repo)
    close_folder()

    result = _run(repo, "reconnect", True)

    assert result.exit_code == 1, result.output
    summary = json.loads(result.stdout)["summary"]
    assert "permission to write in its folder" in summary
    assert "Make that folder writable" in summary
    assert "read-only" not in summary
