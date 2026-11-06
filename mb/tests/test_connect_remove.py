"""`mb connect remove`: confirm, delete metadata and credential, fail closed."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from mb import cli
from mb import connect as c
from mb.cli import app
from mb.credential_store import CredentialStoreError, SecretProbe, SecretStore

runner = CliRunner()
SECRET = "acme-candles-fixture-credential"


@pytest.fixture()
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("MAINBRANCH_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("MB_CONNECT_SECRET_BACKEND", "local-file")
    target = tmp_path / "acme-candles"
    target.mkdir()
    return target


def connect(repo: Path, scope: str = "repo") -> str:
    result = c.connect_provider("cloudflare", repo=repo, token=SECRET, scope=scope)
    entry = c._read_config(repo)["providers"].get("cloudflare") or c._user_scope_provider_entry(
        c._read_config(repo)["repo_id"], "cloudflare"
    )
    assert result["ok"]
    assert entry is not None
    return str(entry["secrets"]["api_token"]["ref"])


def stored(ref: str) -> bool:
    return SecretStore("local-file").probe(ref).present


def remove(repo: Path, *args: str, tty: bool = False, answer: str = "") -> Any:
    with patch.object(cli, "_stdin_is_tty", lambda: tty):
        return runner.invoke(
            app, ["connect", "remove", "cloudflare", "--repo", str(repo), *args], input=answer
        )


def test_plan_changes_nothing(repo: Path) -> None:
    ref = connect(repo)
    plan = c.remove_provider("cloudflare", repo)
    assert plan["ok"] and not plan["applied"] and plan["repo_metadata"]
    assert stored(ref)
    assert "cloudflare" in c._read_config(repo)["providers"]


@pytest.mark.parametrize("scope", ["repo", "user"])
def test_remove_deletes_metadata_and_credential(repo: Path, scope: str) -> None:
    ref = connect(repo, scope)
    result = remove(repo, "--yes")
    assert result.exit_code == 0, result.output
    assert "removed: api_token credential (local-file)" in result.stdout
    assert SECRET not in result.output
    assert not stored(ref)
    config = c._read_config(repo)
    assert "cloudflare" not in config["providers"]
    assert c._user_scope_provider_entry(config["repo_id"], "cloudflare") is None


def test_remove_without_yes_refuses_off_a_terminal(repo: Path) -> None:
    ref = connect(repo)
    result = remove(repo)
    assert result.exit_code == 2
    assert "--yes" in result.stderr
    assert stored(ref)


def test_declined_confirmation_removes_nothing(repo: Path) -> None:
    ref = connect(repo)
    result = remove(repo, tty=True, answer="n\n")
    assert result.exit_code == 1
    assert "Nothing was removed." in result.stdout
    assert stored(ref)
    assert "cloudflare" in c._read_config(repo)["providers"]


def test_confirmed_prompt_removes(repo: Path) -> None:
    ref = connect(repo)
    result = remove(repo, tty=True, answer="y\n")
    assert result.exit_code == 0, result.output
    assert not stored(ref)


def test_not_connected_exits_one(repo: Path) -> None:
    result = remove(repo, "--yes")
    assert result.exit_code == 1
    assert "nothing to remove" in result.stdout


def test_unreachable_backend_fails_closed(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    ref = connect(repo)
    unreachable = SecretProbe("", False, False, "credential_store_timeout")
    monkeypatch.setattr(SecretStore, "probe", lambda self, *a, **k: unreachable)
    result = remove(repo, "--yes")
    assert result.exit_code == 1
    assert "Nothing was removed" in result.stderr
    monkeypatch.undo()
    monkeypatch.setenv("MAINBRANCH_HOME", str(repo.parent / "home"))
    assert stored(ref)
    assert "cloudflare" in c._read_config(repo)["providers"]


def _foreign_ref(value: str = "rowan-vale-other-business-credential") -> str:
    ref = c._secret_ref("other-business-repo-id", "cloudflare", "api_token")
    SecretStore("local-file").set(ref, value)
    return ref


@pytest.mark.parametrize("where", ["repo", "user"])
def test_remove_refuses_a_foreign_credential_ref(repo: Path, where: str) -> None:
    own = connect(repo, where)
    foreign = _foreign_ref()
    config = c._read_config(repo)
    if where == "repo":
        config["providers"]["cloudflare"]["secrets"]["api_token"]["ref"] = foreign
        c._write_config(repo, config)
    else:
        entry = c._user_scope_provider_entry(config["repo_id"], "cloudflare")
        assert entry is not None
        entry["secrets"]["api_token"]["ref"] = foreign
        c._write_user_scope_provider(
            config["repo_id"],
            repo_identity=config.get("repo_identity") or {},
            provider_id="cloudflare",
            entry=entry,
        )
    with pytest.raises(c.ConnectRefusal) as caught:
        c.remove_provider("cloudflare", repo, apply=True)
    assert caught.value.rule == c.REF_MISMATCH_STATE
    assert stored(foreign)
    assert stored(own)


def test_remove_refuses_a_foreign_ref_in_the_user_entry_beside_a_good_repo_entry(
    repo: Path,
) -> None:
    own = connect(repo)
    foreign = _foreign_ref()
    config = c._read_config(repo)
    entry = {"secrets": {"api_token": {"ref": foreign, "backend": "local-file"}}}
    c._write_user_scope_provider(
        config["repo_id"],
        repo_identity=config.get("repo_identity") or {},
        provider_id="cloudflare",
        entry=entry,
    )
    with pytest.raises(c.ConnectRefusal):
        c.remove_provider("cloudflare", repo, apply=True)
    assert stored(foreign)
    assert stored(own)
    assert "cloudflare" in c._read_config(repo)["providers"]


def _delete_then_lose_ack(monkeypatch: pytest.MonkeyPatch) -> None:
    real_delete = SecretStore.delete

    def delete_then_raise(self: SecretStore, target: str, *args: Any, **kwargs: Any) -> None:
        real_delete(self, target, *args, **kwargs)
        raise CredentialStoreError("credential_store_timeout")

    monkeypatch.setattr(SecretStore, "delete", delete_then_raise)


def test_delete_that_raised_after_deleting_is_restored(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ref = connect(repo)
    _delete_then_lose_ack(monkeypatch)
    result = remove(repo, "--yes")
    monkeypatch.undo()
    monkeypatch.setenv("MAINBRANCH_HOME", str(repo.parent / "home"))
    monkeypatch.setenv("MB_CONNECT_SECRET_BACKEND", "local-file")
    assert result.exit_code == 1
    assert "Everything was put back" in result.stderr
    assert stored(ref)
    assert SECRET not in result.output
    assert "cloudflare" in c._read_config(repo)["providers"]


def test_restore_that_fails_says_what_state_remains(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ref = connect(repo)
    _delete_then_lose_ack(monkeypatch)

    def refuse_set(self: SecretStore, *args: Any, **kwargs: Any) -> None:
        raise CredentialStoreError("credential_store_timeout")

    monkeypatch.setattr(SecretStore, "set", refuse_set)
    result = remove(repo, "--yes")
    monkeypatch.undo()
    monkeypatch.setenv("MAINBRANCH_HOME", str(repo.parent / "home"))
    monkeypatch.setenv("MB_CONNECT_SECRET_BACKEND", "local-file")
    assert result.exit_code == 1
    assert "Everything was put back" not in result.stderr
    assert "could not be put back" in result.stderr
    assert not stored(ref)
    assert "cloudflare" in c._read_config(repo)["providers"]
    assert SECRET not in result.output


def test_restore_is_verified_not_assumed(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    ref = connect(repo)
    _delete_then_lose_ack(monkeypatch)

    def set_that_does_not_stick(self: SecretStore, *args: Any, **kwargs: Any) -> None:
        return None

    monkeypatch.setattr(SecretStore, "set", set_that_does_not_stick)
    result = remove(repo, "--yes")
    monkeypatch.undo()
    monkeypatch.setenv("MAINBRANCH_HOME", str(repo.parent / "home"))
    monkeypatch.setenv("MB_CONNECT_SECRET_BACKEND", "local-file")
    assert "Everything was put back" not in result.stderr
    assert not stored(ref)


def _write_then_raise_once(monkeypatch: pytest.MonkeyPatch, *, restore_fails: bool) -> None:
    """The first config write lands and still raises; a later one works or is lost."""
    real_write = c._write_config
    calls: list[int] = []

    def write(repo: Path, config: dict[str, Any]) -> Path:
        calls.append(1)
        if len(calls) == 1:
            real_write(repo, config)
            raise OSError("acknowledgement lost")
        if restore_fails:
            raise OSError("disk full")
        return real_write(repo, config)

    monkeypatch.setattr(c, "_write_config", write)


def test_metadata_write_that_landed_then_raised_is_put_back(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ref = connect(repo)
    before = c._read_config(repo)["providers"]["cloudflare"]
    _write_then_raise_once(monkeypatch, restore_fails=False)
    result = remove(repo, "--yes")
    monkeypatch.undo()
    monkeypatch.setenv("MAINBRANCH_HOME", str(repo.parent / "home"))
    monkeypatch.setenv("MB_CONNECT_SECRET_BACKEND", "local-file")
    assert result.exit_code == 1
    assert "Everything was put back" in result.stderr
    assert c._read_config(repo)["providers"]["cloudflare"] == before
    assert stored(ref)


def test_metadata_restore_that_fails_makes_no_whole_state_claim(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ref = connect(repo)
    _write_then_raise_once(monkeypatch, restore_fails=True)
    result = remove(repo, "--yes")
    monkeypatch.undo()
    monkeypatch.setenv("MAINBRANCH_HOME", str(repo.parent / "home"))
    monkeypatch.setenv("MB_CONNECT_SECRET_BACKEND", "local-file")
    assert result.exit_code == 1
    assert "Everything was put back" not in result.stderr
    assert "could not be put back" in result.stderr
    assert "cloudflare" not in c._read_config(repo)["providers"]
    assert stored(ref)


def _user_scope_removal_that_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    real_remove = c._remove_user_scope_provider

    def remove_then_raise(repo_id: str, provider_id: str) -> None:
        real_remove(repo_id, provider_id)
        raise OSError("acknowledgement lost")

    monkeypatch.setattr(c, "_remove_user_scope_provider", remove_then_raise)


def test_user_scope_restore_is_read_back(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    ref = connect(repo, "user")
    repo_id = c._read_config(repo)["repo_id"]
    before = c._user_scope_provider_entry(repo_id, "cloudflare")
    _user_scope_removal_that_raises(monkeypatch)
    result = remove(repo, "--yes")
    monkeypatch.undo()
    monkeypatch.setenv("MAINBRANCH_HOME", str(repo.parent / "home"))
    monkeypatch.setenv("MB_CONNECT_SECRET_BACKEND", "local-file")
    assert "Everything was put back" in result.stderr
    assert c._user_scope_provider_entry(repo_id, "cloudflare") == before
    assert stored(ref)


def test_user_scope_restore_that_does_not_stick_makes_no_whole_state_claim(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    connect(repo, "user")
    _user_scope_removal_that_raises(monkeypatch)
    monkeypatch.setattr(c, "_write_user_scope_provider", lambda *a, **k: None)
    result = remove(repo, "--yes")
    assert "Everything was put back" not in result.stderr
    assert "could not be put back" in result.stderr


def test_metadata_failure_puts_the_credential_back(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ref = connect(repo)

    def fail(*args: Any, **kwargs: Any) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(c, "_write_config", fail)
    result = remove(repo, "--yes")
    assert result.exit_code == 1
    assert "Everything was put back" in result.stderr
    assert stored(ref)
    assert SECRET not in result.output
    assert "cloudflare" in c._read_config(repo)["providers"]
