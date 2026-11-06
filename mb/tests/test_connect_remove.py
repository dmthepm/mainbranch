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
from mb.credential_store import SecretProbe, SecretStore

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
