"""`mb connect` finds the business repo from the git top level when --repo is not given."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from mb import connect
from mb.cli import app

runner = CliRunner()
SECRET = "sk_test_synthetic_repo_root_secret"
CHILD = [sys.executable, "-c", "pass"]
CHILD_PRINTS_PATH = [sys.executable, "-c", "import os;print(os.getcwd())"]


def make_git(folder: Path) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    git = folder / ".git"
    git.mkdir()
    (git / "HEAD").write_text("ref: refs/heads/main\n")
    return folder


@pytest.fixture()
def hub(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    for name in ("HOME", "XDG_STATE_HOME", "XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_CACHE_HOME"):
        monkeypatch.setenv(name, str(tmp_path / name))
    monkeypatch.delenv("XDG_RUNTIME_DIR", raising=False)
    for provider in connect.PROVIDERS:
        for name in provider.env_vars:
            monkeypatch.delenv(name, raising=False)
    target = make_git(tmp_path / "hub")
    connect.connect_provider("stripe", repo=target, token=SECRET)
    return target


def rows() -> list[dict[str, Any]]:
    path = connect.audit_path()
    if not path.exists():
        return []
    text = path.read_text()
    assert SECRET not in text
    return [json.loads(line) for line in text.splitlines()]


def run_exec(*extra: str) -> Any:
    return runner.invoke(app, ["connect", "exec", "stripe", *extra, "--", *CHILD])


def test_exec_from_a_subfolder_finds_the_hub(hub: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    sub = hub / "notes" / "deep"
    sub.mkdir(parents=True)
    monkeypatch.chdir(sub)
    result = run_exec()
    assert result.exit_code == 0, result.output
    assert rows()[-1]["result"] == "released"
    assert rows()[-1]["repo_id"] == connect._read_config(hub)["repo_id"]


def test_custom_provider_is_found_from_a_subfolder(
    hub: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    connect.connect_provider("acme-shop", repo=hub, token=SECRET, custom=True)
    sub = hub / "a"
    sub.mkdir()
    monkeypatch.chdir(sub)
    result = runner.invoke(app, ["connect", "exec", "acme-shop", "--", *CHILD])
    assert result.exit_code == 0, result.output


@pytest.mark.parametrize("verb", ["status", "test", "policy"])
def test_other_verbs_find_the_hub_from_a_subfolder(
    hub: Path, monkeypatch: pytest.MonkeyPatch, verb: str
) -> None:
    sub = hub / "x"
    sub.mkdir()
    monkeypatch.chdir(sub)
    args = ["connect", verb] if verb == "policy" else ["connect", verb, "stripe"]
    result = runner.invoke(app, [*args, "--json"])
    assert "no_business_repo" not in result.output
    assert "unknown provider" not in result.output


def test_token_from_a_subfolder_finds_the_hub(hub: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    sub = hub / "x"
    sub.mkdir()
    monkeypatch.chdir(sub)
    result = runner.invoke(app, ["connect", "token", "stripe", "--print"])
    assert result.exit_code == 0, result.output
    assert result.stdout == SECRET


def _assert_no_business_repo(result: Any, folder: Path) -> None:
    assert result.exit_code == 2, result.output
    assert "No business repo here" in result.stderr
    assert "cd into the business repo or pass --repo" in result.stderr
    assert "unknown provider" not in result.stderr
    assert SECRET not in result.output
    assert result.stdout == ""


@pytest.mark.parametrize("verb", ["exec", "token"])
def test_outside_any_repo_is_refused_and_logged(
    hub: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, verb: str
) -> None:
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    args = ["--print"] if verb == "token" else ["--", *CHILD]
    result = runner.invoke(app, ["connect", verb, "stripe", *args])
    _assert_no_business_repo(result, elsewhere)
    (row,) = rows()
    assert row["verb"] == verb
    assert row["result"] == "refused"
    assert row["reason"] == "no_business_repo"
    assert row["exit_code"] == 2


def test_json_failure_state(hub: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    result = runner.invoke(app, ["connect", "status", "--json"])
    assert result.exit_code == 2
    payload = json.loads(result.stdout)
    assert payload["state"] == "no_business_repo"


def test_git_repo_without_connect_yaml_is_refused(
    hub: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    plain = make_git(tmp_path / "plain")
    monkeypatch.chdir(plain)
    _assert_no_business_repo(run_exec(), plain)


def test_nested_git_repo_does_not_borrow_the_hub(
    hub: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    tool = make_git(hub / "tools" / "cloned")
    (tool / "src").mkdir()
    monkeypatch.chdir(tool / "src")
    result = run_exec()
    _assert_no_business_repo(result, tool)
    assert rows()[-1]["reason"] == "no_business_repo"


def test_stray_empty_dot_git_is_not_a_repo(hub: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    stray = hub / "stray"
    (stray / ".git").mkdir(parents=True)
    monkeypatch.chdir(stray)
    # No HEAD, so the stray folder is not a repo; the hub above it is.
    result = run_exec()
    assert result.exit_code == 0, result.output


def test_gitfile_counts_as_a_repo(
    hub: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    linked = tmp_path / "linked"
    linked.mkdir()
    (linked / ".git").write_text("gitdir: /somewhere/else\n")
    connect.connect_provider("stripe", repo=linked, token=SECRET)
    monkeypatch.chdir(linked)
    assert run_exec().exit_code == 0


def test_never_walks_above_the_git_top_level(hub: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # The hub's own parent has a connect.yaml too; the hub is the top, so it is used.
    outer = hub.parent
    (outer / ".mb").mkdir()
    (outer / ".mb" / "connect.yaml").write_text("version: 1\n")
    monkeypatch.chdir(hub)
    assert run_exec().exit_code == 0
    assert connect.find_business_repo(hub / "nothing-here") == hub


def test_copied_config_naming_another_repo_still_needs_rebind(
    hub: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    copy = make_git(tmp_path / "copy")
    (copy / ".mb").mkdir()
    (copy / ".mb" / "connect.yaml").write_text((hub / ".mb" / "connect.yaml").read_text())
    monkeypatch.chdir(copy)
    result = run_exec()
    assert result.exit_code == 2, result.output
    assert "never saved keys under" in result.stderr
    assert SECRET not in result.output


def test_explicit_repo_behaves_as_before(
    hub: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    assert run_exec("--repo", str(hub)).exit_code == 0
    # A folder that is not a repo is accepted as today: no repo search with --repo.
    result = runner.invoke(app, ["connect", "exec", "stripe", "--repo", ".", "--", *CHILD])
    assert "No business repo here" not in result.output
