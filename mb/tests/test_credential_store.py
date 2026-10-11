"""Credential-store boundary and platform adapter tests."""

from __future__ import annotations

import io
import json
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
import yaml
from typer.testing import CliRunner

from mb import _credential_helper as helper_mod
from mb import connect as connect_mod
from mb import credential_store as store_mod
from mb.cli import app

runner = CliRunner()


def _local_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("MB_CONNECT_SECRET_BACKEND", "local-file")
    monkeypatch.setenv("MAINBRANCH_HOME", str(tmp_path / "home"))


def _popen_running(run: Any) -> Any:
    """A ``subprocess.Popen`` stand-in that answers through a ``run``-style fake."""

    class FakePopen:
        def __init__(self, args: list[str], **kwargs: Any) -> None:
            self.args = args
            self.kwargs = kwargs
            self.pid = None
            self.returncode: int | None = None

        def communicate(self, input: str | None = None, timeout: float | None = None) -> Any:
            result = run(
                self.args,
                input=input,
                timeout=timeout,
                stdout=self.kwargs.get("stdout"),
                stderr=self.kwargs.get("stderr"),
                text=True,
                start_new_session=self.kwargs.get("start_new_session"),
            )
            self.returncode = result.returncode
            return result.stdout, None

        def kill(self) -> None:
            pass

    return FakePopen


def _fake_subprocess(run: Any) -> SimpleNamespace:
    return SimpleNamespace(
        run=run,
        Popen=_popen_running(run),
        PIPE=subprocess.PIPE,
        DEVNULL=subprocess.DEVNULL,
        TimeoutExpired=subprocess.TimeoutExpired,
        SubprocessError=subprocess.SubprocessError,
    )


def _completed(stdout: str, stderr: str = "") -> SimpleNamespace:
    return SimpleNamespace(returncode=0, stdout=stdout, stderr=stderr)


def test_unknown_backend_selector_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MB_CONNECT_SECRET_BACKEND", "typo-store")

    with pytest.raises(ValueError, match="unknown credential backend"):
        store_mod.SecretStore()


@pytest.mark.parametrize(
    ("system", "expected"),
    [("Darwin", "macos-keychain"), ("Linux", "secret-service")],
)
def test_auto_selects_only_native_secure_backend(
    monkeypatch: pytest.MonkeyPatch, system: str, expected: str
) -> None:
    monkeypatch.delenv("MB_CONNECT_SECRET_BACKEND", raising=False)
    monkeypatch.setattr(store_mod.platform, "system", lambda: system)  # type: ignore[attr-defined]

    assert store_mod.select_secret_backend() == expected


