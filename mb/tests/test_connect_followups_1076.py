"""Google connect follow-ups from the #1075 review (#1076).

Strict `client_secret` types in a stored grant, user-scope writes that keep
what they do not own, rotate under a locked store, and rotate's step for a
Google entry with a source that is not 1Password. Fake backends and temp
config dirs only.
"""

# The fixtures are imported from test_google_connect, so test parameters
# share their names by design.
# ruff: noqa: F811

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

import pytest
import yaml

from mb import connect as connect_mod
from mb import credential_store
from mb import google_connect as gc
from mb.cli import app
from tests.test_google_connect import (  # noqa: F401 (fixtures are used by name)
    _google_entry,
    _oauth,
    _signin_args,
    client_file,
    google,
    google_env,
    loopback_only_network,
    repo,
    runner,
)
from tests.test_google_hardening2 import _metadata_only
from tests.test_google_probe import (  # noqa: F401 (fixtures are used by name)
    _api,
    _mint,
    _sign_in,
    _status,
    fixed_day,
)

BASE = {"client_id": "id.example.com", "refresh_token": "r-1"}


def _set_grant(repo: Path, grant: dict[str, Any]) -> None:
    ref = _google_entry(repo)["secrets"]["oauth_grant"]["ref"]
    credential_store.SecretStore("local-file").set(ref, json.dumps(grant))


# --- 1. client_secret types ----------------------------------------------------------


@pytest.mark.parametrize("secret", [[], False, 0, {}, 5, True, 1.5])
def test_a_client_secret_that_is_not_text_is_unreadable(secret: Any) -> None:
    value = json.dumps({**BASE, "client_secret": secret})

    assert gc.client_from_grant(value) is None
    assert gc.grant_repair_command(value) == gc.REAUTH_WITH_CLIENT_COMMAND


@pytest.mark.parametrize("secret", [None, "", "s-1", "missing"])
def test_a_missing_null_empty_or_text_client_secret_is_a_usable_client(secret: Any) -> None:
    grant = dict(BASE)
    if secret != "missing":
        grant["client_secret"] = secret
    value = json.dumps(grant)

    client = gc.client_from_grant(value)

    assert client is not None
    assert client.client_secret == (secret if secret in {"s-1"} else "")
    assert gc.grant_repair_command(value) == ""


@pytest.mark.parametrize("secret", [[], False, 0, {}, 5, True])
def test_every_path_names_the_same_step_for_a_bad_client_secret(
    repo: Path,
    client_file: Path,
    google: Any,
    monkeypatch: pytest.MonkeyPatch,
    secret: Any,
) -> None:
    _sign_in(repo, client_file, google, monkeypatch)
    _set_grant(repo, {**BASE, "client_secret": secret})

    code, status = _status(repo)
    assert status["state"] in {"invalid", "reauth_required"}
    assert status["repair_command"] == gc.REAUTH_WITH_CLIENT_COMMAND
    assert status["secrets"]["oauth_grant"]["usable"] is False
    _mint(monkeypatch)
    _api(monkeypatch)
    for args in (["token", "google", "--print"], ["test", "google", "--json"]):
        result = runner.invoke(app, ["connect", *args, "--repo", str(repo)])
        assert result.exit_code != 0, args
        assert gc.REAUTH_WITH_CLIENT_COMMAND in result.output
    rotated = runner.invoke(app, ["connect", "rotate", "google", "--repo", str(repo), "--json"])
    assert gc.REAUTH_WITH_CLIENT_COMMAND in json.loads(rotated.stdout)["summary"]


# --- 3. user-scope writes ----------------------------------------------------------------


def _user_file() -> Path:
    return connect_mod._user_scope_path()


def test_a_user_scope_write_keeps_other_top_level_keys(repo: Path) -> None:
    path = _user_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump({"version": 1, "note": {"kept": [1, 2]}, "repos": {}}), encoding="utf-8"
    )

    connect_mod.connect_provider(
        "stripe", repo=repo, token="sk_live_SYNTH1076abcdefghij", scope="user"
    )

    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert data["note"] == {"kept": [1, 2]}
    assert data["repos"]


def test_a_read_only_user_scope_file_is_not_replaced_or_changed(repo: Path) -> None:
    path = _user_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump({"version": 1, "repos": {}}), encoding="utf-8")
    path.chmod(0o400)
    before = path.read_bytes()
    inode = path.stat().st_ino

    with pytest.raises(connect_mod.UserScopeReadOnlyError) as caught:
        connect_mod._write_user_scope({"version": 1, "repos": {"x": {}}})

    assert str(path) in str(caught.value)
    assert "read-only" in str(caught.value)
    assert path.read_bytes() == before
    assert path.stat().st_ino == inode
    assert (path.stat().st_mode & 0o777) == 0o400


