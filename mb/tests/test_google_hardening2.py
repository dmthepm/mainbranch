"""Second round of Google connect hardening follow-ups (#1066).

The tracked-file check when git cannot answer, a first sign-in after a
metadata-only entry, product lines after `reauth_required`, a legacy
`keyring` record, `--oauth` next steps for Google, the PKCE wording, and the
tracked-file rule for other providers' `mb connect test`. No network: stub
senders and the local-file backend, as in test_google_hardening.
"""

# The fixtures are imported from test_google_connect, so test parameters
# share their names by design.
# ruff: noqa: F811

from __future__ import annotations

import json
import platform
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

from mb import connect as connect_mod
from mb import credential_store
from mb import google_connect as gc
from mb import google_oauth as go
from mb.cli import app
from tests.connect_binding import rebind_folder
from tests.test_google_connect import (  # noqa: F401 (fixtures are used by name)
    ACCESS,
    REFRESH,
    _google_entry,
    _oauth,
    client_file,
    google,
    google_env,
    loopback_only_network,
    repo,
    runner,
)
from tests.test_google_hardening import _edit, _git_status, _plain, _track_config
from tests.test_google_probe import (  # noqa: F401 (fixtures are used by name)
    SITE,
    _api,
    _assert_never_shown,
    _mint,
    _sign_in,
    _status,
    _test,
    _test_json,
    _yaml,
    fixed_day,
)

STRIPE_SENTINEL = "sk_test_SYNTH_HARDEN2_SENTINEL_0042"


def _fake_git(tmp_path: Path, exit_code: int) -> Path:
    """A directory holding a `git` that always exits ``exit_code``."""

    bin_dir = tmp_path / "fake-git-bin"
    bin_dir.mkdir()
    script = bin_dir / "git"
    script.write_text(f"#!/bin/sh\nexit {exit_code}\n", encoding="utf-8")
    script.chmod(0o755)
    return bin_dir


def _reauth_on_next_check(repo: Path, client_file: Path, google: Any, monkeypatch: Any) -> None:
    _sign_in(repo, client_file, google, monkeypatch)
    _mint(monkeypatch, status=400, payload={"error": "invalid_grant"})


def _metadata_only(repo: Path) -> None:
    """A tokenless `--metadata` entry: written, though it exits 1 (not connected)."""

    _edit(repo, f"search_console_site={SITE}")
    entry = _google_entry(repo)
    assert entry["metadata"]["search_console_site"] == SITE
    assert not gc.entry_is_oauth(entry)
    assert not (entry.get("secrets") or {})


# --- F1. The tracked-file check fails closed inside a git checkout --------------------------


