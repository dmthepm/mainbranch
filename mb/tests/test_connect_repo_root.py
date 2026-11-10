"""`mb connect` finds the business repo from the git top level when --repo is not given."""

from __future__ import annotations

import errno
import json
import os
import shutil
import subprocess
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


def test_git_repo_without_connect_yaml_is_the_repo(
    hub: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    plain = make_git(tmp_path / "plain")
    monkeypatch.chdir(plain)
    result = run_exec()
    assert result.exit_code == 1, result.output
    assert "is not connected" in result.output
    assert "No business repo here" not in result.stderr


def test_nested_git_repo_does_not_borrow_the_hub(
    hub: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    tool = make_git(hub / "tools" / "cloned")
    (tool / "src").mkdir()
    monkeypatch.chdir(tool / "src")
    result = run_exec()
    assert result.exit_code == 1, result.output
    assert "is not connected" in result.output
    assert SECRET not in result.output
    assert connect.find_business_repo(tool / "src") == tool


def test_stray_empty_dot_git_refuses(hub: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    stray = hub / "stray"
    (stray / ".git").mkdir(parents=True)
    monkeypatch.chdir(stray)
    # A .git folder with no HEAD is a refusal, not a stray the hub above can replace.
    result = run_exec()
    assert result.exit_code == 2, result.output
    assert rows()[-1]["reason"] == "unreadable_repo_marker"


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


# --- an uninspectable git marker refuses; discovery never walks on to a parent ---

BREAKS = [
    "unreadable-gitfile",
    "unreadable-gitdir",
    "other-oserror",
    "dangling-link",
    "link-loop",
    "vanished-gitfile",
    "gitfile-parent-gone",
    "dangling-head",
    "vanished-head",
    "fifo-marker",
    "head-folder",
    "marker-gone",
    "marker-regular-gitfile",
    "marker-dangling-link",
    "empty-marker",
    "non-pointer-gitfile",
]
CHANGES = {"marker-gone", "marker-regular-gitfile", "marker-dangling-link"}
POST_LSTAT = {"vanished-gitfile", "gitfile-parent-gone", "vanished-head"}


def _break_nested_marker(hub: Path, kind: str, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A nested repo inside the hub whose ``.git`` cannot be inspected."""
    nested = hub / "nested"
    (nested / "src").mkdir(parents=True)
    marker = nested / ".git"
    if kind == "non-pointer-gitfile":
        marker.write_text("not a pointer\n")
    elif kind in {"unreadable-gitfile", "vanished-gitfile", "gitfile-parent-gone"}:
        marker.write_text("gitdir: /somewhere/else\n")
    elif kind == "empty-marker":
        marker.mkdir()
    else:
        make_git(nested)
    if kind == "fifo-marker":
        shutil.rmtree(marker)
        os.mkfifo(marker)
    elif kind == "head-folder":
        (marker / "HEAD").unlink()
        (marker / "HEAD").mkdir()
    elif kind == "dangling-link":
        shutil.rmtree(marker)
        marker.symlink_to(nested / "missing-git-dir")
    elif kind == "link-loop":
        shutil.rmtree(marker)
        marker.symlink_to(marker.name)
    elif kind == "dangling-head":
        (marker / "HEAD").unlink()
        (marker / "HEAD").symlink_to(nested / "missing-head")
    elif kind in POST_LSTAT:
        # The entry exists at lstat; the later read or stat then fails as if the
        # file or a path component vanished in between.
        error = NotADirectoryError if kind == "gitfile-parent-gone" else FileNotFoundError
        target = marker / "HEAD" if kind == "vanished-head" else marker
        seen: list[Path] = []
        real_lstat, real_stat, real_read = Path.lstat, Path.stat, Path.read_text

        def lstat(self: Path, *args: Any, **kwargs: Any) -> Any:
            result = real_lstat(self, *args, **kwargs)
            if self == marker:
                seen.append(self)
            return result

        def gone(real: Any) -> Any:
            def call(self: Path, *args: Any, **kwargs: Any) -> Any:
                if self == target and seen:
                    raise error(errno.ENOENT, "vanished after lstat")
                return real(self, *args, **kwargs)

            return call

        monkeypatch.setattr(Path, "lstat", lstat)
        monkeypatch.setattr(Path, "stat", gone(real_stat))
        monkeypatch.setattr(Path, "read_text", gone(real_read))
    if kind in CHANGES:
        # The marker was a folder at lstat and stat; it changes for real just
        # before HEAD is inspected, and the real stat then sees the new state.
        real = Path.stat
        done: list[bool] = []

        def changing(self: Path, *args: Any, **kwargs: Any) -> Any:
            if self == marker / "HEAD" and not done:
                done.append(True)
                marker.rename(nested / "saved-marker")
                if kind == "marker-regular-gitfile":
                    marker.write_text("gitdir: /somewhere/else\n")
                elif kind == "marker-dangling-link":
                    marker.symlink_to(nested / "missing-git-dir")
            return real(self, *args, **kwargs)

        monkeypatch.setattr(Path, "stat", changing)
    if kind == "other-oserror":
        real = Path.stat

        def failing(self: Path, *args: Any, **kwargs: Any) -> Any:
            if self == marker:
                raise OSError(errno.EIO, "Input/output error")
            return real(self, *args, **kwargs)

        monkeypatch.setattr(Path, "stat", failing)
    elif kind in {"unreadable-gitfile", "unreadable-gitdir"}:
        assert os.geteuid() != 0, "run as a non-root user: root can read a mode 0 marker"
        marker.chmod(0)
    return nested


def _restore(nested: Path) -> None:
    (nested / ".git").chmod(0o755)


@pytest.mark.parametrize("kind", BREAKS)
def test_finder_refuses_and_never_selects_the_parent(
    hub: Path, monkeypatch: pytest.MonkeyPatch, kind: str
) -> None:
    nested = _break_nested_marker(hub, kind, monkeypatch)
    try:
        with pytest.raises(connect.ConnectRefusal) as caught:
            connect.find_business_repo(nested / "src")
    finally:
        if kind in {"unreadable-gitfile", "unreadable-gitdir"}:
            _restore(nested)
    assert caught.value.rule == "unreadable_repo_marker"


@pytest.mark.parametrize("kind", BREAKS)
@pytest.mark.parametrize("verb", ["exec", "token"])
def test_cli_unreadable_marker_reads_no_key_launches_nothing_and_is_logged(
    hub: Path, monkeypatch: pytest.MonkeyPatch, kind: str, verb: str
) -> None:
    nested = _break_nested_marker(hub, kind, monkeypatch)
    reads: list[object] = []
    launches: list[object] = []

    def read_token(*args: Any, **kwargs: Any) -> str:
        reads.append(args)
        return SECRET

    monkeypatch.setattr(connect, "read_token", read_token)
    for owner, name in (
        (subprocess, "run"),
        (subprocess, "Popen"),
        (os, "execvp"),
        (os, "execvpe"),
    ):
        monkeypatch.setattr(owner, name, lambda *a, **k: launches.append(a))
    monkeypatch.chdir(nested / "src")
    args = ["--print"] if verb == "token" else ["--", *CHILD_PRINTS_PATH]
    try:
        result = runner.invoke(app, ["connect", verb, "stripe", *args])
    finally:
        if kind in {"unreadable-gitfile", "unreadable-gitdir"}:
            _restore(nested)
    assert result.exit_code == 2, result.output
    assert "Cannot read the git marker" in result.stderr
    assert SECRET not in result.output
    assert result.stdout == ""
    assert reads == [] and launches == []
    (row,) = rows()
    assert row["verb"] == verb
    assert row["result"] == "refused"
    assert row["reason"] == "unreadable_repo_marker"
    assert row["exit_code"] == 2


def test_failing_marker_at_a_higher_level_stops_the_walk(
    hub: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The repo marker in the starting folder is absent; an ancestor's marker is a
    # dangling link. Discovery refuses there and never selects the hub above it.
    mid = hub / "mid"
    start = mid / "deep" / "er"
    start.mkdir(parents=True)
    (mid / ".git").symlink_to(mid / "missing-git-dir")
    reads: list[object] = []
    launches: list[object] = []

    def read_token(*args: Any, **kwargs: Any) -> str:
        reads.append(args)
        return SECRET

    monkeypatch.setattr(connect, "read_token", read_token)
    for owner, name in ((subprocess, "run"), (subprocess, "Popen"), (os, "execvp")):
        monkeypatch.setattr(owner, name, lambda *a, **k: launches.append(a))
    with pytest.raises(connect.ConnectRefusal) as caught:
        connect.find_business_repo(start)
    assert caught.value.rule == "unreadable_repo_marker"
    monkeypatch.chdir(start)
    for verb, args in (("exec", ["--", *CHILD_PRINTS_PATH]), ("token", ["--print"])):
        result = runner.invoke(app, ["connect", verb, "stripe", *args])
        assert result.exit_code == 2, result.output
        assert SECRET not in result.output and result.stdout == ""
    assert reads == [] and launches == []
    logged = rows()
    assert [(r["verb"], r["result"], r["reason"]) for r in logged] == [
        ("exec", "refused", "unreadable_repo_marker"),
        ("token", "refused", "unreadable_repo_marker"),
    ]


@pytest.fixture()
def fresh(tmp_path: Path, hub: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A git repo with no .mb/connect.yaml, as `mb init` leaves it."""
    repo = make_git(tmp_path / "fresh")
    monkeypatch.chdir(repo)
    return repo


@pytest.mark.parametrize(
    "args",
    [["status"], ["status", "stripe"], ["test", "stripe"], ["policy"]],
)
def test_fresh_repo_answers_not_connected_instead_of_no_business_repo(
    fresh: Path, args: list[str]
) -> None:
    result = runner.invoke(app, ["connect", *args, "--json"])
    assert "no_business_repo" not in result.output, result.output
    assert "No business repo here" not in result.output


def test_fresh_repo_status_reports_none_configured(fresh: Path) -> None:
    result = runner.invoke(app, ["connect", "status", "--json"])
    assert result.exit_code == 0, result.output
    assert "no_business_repo" not in result.output


@pytest.mark.parametrize("verb", ["exec", "token"])
def test_fresh_repo_exec_and_token_answer_not_connected(fresh: Path, verb: str) -> None:
    args = ["--print"] if verb == "token" else ["--", *CHILD]
    result = runner.invoke(app, ["connect", verb, "stripe", *args])
    assert result.exit_code == 1, result.output
    assert "is not connected" in result.output
    assert "No business repo here" not in result.stderr
    assert result.stdout == ""
    assert SECRET not in result.output


def test_finder_returns_a_git_top_without_connect_yaml(fresh: Path) -> None:
    assert connect.find_business_repo(fresh) == fresh


REPO_COMMANDS = [
    [],
    ["list"],
    ["plan"],
    ["doctor"],
    ["hygiene"],
    ["identity"],
    ["rotate", "stripe"],
    ["hydrate"],
    ["remove", "stripe"],
    ["rebind"],
]


@pytest.mark.parametrize("args", REPO_COMMANDS)
@pytest.mark.parametrize("nested", [False, True])
def test_repo_commands_match_explicit_root_from_subfolder(
    hub: Path, monkeypatch: pytest.MonkeyPatch, args: list[str], nested: bool
) -> None:
    root = make_git(hub / "clone") if nested else hub
    sub = root / "notes" / "deep"
    sub.mkdir(parents=True)
    monkeypatch.chdir(sub)
    expected = runner.invoke(app, ["connect", *args, "--repo", str(root), "--json"])
    result = runner.invoke(app, ["connect", *args, "--json"])
    assert result.exit_code == expected.exit_code, result.output
    assert json.loads(result.stdout) == json.loads(expected.stdout)
    assert SECRET not in result.output


@pytest.mark.parametrize("args", [*REPO_COMMANDS, ["repair", "--keychain"]])
def test_repo_commands_refuse_outside_git(
    hub: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, args: list[str]
) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    monkeypatch.chdir(outside)
    result = runner.invoke(app, ["connect", *args, "--json"])
    assert result.exit_code == 2, result.output
    assert json.loads(result.stdout)["state"] == "no_business_repo"


@pytest.mark.parametrize("nested", [False, True])
def test_repair_selects_current_repo_from_subfolder(
    hub: Path, monkeypatch: pytest.MonkeyPatch, nested: bool
) -> None:
    root = make_git(hub / "clone") if nested else hub
    sub = root / "notes"
    sub.mkdir()
    monkeypatch.chdir(sub)
    monkeypatch.setattr("typer.testing._NamedTextIOWrapper.isatty", lambda self: True)

    def repair(repo: str, *, interactive: bool) -> dict[str, Any]:
        assert interactive
        return {"ok": True, "repo": str(Path(repo).resolve())}

    # Exercise discovery without opening a machine keychain dialog.
    monkeypatch.setattr(connect, "repair_keychain", repair)
    result = runner.invoke(app, ["connect", "repair", "--keychain", "--json"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["repo"] == str(root)


def test_hygiene_scans_root_config_from_subfolder(
    hub: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (hub / ".mcp.json").write_text('{"mcpServers": {}}\n')
    sub = hub / "notes"
    sub.mkdir()
    monkeypatch.chdir(sub)
    result = runner.invoke(app, ["connect", "hygiene", "--json"])
    assert result.exit_code == 0, result.output
    assert ".mcp.json" in json.loads(result.stdout)["surfaces_scanned"]


def test_audit_reads_machine_log_outside_git(
    hub: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    monkeypatch.chdir(outside)
    result = runner.invoke(app, ["connect", "audit", "--json"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout) == []