def test_auto_never_falls_back_to_plaintext(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MB_CONNECT_SECRET_BACKEND", raising=False)
    monkeypatch.setattr(store_mod.platform, "system", lambda: "FreeBSD")  # type: ignore[attr-defined]

    with pytest.raises(store_mod.CredentialStoreError) as exc_info:
        store_mod.SecretStore()

    assert exc_info.value.reason == "backend_incompatible"


def test_explicit_local_file_preserves_exact_text(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _local_env(monkeypatch, tmp_path)
    value = "  first line\nsecond line  "
    store = store_mod.SecretStore("local-file")

    store.set("fixture-ref", value)

    assert store.probe("fixture-ref") == store_mod.SecretProbe(value, True, True, "")


def test_corrupt_local_file_is_not_clobbered_on_replacement(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _local_env(monkeypatch, tmp_path)
    path = tmp_path / "home" / "secrets" / "connect.json"
    path.parent.mkdir(parents=True)
    original = "{not-json\n"
    path.write_text(original, encoding="utf-8")

    with pytest.raises(store_mod.CredentialStoreError) as exc_info:
        store_mod.SecretStore("local-file").set("fixture-ref", "replacement")

    assert exc_info.value.reason == "local_file_corrupt"
    assert path.read_text(encoding="utf-8") == original


def test_failed_local_replacement_preserves_previous_value(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _local_env(monkeypatch, tmp_path)
    store = store_mod.SecretStore("local-file")
    store.set("fixture-ref", "previous")
    path = tmp_path / "home" / "secrets" / "connect.json"
    before = path.read_text(encoding="utf-8")

    def fail_write(path: Path, content: str) -> None:
        raise OSError("synthetic write failure")

    monkeypatch.setattr(store_mod, "atomic_write_text", fail_write)

    with pytest.raises(store_mod.CredentialStoreError) as exc_info:
        store.set("fixture-ref", "replacement")

    assert exc_info.value.reason == "local_file_unavailable"
    assert path.read_text(encoding="utf-8") == before
    assert json.loads(before)["fixture-ref"] == "previous"


def test_native_helper_keeps_secret_out_of_argv_and_discards_stderr(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    secret = "fixture-secret-never-in-argv"
    seen: dict[str, Any] = {}
    monkeypatch.setattr(store_mod.platform, "system", lambda: "Darwin")  # type: ignore[attr-defined]

    def fake_run(args: list[str], **kwargs: Any) -> SimpleNamespace:
        seen["args"] = args
        seen["input"] = kwargs["input"]
        seen["stdout"] = kwargs["stdout"]
        seen["stderr"] = kwargs["stderr"]
        return _completed('{"state":"unavailable"}', f"raw failure {secret}")

    monkeypatch.setattr(store_mod, "subprocess", _fake_subprocess(fake_run))

    with pytest.raises(store_mod.CredentialStoreError) as exc_info:
        store_mod.SecretStore("macos-keychain").set("fixture-ref", secret)

    assert secret not in " ".join(seen["args"])
    assert "fixture-ref" not in " ".join(seen["args"])
    assert secret in seen["input"]
    assert seen["stdout"] is subprocess.PIPE
    assert seen["stderr"] is subprocess.DEVNULL
    assert secret not in str(exc_info.value)
    assert "raw failure" not in str(exc_info.value)


def test_native_helper_timeout_is_bounded_and_sanitized(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(store_mod.platform, "system", lambda: "Darwin")  # type: ignore[attr-defined]

    def hang(args: list[str], **kwargs: Any) -> SimpleNamespace:
        raise subprocess.TimeoutExpired(args, kwargs["timeout"])

    monkeypatch.setattr(store_mod, "subprocess", _fake_subprocess(hang))

    probe = store_mod.SecretStore("macos-keychain").probe("fixture-ref")

    assert probe.backend_ok is False
    assert probe.reason == "credential_store_timeout"


@pytest.mark.parametrize(
    ("helper_state", "reason"),
    [
        ("locked", "keychain_locked"),
        ("auth-failed", "keychain_auth_failed"),
        ("prompt-pending", "keychain_prompt_pending"),
        ("unavailable", "keychain_unavailable"),
    ],
)
def test_native_failure_states_are_sanitized(
    monkeypatch: pytest.MonkeyPatch, helper_state: str, reason: str
) -> None:
    monkeypatch.setattr(store_mod.platform, "system", lambda: "Darwin")  # type: ignore[attr-defined]
    monkeypatch.setattr(
        store_mod,
        "_run_helper",
        lambda backend, action, **kwargs: {"state": helper_state},
    )

    probe = store_mod.SecretStore("macos-keychain").probe("fixture-ref")

    assert probe == store_mod.SecretProbe("", False, False, reason)


def test_macos_read_query_explicitly_forbids_authentication_ui() -> None:
    adapter: Any = object.__new__(helper_mod._MacSecurity)
    adapter.security = object()
    adapter.core = object()
    adapter.search_list = None
    constants = {
        "kSecClass": 1,
        "kSecClassGenericPassword": 2,
        "kSecAttrService": 3,
        "kSecAttrAccount": 4,
        "kSecUseAuthenticationUI": 5,
        "kSecUseAuthenticationUIFail": 6,
        "kSecMatchLimit": 7,
        "kSecMatchLimitOne": 8,
        "kSecReturnData": 9,
        "kCFBooleanTrue": 10,
    }
    captured: list[tuple[int, int]] = []
    adapter._constant = lambda library, name: constants[name]
    adapter._string = lambda value: 20 if value == helper_mod.SERVICE_NAME else 21

    def capture(pairs: list[tuple[int, int]]) -> int:
        captured.extend(pairs)
        return 99

    adapter._dictionary = capture

    query, owned = adapter._query("fixture-ref", return_data=True)

    assert query == 99
    assert owned == [20, 21]
    assert (constants["kSecUseAuthenticationUI"], constants["kSecUseAuthenticationUIFail"]) in (
        captured
    )


def test_macos_failed_update_preserves_previous_item_without_delete() -> None:
    state = {"value": "previous", "add_called": False, "delete_called": False}

    class FakeSecurity:
        def SecItemUpdate(self, query: int, update: int) -> int:
            return helper_mod.ERR_SEC_AUTH_FAILED

        def SecItemAdd(self, add: int, result: Any) -> int:
            state["add_called"] = True
            return helper_mod.ERR_SEC_SUCCESS

        def SecItemDelete(self, query: int) -> int:
            state["delete_called"] = True
            return helper_mod.ERR_SEC_SUCCESS

    adapter: Any = object.__new__(helper_mod._MacSecurity)
    adapter.security = FakeSecurity()
    adapter.health = lambda: "ready"
    adapter._item_owner = lambda ref: "legacy"
    adapter._update = lambda ref, value: helper_mod.ERR_SEC_AUTH_FAILED

    result = adapter.set("fixture-ref", "replacement")

    # On an unlocked keychain the refusal means a macOS dialog would wait.
    assert result == "prompt-pending"
    assert state == {"value": "previous", "add_called": False, "delete_called": False}


def test_macos_add_explicitly_forbids_authentication_ui() -> None:
    adapter: Any = object.__new__(helper_mod._MacSecurity)
    adapter.security = SimpleNamespace(SecItemAdd=lambda add, result: helper_mod.ERR_SEC_SUCCESS)
    adapter.core = SimpleNamespace(CFRelease=lambda value: None)
    adapter.keychain = None
    adapter.health = lambda: "ready"
    constants = {
        "kSecClass": 1,
        "kSecClassGenericPassword": 2,
        "kSecAttrService": 3,
        "kSecAttrAccount": 4,
        "kSecValueData": 5,
        "kSecUseAuthenticationUI": 6,
        "kSecUseAuthenticationUIFail": 7,
    }
    captured: list[tuple[int, int]] = []
    adapter._constant = lambda library, name: constants[name]
    adapter._string = lambda value: 20 if value == helper_mod.SERVICE_NAME else 21
    adapter._data = lambda value: 22
    adapter._update = lambda ref, value: helper_mod.ERR_SEC_ITEM_NOT_FOUND

    def capture(pairs: list[tuple[int, int]]) -> int:
        captured.extend(pairs)
        return 99

    adapter._dictionary = capture
    adapter._release_all = lambda values: None

    # The legacy add is now only the restore path of a failed migration.
    assert adapter._ctypes_add("fixture-ref", "replacement") == helper_mod.ERR_SEC_SUCCESS
    assert (constants["kSecUseAuthenticationUI"], constants["kSecUseAuthenticationUIFail"]) in (
        captured
    )


def test_missing_item_is_distinct_from_backend_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(store_mod.platform, "system", lambda: "Darwin")  # type: ignore[attr-defined]
    monkeypatch.setattr(
        store_mod,
        "_run_helper",
        lambda backend, action, **kwargs: {"state": "missing"},
    )

    probe = store_mod.SecretStore("macos-keychain").probe("fixture-ref")

    assert probe == store_mod.SecretProbe("", False, True, "")


@pytest.mark.parametrize(
    ("system", "expected"),
    [("Darwin", "macos-keychain"), ("Linux", "secret-service")],
)
def test_legacy_keyring_metadata_maps_to_native_adapter(
    monkeypatch: pytest.MonkeyPatch, system: str, expected: str
) -> None:
    monkeypatch.setattr(store_mod.platform, "system", lambda: system)  # type: ignore[attr-defined]

    assert store_mod.SecretStore("keyring").backend == expected


def test_cli_rejects_unknown_backend_before_writing_metadata(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MAINBRANCH_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("MB_CONNECT_SECRET_BACKEND", "typo-store")
    repo = tmp_path / "business"
    repo.mkdir()
    secret = "fixture-secret-not-printed"

    result = runner.invoke(
        app,
        ["connect", "cloudflare", "--repo", str(repo), "--token-stdin"],
        input=secret + "\n",
    )

    assert result.exit_code == 2
    assert "unknown credential backend" in result.stderr
    assert secret not in result.stderr
    assert not (repo / ".mb" / "connect.yaml").exists()


def test_foreign_backend_metadata_fails_closed_in_status(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _local_env(monkeypatch, tmp_path)
    repo = tmp_path / "business"
    repo.mkdir()
    connect_mod.connect_provider("cloudflare", repo, token="fixture-token")
    path = repo / ".mb" / "connect.yaml"
    config = yaml.safe_load(path.read_text(encoding="utf-8"))
    config["providers"]["cloudflare"]["secrets"]["api_token"]["backend"] = "secret-service"
    path.write_text(yaml.safe_dump(config), encoding="utf-8")
    monkeypatch.setattr(store_mod.platform, "system", lambda: "Darwin")  # type: ignore[attr-defined]

    status = connect_mod.status_provider("cloudflare", repo)

    assert status["state"] == "backend_unavailable"
    assert status["secrets"]["api_token"]["backend_state"] == "backend_incompatible"


def test_tokenless_reconnect_preserves_existing_ref_and_backend(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _local_env(monkeypatch, tmp_path)
    repo = tmp_path / "business"
    repo.mkdir()
    connect_mod.connect_provider("cloudflare", repo, token="fixture-token")
    path = repo / ".mb" / "connect.yaml"
    before = yaml.safe_load(path.read_text(encoding="utf-8"))
    before_secret = before["providers"]["cloudflare"]["secrets"]["api_token"]
    monkeypatch.delenv("MB_CONNECT_SECRET_BACKEND", raising=False)
    monkeypatch.setattr(store_mod.platform, "system", lambda: "Darwin")  # type: ignore[attr-defined]

    result = connect_mod.connect_provider(
        "cloudflare", repo, metadata_pairs=["account_id=fixture-account"]
    )
    after = yaml.safe_load(path.read_text(encoding="utf-8"))
    after_secret = after["providers"]["cloudflare"]["secrets"]["api_token"]

    assert after_secret == before_secret
    assert result["credential_backend"] == "local-file"
    assert connect_mod.read_token("cloudflare", repo)["token"] == "fixture-token"


def test_tokenless_reconnect_rejects_incompatible_recorded_backend(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _local_env(monkeypatch, tmp_path)
    repo = tmp_path / "business"
    repo.mkdir()
    connect_mod.connect_provider("cloudflare", repo, token="fixture-token")
    path = repo / ".mb" / "connect.yaml"
    config = yaml.safe_load(path.read_text(encoding="utf-8"))
    config["providers"]["cloudflare"]["secrets"]["api_token"]["backend"] = "secret-service"
    path.write_text(yaml.safe_dump(config), encoding="utf-8")
    before = path.read_text(encoding="utf-8")
    monkeypatch.setattr(store_mod.platform, "system", lambda: "Darwin")  # type: ignore[attr-defined]

    with pytest.raises(store_mod.CredentialStoreError) as exc_info:
        connect_mod.connect_provider("cloudflare", repo)

    assert exc_info.value.reason == "backend_incompatible"
    assert path.read_text(encoding="utf-8") == before


def test_tokenless_reconnect_preserves_matching_user_scope_ref_and_backend(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _local_env(monkeypatch, tmp_path)
    canonical = tmp_path / "canonical"
    fresh = tmp_path / "fresh"
    canonical.mkdir()
    fresh.mkdir()

    def fake_git(repo: Path, args: list[str]) -> str:
        if args == ["config", "--get", "remote.origin.url"]:
            return "git@github.com:acme/business.git"
        return ""

    monkeypatch.setattr(connect_mod, "_git_output", fake_git)
    connect_mod.connect_provider(
        "cloudflare",
        canonical,
        token="fixture-token",
        scope="user",
    )
    user_scope_path = tmp_path / "home" / connect_mod.USER_SCOPE_RELATIVE_PATH
    user_scope = yaml.safe_load(user_scope_path.read_text(encoding="utf-8"))
    repo_id = next(iter(user_scope["repos"]))
    expected_secret = user_scope["repos"][repo_id]["providers"]["cloudflare"]["secrets"][
        "api_token"
    ]
    monkeypatch.delenv("MB_CONNECT_SECRET_BACKEND", raising=False)
    monkeypatch.setattr(store_mod.platform, "system", lambda: "Darwin")  # type: ignore[attr-defined]
    monkeypatch.setattr(
        store_mod,
        "_run_helper",
        lambda backend, action, **kwargs: {"state": "missing"},
    )

    result = connect_mod.connect_provider(
        "cloudflare",
        fresh,
        metadata_pairs=["account_id=fixture-account"],
    )
    fresh_config = yaml.safe_load((fresh / ".mb" / "connect.yaml").read_text(encoding="utf-8"))

    assert fresh_config["providers"]["cloudflare"]["secrets"]["api_token"] == expected_secret
    assert result["credential_backend"] == "local-file"
    assert connect_mod.read_token("cloudflare", fresh)["token"] == "fixture-token"


def test_tokenless_reconnect_rejects_incompatible_matching_user_scope_backend(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _local_env(monkeypatch, tmp_path)
    canonical = tmp_path / "canonical"
    fresh = tmp_path / "fresh"
    canonical.mkdir()
    fresh.mkdir()

    def fake_git(repo: Path, args: list[str]) -> str:
        if args == ["config", "--get", "remote.origin.url"]:
            return "git@github.com:acme/business.git"
        return ""

    monkeypatch.setattr(connect_mod, "_git_output", fake_git)
    connect_mod.connect_provider(
        "cloudflare",
        canonical,
        token="fixture-token",
        scope="user",
    )
    user_scope_path = tmp_path / "home" / connect_mod.USER_SCOPE_RELATIVE_PATH
    user_scope = yaml.safe_load(user_scope_path.read_text(encoding="utf-8"))
    repo_id = next(iter(user_scope["repos"]))
    user_scope["repos"][repo_id]["providers"]["cloudflare"]["secrets"]["api_token"]["backend"] = (
        "secret-service"
    )
    user_scope_path.write_text(yaml.safe_dump(user_scope), encoding="utf-8")
    monkeypatch.delenv("MB_CONNECT_SECRET_BACKEND", raising=False)
    monkeypatch.setattr(store_mod.platform, "system", lambda: "Darwin")  # type: ignore[attr-defined]
    monkeypatch.setattr(
        store_mod,
        "_run_helper",
        lambda backend, action, **kwargs: {"state": "missing"},
    )

    with pytest.raises(store_mod.CredentialStoreError) as exc_info:
        connect_mod.connect_provider("cloudflare", fresh)

    assert exc_info.value.reason == "backend_incompatible"
    assert not (fresh / ".mb" / "connect.yaml").exists()


def test_supplied_repo_token_ignores_corrupt_user_scope(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _local_env(monkeypatch, tmp_path)
    repo = tmp_path / "business"
    repo.mkdir()
    user_scope_path = tmp_path / "home" / connect_mod.USER_SCOPE_RELATIVE_PATH
    user_scope_path.parent.mkdir(parents=True)
    user_scope_path.write_text("{not-yaml\n", encoding="utf-8")
    monkeypatch.setattr(connect_mod, "_git_output", lambda repo, args: "")

    result = connect_mod.connect_provider(
        "cloudflare",
        repo,
        token="fixture-token",
        secret_backend="local-file",
        scope="repo",
    )

    assert result["ok"] is True
    assert result["scope"] == "repo"
    assert connect_mod.read_token("cloudflare", repo)["token"] == "fixture-token"
    assert user_scope_path.read_text(encoding="utf-8") == "{not-yaml\n"


def test_repo_backend_outage_never_falls_back_to_user_scope(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _local_env(monkeypatch, tmp_path)
    repo = tmp_path / "business"
    repo.mkdir()
    connect_mod.connect_provider("cloudflare", repo, token="user-token", scope="user")
    path = repo / ".mb" / "connect.yaml"
    config = yaml.safe_load(path.read_text(encoding="utf-8"))
    config["providers"]["cloudflare"]["secrets"]["api_token"]["backend"] = "macos-keychain"
    path.write_text(yaml.safe_dump(config), encoding="utf-8")
    monkeypatch.setattr(store_mod.platform, "system", lambda: "Darwin")  # type: ignore[attr-defined]
    monkeypatch.setattr(
        store_mod,
        "_run_helper",
        lambda backend, action, **kwargs: {"state": "locked"},
    )

    result = connect_mod.read_token("cloudflare", repo)

    assert result["ok"] is False
    assert result["source"] == "repo"
    assert result["state"] == "backend_unavailable"
    assert result["backend_state"] == "keychain_locked"
    assert "user-token" not in json.dumps(result)

    cli = runner.invoke(app, ["connect", "token", "cloudflare", "--print", "--repo", str(repo)])
    assert cli.exit_code == 1
    assert cli.stdout == ""
    assert "login Keychain is locked" in cli.stderr
    assert "user-token" not in cli.stderr


def test_doctor_checks_the_recorded_backend_instead_of_auto(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MAINBRANCH_HOME", str(tmp_path / "home"))
    monkeypatch.delenv("MB_CONNECT_SECRET_BACKEND", raising=False)
    monkeypatch.setattr(store_mod.platform, "system", lambda: "Darwin")  # type: ignore[attr-defined]
    repo = tmp_path / "business"
    repo.mkdir()
    connect_mod.connect_provider(
        "cloudflare", repo, token="fixture-token", secret_backend="local-file"
    )

    report = connect_mod.doctor(repo)
    checks = {check["name"]: check for check in report["checks"]}

    assert checks["credential-backend"]["ok"] is True
    assert "local-file" in checks["credential-backend"]["summary"]


def test_provider_test_reuses_first_failed_credential_probe(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _local_env(monkeypatch, tmp_path)
    repo = tmp_path / "business"
    repo.mkdir()
    connect_mod.connect_provider("cloudflare", repo, token="fixture-token")
    path = repo / ".mb" / "connect.yaml"
    config = yaml.safe_load(path.read_text(encoding="utf-8"))
    config["providers"]["cloudflare"]["secrets"]["api_token"]["backend"] = "macos-keychain"
    path.write_text(yaml.safe_dump(config), encoding="utf-8")
    monkeypatch.setattr(store_mod.platform, "system", lambda: "Darwin")  # type: ignore[attr-defined]
    calls = 0

    def fail_once(backend: str, action: str, **kwargs: Any) -> dict[str, str]:
        nonlocal calls
        calls += 1
        return {"state": "locked"}

    monkeypatch.setattr(store_mod, "_run_helper", fail_once)

    result = connect_mod.test_provider("cloudflare", repo)

    assert result["status"]["state"] == "backend_unavailable"
    assert calls == 1


def test_status_all_shares_one_aggregate_credential_deadline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _local_env(monkeypatch, tmp_path)
    repo = tmp_path / "business"
    repo.mkdir()
    connect_mod.connect_provider("cloudflare", repo, token="fixture-cloudflare")
    connect_mod.connect_provider("resend", repo, token="re_fixture")
    path = repo / ".mb" / "connect.yaml"
    config = yaml.safe_load(path.read_text(encoding="utf-8"))
    for provider, field in (("cloudflare", "api_token"), ("resend", "api_key")):
        config["providers"][provider]["secrets"][field]["backend"] = "macos-keychain"
    path.write_text(yaml.safe_dump(config), encoding="utf-8")
    monkeypatch.setattr(store_mod.platform, "system", lambda: "Darwin")  # type: ignore[attr-defined]
    clock = iter([0.0, 0.0, 9.0])
    monkeypatch.setattr(time, "monotonic", lambda: next(clock))
    calls = 0

    def unavailable(args: list[str], **kwargs: Any) -> SimpleNamespace:
        nonlocal calls
        calls += 1
        return SimpleNamespace(returncode=1, stdout='{"state":"unavailable"}')

    monkeypatch.setattr(store_mod, "subprocess", _fake_subprocess(unavailable))

    status = connect_mod.status_all(repo)

    assert calls == 1
    states = {
        provider["secrets"][next(iter(provider["secrets"]))]["backend_state"]
        for provider in status["providers"]
    }
    # The provider the spent budget never reached is not checked, not a broken
    # store (#1151); the one that was read still reports what the store said.
    assert states == {"keychain_unavailable", "not_checked"}


def test_token_stdin_and_stdout_preserve_whitespace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _local_env(monkeypatch, tmp_path)
    repo = tmp_path / "business"
    repo.mkdir()
    value = "  first line\nsecond line  "

    connected = runner.invoke(
        app,
        ["connect", "mercury", "--custom", "--repo", str(repo), "--token-stdin"],
        input=value + "\n",
    )
    read = runner.invoke(app, ["connect", "token", "mercury", "--print", "--repo", str(repo)])

    assert connected.exit_code == 0
    assert read.exit_code == 0
    assert read.stdout == value


def test_environment_credential_preserves_whitespace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _local_env(monkeypatch, tmp_path)
    repo = tmp_path / "business"
    repo.mkdir()
    value = "  fixture-token  "
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", value)

    connected = runner.invoke(
        app,
        ["connect", "cloudflare", "--repo", str(repo), "--from-env"],
    )
    read = runner.invoke(app, ["connect", "token", "cloudflare", "--print", "--repo", str(repo)])

    assert connected.exit_code == 0
    assert read.stdout == value


class _FakeCollection:
    def __init__(self, *, locked: bool = False, items: list[Any] | None = None) -> None:
        self.locked = locked
        self.items = items or []
        self.created: dict[str, Any] = {}

    def is_locked(self) -> bool:
        return self.locked

    def search_items(self, attributes: dict[str, str]) -> list[Any]:
        return self.items

    def create_item(
        self,
        label: str,
        attributes: dict[str, str],
        secret: bytes,
        *,
        replace: bool,
    ) -> None:
        self.created = {
            "label": label,
            "attributes": attributes,
            "secret": secret,
            "replace": replace,
        }


class _FakeSecretServiceItem:
    def __init__(self, value: str, *, application: str) -> None:
        self.value = value.encode("utf-8")
        self.attributes = {
            "application": application,
            "service": store_mod.SERVICE_NAME,
            "username": "fixture-ref",
        }

    def is_locked(self) -> bool:
        return False

    def get_attributes(self) -> dict[str, str]:
        return dict(self.attributes)

    def get_secret(self) -> bytes:
        return self.value

    def set_secret(self, value: bytes) -> None:
        self.value = value


def _fake_secretstorage(collection: _FakeCollection) -> SimpleNamespace:
    return SimpleNamespace(
        dbus_init=lambda: object(),
        get_collection_by_alias=lambda connection, alias: collection,
    )


def test_simulated_linux_locked_collection_is_checked_without_unlock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    collection = _FakeCollection(locked=True)
    monkeypatch.setattr(helper_mod.platform, "system", lambda: "Linux")  # type: ignore[attr-defined]
    monkeypatch.setattr(
        helper_mod.importlib,  # type: ignore[attr-defined]
        "import_module",
        lambda name: _fake_secretstorage(collection),
    )

    state, value = helper_mod._secret_service("get", {"ref": "fixture-ref"})

    assert (state, value) == ("locked", None)
    assert not hasattr(collection, "unlock")


def test_simulated_linux_new_item_uses_secret_service_replace(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    collection = _FakeCollection()
    monkeypatch.setattr(helper_mod.platform, "system", lambda: "Linux")  # type: ignore[attr-defined]
    monkeypatch.setattr(
        helper_mod.importlib,  # type: ignore[attr-defined]
        "import_module",
        lambda name: _fake_secretstorage(collection),
    )

    state, value = helper_mod._secret_service(
        "set", {"ref": "fixture-ref", "value": "fixture-secret"}
    )

    assert (state, value) == ("ready", None)
    assert collection.created["replace"] is True
    assert collection.created["secret"] == b"fixture-secret"


def test_simulated_linux_rotation_updates_legacy_keyring_item_in_place(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    legacy = _FakeSecretServiceItem("old", application="Python keyring library")
    collection = _FakeCollection(items=[legacy])
    monkeypatch.setattr(helper_mod.platform, "system", lambda: "Linux")  # type: ignore[attr-defined]
    monkeypatch.setattr(
        helper_mod.importlib,  # type: ignore[attr-defined]
        "import_module",
        lambda name: _fake_secretstorage(collection),
    )

    set_state, _ = helper_mod._secret_service("set", {"ref": "fixture-ref", "value": "new"})
    get_state, value = helper_mod._secret_service("get", {"ref": "fixture-ref"})

    assert set_state == "ready"
    assert (get_state, value) == ("ready", "new")
    assert legacy.get_attributes()["application"] == "Python keyring library"
    assert collection.created == {}


def test_simulated_linux_duplicate_lookup_prefers_canonical_item(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    legacy = _FakeSecretServiceItem("old", application="Python keyring library")
    canonical = _FakeSecretServiceItem("new", application="mainbranch")
    collection = _FakeCollection(items=[legacy, canonical])
    monkeypatch.setattr(helper_mod.platform, "system", lambda: "Linux")  # type: ignore[attr-defined]
    monkeypatch.setattr(
        helper_mod.importlib,  # type: ignore[attr-defined]
        "import_module",
        lambda name: _fake_secretstorage(collection),
    )

    state, value = helper_mod._secret_service("get", {"ref": "fixture-ref"})

    assert (state, value) == ("ready", "new")


def test_simulated_linux_failed_in_place_rotation_preserves_previous_value(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    class FailingItem(_FakeSecretServiceItem):
        def set_secret(self, value: bytes) -> None:
            raise RuntimeError("synthetic update failure")

    legacy = FailingItem("old", application="Python keyring library")
    collection = _FakeCollection(items=[legacy])
    monkeypatch.setattr(helper_mod.platform, "system", lambda: "Linux")  # type: ignore[attr-defined]
    monkeypatch.setattr(
        helper_mod.importlib,  # type: ignore[attr-defined]
        "import_module",
        lambda name: _fake_secretstorage(collection),
    )
    monkeypatch.setattr(sys, "argv", ["helper", "secret-service", "set"])
    monkeypatch.setattr(
        sys,
        "stdin",
        io.StringIO('{"ref":"fixture-ref","value":"replacement"}'),
    )

    result = helper_mod.main()
    captured = capsys.readouterr()

    assert result == 1
    assert json.loads(captured.out) == {"state": "unavailable"}
    assert legacy.get_secret() == b"old"


def test_helper_never_emits_raw_exception_text(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    sentinel = "fixture-secret-from-raw-exception"
    monkeypatch.setattr(sys, "argv", ["helper", "macos-keychain", "get"])
    monkeypatch.setattr(sys, "stdin", io.StringIO('{"ref":"fixture-ref"}'))
    monkeypatch.setattr(
        helper_mod,
        "_macos",
        lambda action, payload: (_ for _ in ()).throw(RuntimeError(sentinel)),
    )

    result = helper_mod.main()
    captured = capsys.readouterr()

    assert result == 1
    assert json.loads(captured.out) == {"state": "unavailable"}
    assert sentinel not in captured.out
    assert captured.err == ""


def test_secret_probe_repr_hides_the_value() -> None:
    from rich.pretty import pretty_repr

    secret = "SYNTH-PROBE-SECRET-0001"
    probe = store_mod.SecretProbe(secret, True, True, "", False, "security")
    for text in (repr(probe), str(probe), pretty_repr({"probe": probe}), f"{probe!r}"):
        assert secret not in text
        assert "present=True" in text
    assert "value=<empty>" in repr(store_mod.SecretProbe("", False, True, ""))
    # The value itself, equality and tuple behaviour are unchanged.
    assert probe.value == secret and probe[0] == secret
    assert probe == store_mod.SecretProbe(secret, True, True, "", False, "security")