def test_git_missing_from_path_counts_a_checkout_as_tracked(
    repo: Path, client_file: Path, google: Any, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _reauth_on_next_check(repo, client_file, google, monkeypatch)
    _track_config(repo)
    before = _yaml(repo)
    monkeypatch.setenv("PATH", str(tmp_path / "no-git-here"))

    code, result = _test_json(repo)

    assert code == 1
    assert result["recorded"] is False
    assert result["not_recorded_reason"] == "connect_yaml_tracked"
    assert _yaml(repo) == before


def test_a_git_error_counts_a_checkout_as_tracked(
    repo: Path, client_file: Path, google: Any, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Exit 128 is what git gives for dubious ownership (`safe.directory`)."""

    _reauth_on_next_check(repo, client_file, google, monkeypatch)
    _track_config(repo)
    before = _yaml(repo)
    monkeypatch.setenv("PATH", str(_fake_git(tmp_path, 128)))

    token = runner.invoke(app, ["connect", "token", "google", "--repo", str(repo), "--print"])

    assert token.exit_code == 1
    assert "mb connect google --oauth --reauth" in token.output
    assert _yaml(repo) == before


def test_git_environment_pointing_elsewhere_is_ignored(
    repo: Path, client_file: Path, google: Any, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _reauth_on_next_check(repo, client_file, google, monkeypatch)
    _track_config(repo)
    before = _yaml(repo)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=elsewhere, check=True, capture_output=True)
    monkeypatch.setenv("GIT_DIR", str(elsewhere / ".git"))
    monkeypatch.setenv("GIT_WORK_TREE", str(elsewhere))
    monkeypatch.setenv("GIT_INDEX_FILE", str(elsewhere / ".git" / "index"))

    _, result = _test_json(repo)

    assert result["not_recorded_reason"] == "connect_yaml_tracked"
    assert _yaml(repo) == before
    monkeypatch.delenv("GIT_DIR")
    monkeypatch.delenv("GIT_WORK_TREE")
    monkeypatch.delenv("GIT_INDEX_FILE")
    assert _git_status(repo) == ""


def test_a_timeout_counts_a_checkout_as_tracked(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (repo / ".git").mkdir()

    def slow(*args: Any, **kwargs: Any) -> Any:
        raise subprocess.TimeoutExpired(cmd="git", timeout=5)

    monkeypatch.setattr(subprocess, "run", slow)

    assert connect_mod.config_tracked_by_git(repo) is True


def test_a_git_failure_outside_any_checkout_still_records(
    repo: Path, client_file: Path, google: Any, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _reauth_on_next_check(repo, client_file, google, monkeypatch)
    monkeypatch.setenv("PATH", str(_fake_git(tmp_path, 128)))

    _, result = _test_json(repo)

    assert result["recorded"] is True
    assert "reauth_required" in _yaml(repo)


def test_an_untracked_file_in_a_checkout_still_reads_as_untracked(repo: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True, capture_output=True)
    rebind_folder(repo)
    (repo / ".mb").mkdir()
    (repo / ".mb" / "connect.yaml").write_text("version: 1\n", encoding="utf-8")

    assert connect_mod.config_tracked_by_git(repo) is False


# --- F2. A first sign-in after a metadata-only entry ----------------------------------------


def test_a_first_sign_in_after_metadata_only_honours_scope(
    repo: Path, client_file: Path, google: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    _metadata_only(repo)
    assert _google_entry(repo).get("scope", "repo") == "repo"
    google()
    _api(monkeypatch)

    result = _oauth(repo, "--client-file", str(client_file), "--scope", "user", "--json")

    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["scope"] == "user"
    assert payload["user_scope_path"]
    assert _google_entry(repo)["scope"] == "user"
    assert _google_entry(repo)["metadata"]["search_console_site"] == SITE
    _assert_never_shown(result.output + _yaml(repo))


def test_a_first_sign_in_after_metadata_only_keeps_its_scope_by_default(
    repo: Path, client_file: Path, google: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    _metadata_only(repo)
    google()
    _api(monkeypatch)

    result = _oauth(repo, "--client-file", str(client_file), "--json")

    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["scope"] == "repo"


# --- F3. Product lines after reauth_required ------------------------------------------------


def test_product_lines_after_reauth_say_the_sign_in_expired(
    repo: Path, client_file: Path, google: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    _sign_in(repo, client_file, google, monkeypatch)
    _mint(monkeypatch)
    _api(monkeypatch)
    assert _test_json(repo)[0] == 0
    _mint(monkeypatch, status=400, payload={"error": "invalid_grant"})
    runner.invoke(app, ["connect", "token", "google", "--repo", str(repo), "--print"])

    human = runner.invoke(app, ["connect", "status", "google", "--repo", str(repo)])

    lines = _plain(human.stdout).splitlines()
    assert "  search_console: granted, last check: not checked since the sign-in expired" in lines
    assert "  ga4: granted, last check: not checked since the sign-in expired" in lines
    assert "not checked yet" not in human.stdout
    assert "next: mb connect google --oauth --reauth" in lines


# --- F4. A legacy keyring record and MB_CONNECT_SECRET_BACKEND ------------------------------


def _legacy_keyring() -> gc._Existing:
    ref = "mainbranch://abc/google/access_token"
    return gc._Existing(
        entry={"scope": "repo"},
        grant={},
        token={"ref": ref, "backend": "keyring"},
    )


@pytest.mark.parametrize("requested", ["auto", "keyring", "macos-keychain", "KEYRING"])
def test_a_legacy_keyring_record_accepts_the_same_native_store(
    monkeypatch: pytest.MonkeyPatch, requested: str
) -> None:
    monkeypatch.setattr(platform, "system", lambda: "Darwin")

    gc._refuse_other_backend(_legacy_keyring(), requested)


def test_a_legacy_keyring_refusal_advice_is_never_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(platform, "system", lambda: "Darwin")

    with pytest.raises(connect_mod.ConnectRefusal) as refused:
        gc._refuse_other_backend(_legacy_keyring(), "local-file")

    assert refused.value.rule == "oauth_backend_kept"
    assert "set it to keyring" in str(refused.value)
    gc._refuse_other_backend(_legacy_keyring(), "keyring")


def test_a_legacy_keyring_record_still_refuses_another_store_on_linux(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(platform, "system", lambda: "Linux")

    gc._refuse_other_backend(_legacy_keyring(), "auto")
    with pytest.raises(connect_mod.ConnectRefusal):
        gc._refuse_other_backend(_legacy_keyring(), "macos-keychain")


# --- N2. Google's next steps name --oauth ---------------------------------------------------


def test_connect_test_google_without_a_connection_names_oauth(repo: Path) -> None:
    human = _test(repo)
    code, result = _test_json(repo)

    assert code == 1
    assert result["status"]["repair_command"] == "mb connect google --oauth"
    assert "next: mb connect google --oauth" in _plain(human.output)
    assert "--token-stdin" not in human.output + json.dumps(result)


def test_status_and_token_without_a_connection_name_oauth(repo: Path) -> None:
    code, payload = _status(repo)
    token = runner.invoke(app, ["connect", "token", "google", "--repo", str(repo), "--print"])

    assert code == 1
    assert payload["repair_command"] == "mb connect google --oauth"
    assert "mb connect google --oauth" in token.output
    assert "--token-stdin" not in token.output + json.dumps(payload)


def test_a_metadata_only_entry_names_oauth(repo: Path) -> None:
    _metadata_only(repo)

    _, payload = _status(repo)

    assert payload["repair_command"] == "mb connect google --oauth"


def test_an_invalid_sign_in_entry_names_reauth(
    repo: Path, client_file: Path, google: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    _sign_in(repo, client_file, google, monkeypatch)
    config = connect_mod._read_config(repo)
    config["providers"]["google"]["validation"] = {"state": "invalid", "summary": ""}
    connect_mod._write_config(repo, config)

    human = runner.invoke(app, ["connect", "status", "google", "--repo", str(repo)])
    code, payload = _status(repo)

    assert code == 1
    assert payload["repair_command"] == "mb connect google --oauth --reauth"
    assert "next: mb connect google --oauth --reauth" in _plain(human.stdout)
    assert "--token-stdin" not in human.output + json.dumps(payload)


def test_a_sign_in_entry_missing_its_token_names_reauth(
    repo: Path, client_file: Path, google: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    _sign_in(repo, client_file, google, monkeypatch)
    ref = _google_entry(repo)["secrets"]["access_token"]["ref"]
    credential_store.SecretStore("local-file").delete(ref)

    _, payload = _status(repo)

    assert payload["state"] == "missing_secret"
    assert payload["repair_command"] == "mb connect google --oauth --reauth"


def _run_named(repo: Path, command: str, client_file: Path) -> Any:
    """Run a `next:` command exactly as named, with the client file filled in."""

    named = command.replace("<Desktop client JSON>", str(client_file)).split()
    assert named[:2] == ["mb", "connect"]
    return runner.invoke(app, [*named[1:], "--repo", str(repo), "--json"])


def _wipe(repo: Path, *slots: str) -> None:
    for slot in slots:
        ref = _google_entry(repo)["secrets"][slot]["ref"]
        credential_store.SecretStore("local-file").delete(ref)


def test_the_named_reauth_works_when_only_the_token_is_missing(
    repo: Path, client_file: Path, google: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    _sign_in(repo, client_file, google, monkeypatch)
    _wipe(repo, "access_token")
    _, payload = _status(repo)
    google()
    _api(monkeypatch)

    renewed = _run_named(repo, payload["repair_command"], client_file)

    assert payload["repair_command"] == "mb connect google --oauth --reauth"
    assert renewed.exit_code == 0, renewed.output
    assert _status(repo)[1]["state"] == "ready"


def test_a_wiped_sign_in_names_the_client_file_and_that_command_works(
    repo: Path, client_file: Path, google: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Grant and token both gone (a reset store): `--reauth` alone is refused."""

    _sign_in(repo, client_file, google, monkeypatch)
    _wipe(repo, "oauth_grant", "access_token")

    _, payload = _status(repo)
    human = runner.invoke(app, ["connect", "status", "google", "--repo", str(repo)])
    _, tested = _test_json(repo)
    plain_test = _test(repo)

    assert payload["state"] == "missing_secret"
    assert payload["repair_command"] == gc.REAUTH_WITH_CLIENT_COMMAND
    assert tested["status"]["repair_command"] == gc.REAUTH_WITH_CLIENT_COMMAND
    assert f"next: {gc.REAUTH_WITH_CLIENT_COMMAND}" in _plain(human.stdout)
    assert f"next: {gc.REAUTH_WITH_CLIENT_COMMAND}" in _plain(plain_test.output)
    # The command as named is not refused for want of the OAuth client.
    bare = _run_named(repo, gc.REAUTH_COMMAND, client_file)
    assert json.loads(bare.stdout)["rule"] == "oauth_client_required"
    google()
    _api(monkeypatch)
    renewed = _run_named(repo, payload["repair_command"], client_file)
    assert renewed.exit_code == 0, renewed.output
    assert "oauth_client_required" not in renewed.output
    assert _status(repo)[1]["state"] == "ready"


@pytest.mark.parametrize("recorded", ["invalid", "reauth_required"])
def test_an_unreadable_grant_never_names_bare_reauth(
    repo: Path, client_file: Path, google: Any, monkeypatch: pytest.MonkeyPatch, recorded: str
) -> None:
    """The token is still stored, but the grant (and so its client) is gone."""

    _sign_in(repo, client_file, google, monkeypatch)
    config = connect_mod._read_config(repo)
    validation: dict[str, Any] = {"state": recorded, "summary": ""}
    if recorded == "reauth_required":
        validation["repair"] = f"Run `{gc.REAUTH_COMMAND}` in a terminal."
        validation["repair_command"] = gc.REAUTH_COMMAND
    config["providers"]["google"]["validation"] = validation
    connect_mod._write_config(repo, config)
    _wipe(repo, "oauth_grant")

    _, payload = _status(repo)

    # A recorded grant that is gone is missing, whatever was recorded (#1073).
    assert payload["state"] == "missing_secret"
    assert payload["repair_command"] == gc.REAUTH_WITH_CLIENT_COMMAND
    assert gc.REAUTH_WITH_CLIENT_COMMAND in payload["repair"] or not payload["repair"]


def test_a_legacy_access_token_entry_keeps_token_stdin(repo: Path) -> None:
    connect_mod.connect_provider("google", repo=repo, token="SYNTH-LEGACY-0010")
    config = connect_mod._read_config(repo)
    config["providers"]["google"]["validation"] = {"state": "invalid", "summary": ""}
    connect_mod._write_config(repo, config)

    _, payload = _status(repo)

    assert payload["repair_command"] == "mb connect google --token-stdin"


def test_other_providers_name_the_plain_connect_command(repo: Path) -> None:
    result = runner.invoke(app, ["connect", "test", "stripe", "--repo", str(repo), "--json"])

    assert result.exit_code == 1
    assert json.loads(result.stdout)["status"]["repair_command"] == ("mb connect stripe")


# --- N3. The authorization-code wording -----------------------------------------------------


def test_authorization_code_rejected_covers_a_mismatched_request() -> None:
    message = go._RULE_MESSAGES["authorization_code_rejected"]

    assert "did not match the sign-in request" in message
    assert "code_challenge" not in message


# --- Other providers' mb connect test and a tracked config ----------------------------------


def _stripe_check(monkeypatch: pytest.MonkeyPatch, *, ok: bool) -> None:
    def validate(provider: Any, secret: str, metadata: Any = None, **kwargs: Any) -> Any:
        assert secret == STRIPE_SENTINEL
        return {
            "ok": ok,
            "state": "ready" if ok else "invalid",
            "checked_at": connect_mod._now(),
            "provider_verified": ok,
            "summary": "Stripe accepted the key." if ok else "Stripe refused the key.",
            "repair": "" if ok else "Replace the key.",
            "repair_command": "" if ok else "mb connect stripe",
            "safe_to_share": True,
        }

    monkeypatch.setattr(connect_mod, "_validate_with_provider", validate)


def _connect_stripe(repo: Path) -> None:
    connect_mod.connect_provider("stripe", repo=repo, token=STRIPE_SENTINEL)


def test_another_providers_check_is_not_recorded_into_a_tracked_config(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _connect_stripe(repo)
    _track_config(repo)
    before = _yaml(repo)
    _stripe_check(monkeypatch, ok=False)

    human = runner.invoke(app, ["connect", "test", "stripe", "--repo", str(repo)])
    as_json = runner.invoke(app, ["connect", "test", "stripe", "--repo", str(repo), "--json"])

    result = json.loads(as_json.stdout)
    assert human.exit_code == 1 and as_json.exit_code == 1
    assert result["recorded"] is False
    assert result["not_recorded_reason"] == "connect_yaml_tracked"
    plain = _plain(human.stdout)
    assert "mb connect test stripe: warn (invalid)" in plain
    assert "recorded: no (.mb/connect.yaml is tracked by git" in plain
    assert "next: mb connect stripe" in plain
    assert _yaml(repo) == before
    assert _git_status(repo) == ""
    assert STRIPE_SENTINEL not in human.output + as_json.output + _yaml(repo)


def test_another_providers_passing_check_in_a_tracked_config_exits_0(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _connect_stripe(repo)
    _track_config(repo)
    before = _yaml(repo)
    _stripe_check(monkeypatch, ok=True)

    result = runner.invoke(app, ["connect", "test", "stripe", "--repo", str(repo)])

    # The stored status still reads unvalidated; the exit code follows the check.
    assert result.exit_code == 0, result.output
    assert "mb connect test stripe: ok (ready)" in _plain(result.stdout)
    assert "recorded: no" in result.stdout
    assert _yaml(repo) == before


def test_a_passing_google_check_in_a_tracked_config_exits_0(
    repo: Path, client_file: Path, google: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    _sign_in(repo, client_file, google, monkeypatch)
    # A metadata edit clears the recorded check, so status reads unvalidated.
    _edit(repo, f"search_console_site={SITE}")
    _track_config(repo)
    _mint(monkeypatch)
    _api(monkeypatch)

    result = _test(repo)

    assert result.exit_code == 0, result.output
    assert "recorded: no (.mb/connect.yaml is tracked by git" in _plain(result.output)


def test_another_providers_check_still_records_when_untracked(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _connect_stripe(repo)
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True, capture_output=True)
    rebind_folder(repo)
    _stripe_check(monkeypatch, ok=True)

    result = runner.invoke(app, ["connect", "test", "stripe", "--repo", str(repo), "--json"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert "recorded" not in payload
    assert payload["status"]["state"] == "ready"
    assert STRIPE_SENTINEL not in result.output + _yaml(repo)


def test_rotate_still_records_into_a_tracked_config(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A person running rotate asked for the write; its check lands too."""

    _connect_stripe(repo)
    config = connect_mod._read_config(repo)
    config["providers"]["stripe"].setdefault("metadata", {})["source"] = "op://Vault/Stripe/key"
    connect_mod._write_config(repo, config)
    _track_config(repo)
    _stripe_check(monkeypatch, ok=True)
    monkeypatch.setattr(
        connect_mod, "_read_onepassword_ref", lambda *args, **kwargs: STRIPE_SENTINEL
    )

    result = connect_mod.rotate_provider("stripe", repo)

    assert result["ok"] is True
    assert result["status"]["state"] == "ready"
    assert STRIPE_SENTINEL not in json.dumps(result) + _yaml(repo)


def test_the_new_paths_never_show_a_secret(
    repo: Path, client_file: Path, google: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    _sign_in(repo, client_file, google, monkeypatch)
    _mint(monkeypatch, status=400, payload={"error": "invalid_grant"})
    _track_config(repo)
    test = _test(repo)
    _status_code, payload = _status(repo)
    human = runner.invoke(app, ["connect", "status", "google", "--repo", str(repo)])

    text = test.output + json.dumps(payload) + human.output
    _assert_never_shown(text)
    assert ACCESS not in text and REFRESH not in text


@pytest.mark.parametrize("tracked", [False, True])
def test_a_probe_less_check_exits_0_tracked_or_not(repo: Path, tracked: bool) -> None:
    """A legacy Google access token has no probe: it warns, as on main, tracked or not."""

    connect_mod.connect_provider("google", repo=repo, token="SYNTH-LEGACY-0011")
    if tracked:
        _track_config(repo)
    else:
        subprocess.run(["git", "init", "-q"], cwd=repo, check=True, capture_output=True)
        rebind_folder(repo)
    before = _yaml(repo)

    result = runner.invoke(app, ["connect", "test", "google", "--repo", str(repo)])

    assert result.exit_code == 0, result.output
    assert ("recorded: no" in result.stdout) is tracked
    if tracked:
        assert _yaml(repo) == before


# --- Fix round 2: every stored-grant state names a command that is not refused ---------

GRANT_SENTINEL = "SYNTH-GRANT-SENTINEL-0077"
GRANT_SHAPES = (
    "absent",
    "valid",
    "garbage",
    "json_list",
    "client_id_missing",
    "client_id_empty",
    "client_secret_not_string",
    "refresh_token_missing",
)
# Shapes whose OAuth client `--reauth` can still read (#1073: one rule for a grant).
CLIENT_READABLE = ("valid", "refresh_token_missing")
VALIDATIONS = ("none", "ok", "invalid", "reauth_required")
SIGN_IN_PREFIX = "mb connect google --oauth"


def _grant_value(shape: str, valid: dict[str, Any]) -> str | None:
    if shape == "absent":
        return None
    if shape == "valid":
        return json.dumps(valid)
    if shape == "garbage":
        return f"not json {{ {GRANT_SENTINEL}"
    if shape == "json_list":
        return json.dumps([GRANT_SENTINEL, valid["client_id"]])
    if shape == "refresh_token_missing":
        # A valid client, so bare `--reauth` works, but nothing to mint with.
        return json.dumps({key: value for key, value in valid.items() if key != "refresh_token"})
    broken = {**valid, "refresh_token": GRANT_SENTINEL}
    if shape == "client_id_missing":
        broken.pop("client_id")
    elif shape == "client_id_empty":
        broken["client_id"] = ""
    else:
        broken["client_secret"] = 7
    return json.dumps(broken)


def _matrix_state(
    repo: Path,
    client_file: Path,
    google: Any,
    monkeypatch: pytest.MonkeyPatch,
    grant: str,
    token: str,
    recorded: str,
) -> None:
    """Sign in (repo untracked), then put the store and the record into one cell."""

    for path in (repo / ".mb", repo.parent / "home"):
        if path.exists():
            shutil.rmtree(path)
    gc.forget_minted()
    _sign_in(repo, client_file, google, monkeypatch)
    entry = _google_entry(repo)
    store = credential_store.SecretStore("local-file")
    grant_ref = entry["secrets"]["oauth_grant"]["ref"]
    valid = json.loads(store.probe(grant_ref).value)
    value = _grant_value(grant, valid)
    if value is None:
        store.delete(grant_ref)
    else:
        store.set(grant_ref, value)
    if token == "absent":
        store.delete(entry["secrets"]["access_token"]["ref"])
    config = connect_mod._read_config(repo)
    google_entry = config["providers"]["google"]
    if recorded == "none":
        google_entry.pop("validation", None)
    elif recorded == "invalid":
        google_entry["validation"] = {
            "state": "invalid",
            "checked_at": "2026-10-06T00:00:00Z",
            "provider_verified": False,
            "summary": "Google refused the stored sign-in's access.",
            "rule": "search_console_auth_rejected",
            "repair": f"Run `{gc.REAUTH_COMMAND}`.",
            "repair_command": gc.REAUTH_COMMAND,
        }
    elif recorded == "reauth_required":
        google_entry["validation"] = {
            "state": "reauth_required",
            "checked_at": "2026-10-06T00:00:00Z",
            "provider_verified": False,
            "summary": "Google refused the stored sign-in (expired or revoked).",
            "rule": "reauth_required",
            "repair": f"Run `{gc.REAUTH_COMMAND}` in a terminal (a person, not an agent).",
            "repair_command": gc.REAUTH_COMMAND,
        }
    # "ok" keeps the passing check the sign-in itself recorded.
    connect_mod._write_config(repo, config)
    gc.forget_minted()


def _next_line(output: str) -> str:
    lines = [line for line in _plain(output).splitlines() if line.startswith("next: ")]
    return lines[-1][len("next: ") :] if lines else ""


def _run_next(
    repo: Path, client_file: Path, google: Any, monkeypatch: pytest.MonkeyPatch, command: str
) -> Any:
    """Run a named next step against the current state; stubs stand in for Google."""

    if command.startswith(SIGN_IN_PREFIX):
        google()
        _api(monkeypatch)
    else:
        _mint(monkeypatch)
        _api(monkeypatch)
    return _run_named(repo, command, client_file)


@pytest.mark.parametrize("recorded", VALIDATIONS)
@pytest.mark.parametrize("token", ["present", "absent"])
@pytest.mark.parametrize("grant", GRANT_SHAPES)
def test_every_stored_grant_state_names_a_next_step_that_is_not_refused(
    repo: Path,
    client_file: Path,
    google: Any,
    monkeypatch: pytest.MonkeyPatch,
    grant: str,
    token: str,
    recorded: str,
) -> None:
    """8 grant shapes x 2 token states x 4 records: every cell is reachable by
    editing the store or the record after a sign-in, so none is skipped.

    Any grant that cannot mint is never `ready` in status, and status and
    `mb connect test google` name the same next step for it (#1073)."""

    seen: list[str] = []

    def check(command: str) -> None:
        if not command:
            return
        assert "<" not in command.replace("<Desktop client JSON>", ""), command
        # Bare --reauth only where the stored grant still holds a usable client.
        if (
            command.startswith(SIGN_IN_PREFIX)
            and "--reauth" in command
            and grant not in CLIENT_READABLE
        ):
            assert "--client-file" in command, command
        ran = _run_next(repo, client_file, google, monkeypatch, command)
        output = ran.output
        seen.append(output)
        assert "oauth_client_required" not in output, (command, output)
        assert ran.exit_code != 2, (command, output)
        if command.startswith(SIGN_IN_PREFIX):
            assert ran.exit_code == 0, (command, output)

    # Status, --json and plain, on one untouched state (status never writes).
    _matrix_state(repo, client_file, google, monkeypatch, grant, token, recorded)
    status_json = runner.invoke(app, ["connect", "status", "google", "--repo", str(repo), "--json"])
    status_plain = runner.invoke(app, ["connect", "status", "google", "--repo", str(repo)])
    payload = json.loads(status_json.stdout)
    named = str(payload.get("repair_command") or "")
    assert _next_line(status_plain.stdout) == named
    assert set(payload["secrets"]["oauth_grant"]) >= {"present", "readable", "usable"}
    assert payload["secrets"]["oauth_grant"]["readable"] is (grant in CLIENT_READABLE)
    assert payload["secrets"]["oauth_grant"]["usable"] is (grant == "valid")
    if grant != "valid":
        assert payload["state"] != "ready", payload["state"]
    seen += [status_json.output, status_plain.output]
    if payload["state"] != "ready":
        assert named, payload["state"]
    check(named)

    # `mb connect test google --json` on a fresh copy of the cell, then its next step.
    _matrix_state(repo, client_file, google, monkeypatch, grant, token, recorded)
    _mint(monkeypatch)
    _api(monkeypatch)
    tested = runner.invoke(app, ["connect", "test", "google", "--repo", str(repo), "--json"])
    result = json.loads(tested.stdout)
    test_named = str(result.get("repair_command") or "") or str(
        result["status"].get("repair_command") or ""
    )
    seen.append(tested.output)
    if not result["ok"] or result["status"]["state"] != "ready":
        assert test_named, result
    if grant != "valid":
        # One rule: the check and the stored status agree on the next step.
        assert test_named == named, (test_named, named)
    check(test_named)

    # The plain test on another fresh copy names the same next step.
    _matrix_state(repo, client_file, google, monkeypatch, grant, token, recorded)
    _mint(monkeypatch)
    _api(monkeypatch)
    plain = _test(repo)
    seen.append(plain.output)
    assert _next_line(plain.output) == test_named

    text = "\n".join(seen) + _yaml(repo)
    assert GRANT_SENTINEL not in text
    _assert_never_shown(text)


def test_a_repair_step_is_the_plain_command_so_an_owner_gets_the_hidden_prompt() -> None:
    """`--token-stdin` is for piped use; the one reviewed exception is a legacy Google token."""
    for provider_id in ("stripe", "cloudflare", "meta"):
        provider = connect_mod.resolve_provider(provider_id, Path("."))
        assert connect_mod._reconnect_command(provider) == f"mb connect {provider_id}"
        assert "--token-stdin" not in connect_mod._reconnect_step(provider, False)