def test_a_stale_entry_is_kept_when_the_user_scope_file_is_read_only(repo: Path) -> None:
    connect_mod.connect_provider(
        "google",
        repo=repo,
        metadata_pairs=["search_console_site=sc-domain:example.com"],
        scope="user",
    )
    path = _user_file()
    path.chmod(0o400)
    before = path.read_bytes()
    repo_id = str(connect_mod._read_config(repo)["repo_id"])

    assert connect_mod._drop_user_scope_metadata_only(repo_id, "google") is False

    assert path.read_bytes() == before
    assert (path.stat().st_mode & 0o777) == 0o400


# --- 4. rotate under a locked store ----------------------------------------------------


def test_rotate_over_a_sign_in_under_a_locked_store_names_the_store_repair(
    repo: Path, client_file: Path, google: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    _sign_in(repo, client_file, google, monkeypatch)

    def locked(*args: Any, **kwargs: Any) -> credential_store.SecretProbe:
        return credential_store.SecretProbe("", False, False, "keychain_locked")

    monkeypatch.setattr(connect_mod, "_probe_secret_ref", locked)
    status_repair = credential_store.backend_repair("keychain_locked")["repair"]

    result = runner.invoke(app, ["connect", "rotate", "google", "--repo", str(repo), "--json"])

    payload = json.loads(result.stdout)
    assert result.exit_code == 2
    assert payload["rule"] == "rotate_backend_unavailable"
    assert status_repair in payload["summary"]
    assert "--client-file" not in payload["summary"]
    assert "once the store unlocks" in payload["summary"]
    assert connect_mod.status_provider("google", repo)["repair"] == status_repair


# --- 5. rotate_unsupported_source for Google ---------------------------------------------


def test_rotate_over_a_google_entry_with_a_foreign_source_names_the_sign_in(repo: Path) -> None:
    _metadata_only(repo)
    config = connect_mod._read_config(repo)
    config["providers"]["google"]["metadata"]["source"] = "vault://elsewhere/item"
    connect_mod._write_config(repo, config)

    result = runner.invoke(app, ["connect", "rotate", "google", "--repo", str(repo), "--json"])

    payload = json.loads(result.stdout)
    assert payload["rule"] == "rotate_unsupported_source"
    assert f"`{connect_mod.GOOGLE_SIGN_IN_COMMAND}`" in payload["summary"]
    assert "--token-stdin" not in payload["summary"]


# --- The CLI paths with a read-only user-scope file (review-1082) ------------------------


def _store_snapshot() -> dict[str, bytes]:
    """Every file under the config home except the user-scope file and the lock files.

    Lock files are empty and stay after a connect by design (#1150).
    """

    home = connect_mod._home()
    skip = connect_mod._user_scope_path()
    locks = home / "locks"
    return {
        str(path): path.read_bytes()
        for path in sorted(home.rglob("*"))
        if path.is_file() and path != skip and locks not in path.parents
    }


def _freeze_user_scope() -> tuple[Path, bytes, int, int]:
    path = connect_mod._user_scope_path()
    path.chmod(0o400)
    stat = path.stat()
    return path, path.read_bytes(), stat.st_ino, stat.st_mode & 0o777


def _assert_untouched(frozen: tuple[Path, bytes, int, int]) -> None:
    path, data, inode, mode = frozen
    stat = path.stat()
    assert path.read_bytes() == data
    assert (stat.st_ino, stat.st_mode & 0o777) == (inode, mode)


def _assert_refusal(result: Any, as_json: bool, path: Path) -> None:
    assert result.exit_code == 2, result.output
    assert "unexpected error" not in result.output
    if as_json:
        payload = json.loads(result.stdout)
        assert payload["rule"] == "user_scope_read_only"
        text = payload.get("summary", result.stdout)
    else:
        text = result.output
    assert path.name in text
    assert "read-only" in text
    assert "writable" in text


def _user_scope_cloudflare(repo: Path, *, source: str = "") -> None:
    connect_mod.connect_provider(
        "cloudflare",
        repo=repo,
        token="cf-old-token-1076",
        scope="user",
        source=source,
        metadata_pairs=["zone_id=abc123"],
    )


@pytest.mark.parametrize("as_json", [False, True])
def test_connect_user_scope_over_a_read_only_file_is_a_refusal_and_stores_nothing(
    repo: Path, as_json: bool
) -> None:
    _user_scope_cloudflare(repo)
    frozen = _freeze_user_scope()
    before = _store_snapshot()
    args = ["connect", "stripe", "--scope", "user", "--token-stdin", "--repo", str(repo)]

    result = runner.invoke(
        app, [*args, *(["--json"] if as_json else [])], input="sk_live_SYNTH1076abcdefghij\n"
    )

    _assert_refusal(result, as_json, frozen[0])
    assert "sk_live_SYNTH1076" not in result.output
    assert _store_snapshot() == before
    _assert_untouched(frozen)


@pytest.mark.parametrize("as_json", [False, True])
def test_rotate_a_user_scope_entry_over_a_read_only_file_stores_nothing(
    repo: Path, monkeypatch: pytest.MonkeyPatch, as_json: bool
) -> None:
    _user_scope_cloudflare(repo, source="op://Business/Cloudflare/credential")
    frozen = _freeze_user_scope()
    before = _store_snapshot()

    def run(args: Any, cwd: Any = None, timeout: float = 5.0, *, env: Any = None) -> Any:
        return {"ok": True, "returncode": 0, "stdout": "cf-rotated-1076", "stderr": ""}

    monkeypatch.setattr(connect_mod, "_run_command", run)
    monkeypatch.setattr(shutil, "which", lambda name: f"/usr/bin/{name}")

    result = runner.invoke(
        app,
        ["connect", "rotate", "cloudflare", "--repo", str(repo), *(["--json"] if as_json else [])],
    )

    _assert_refusal(result, as_json, frozen[0])
    assert "cf-rotated-1076" not in result.output
    assert _store_snapshot() == before
    _assert_untouched(frozen)


@pytest.mark.parametrize("as_json", [False, True])
def test_test_a_user_scope_entry_over_a_read_only_file_still_checks(
    repo: Path, monkeypatch: pytest.MonkeyPatch, as_json: bool
) -> None:
    _user_scope_cloudflare(repo)
    frozen = _freeze_user_scope()
    before = _store_snapshot()

    result = runner.invoke(
        app,
        ["connect", "test", "cloudflare", "--repo", str(repo), *(["--json"] if as_json else [])],
    )

    assert "unexpected error" not in result.output
    assert "PermissionError" not in result.output
    if as_json:
        payload = json.loads(result.stdout)
        assert payload["recorded"] is False
        assert payload["not_recorded_reason"] == "user_scope_read_only"
    assert _store_snapshot() == before
    _assert_untouched(frozen)


@pytest.mark.parametrize("as_json", [False, True])
def test_google_sign_in_user_scope_over_a_read_only_file_stores_no_grant(
    repo: Path, client_file: Path, google: Any, as_json: bool
) -> None:
    google()
    _user_scope_cloudflare(repo)
    frozen = _freeze_user_scope()
    before = _store_snapshot()

    result = _oauth(
        repo, *_signin_args(client_file), "--scope", "user", *(["--json"] if as_json else [])
    )

    _assert_refusal(result, as_json, frozen[0])
    assert "repo metadata" not in result.output
    assert _store_snapshot() == before
    _assert_untouched(frozen)


def test_google_sign_in_names_the_user_scope_file_when_it_turns_read_only_mid_write(
    repo: Path, client_file: Path, google: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    google()
    path = connect_mod._user_scope_path()

    def refuse(*args: Any, **kwargs: Any) -> Any:
        raise connect_mod.UserScopeReadOnlyError(path)

    monkeypatch.setattr(connect_mod, "_write_user_scope_provider", refuse)

    result = _oauth(repo, *_signin_args(client_file), "--scope", "user", "--json")

    payload = json.loads(result.stdout)
    assert payload["state"] == "metadata_write_failed"
    assert path.name in payload["summary"]
    assert "read-only" in payload["summary"]
    assert "once the store is healthy" not in payload["summary"]
    assert "repo metadata could not be written" not in payload["summary"]


def test_a_writable_user_scope_file_still_works_on_every_path(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _user_scope_cloudflare(repo, source="op://Business/Cloudflare/credential")

    def run(args: Any, cwd: Any = None, timeout: float = 5.0, *, env: Any = None) -> Any:
        return {"ok": True, "returncode": 0, "stdout": "cf-rotated-1076", "stderr": ""}

    monkeypatch.setattr(connect_mod, "_run_command", run)
    monkeypatch.setattr(shutil, "which", lambda name: f"/usr/bin/{name}")
    stripe = runner.invoke(
        app,
        ["connect", "stripe", "--scope", "user", "--token-stdin", "--repo", str(repo), "--json"],
        input="sk_live_SYNTH1076abcdefghij\n",
    )
    rotated = runner.invoke(app, ["connect", "rotate", "cloudflare", "--repo", str(repo), "--json"])
    tested = runner.invoke(app, ["connect", "test", "cloudflare", "--repo", str(repo), "--json"])

    assert stripe.exit_code == 0, stripe.output
    assert "user_scope_read_only" not in rotated.output + tested.output
    assert json.loads(tested.stdout).get("not_recorded_reason") != "user_scope_read_only"
