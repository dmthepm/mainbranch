"""Credential release decisions through the CLI, using synthetic local state."""

from __future__ import annotations

import hashlib
import json
import os
import stat
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from mb import connect
from mb.cli import app

runner = CliRunner()
SECRET = "fixture-credential-only"
FIELDS = {
    "ts",
    "verb",
    "provider",
    "repo_id",
    "scope",
    "result",
    "reason",
    "exit_code",
    "pid",
    "ppid",
    "parent",
    "flags",
}


@pytest.fixture()
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    for provider in connect.PROVIDERS:
        for name in provider.env_vars:
            monkeypatch.delenv(name, raising=False)
    for name in ("XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_CACHE_HOME", "XDG_RUNTIME_DIR"):
        monkeypatch.setenv(name, str(tmp_path / name))
    target = tmp_path / "repo"
    target.mkdir()
    connect.connect_provider("cloudflare", repo=target, token=SECRET)
    return target


def invoke(repo: Path, verb: str, *args: Any) -> Any:
    return runner.invoke(app, ["connect", verb, "cloudflare", "--repo", str(repo), *args])


def entries() -> list[dict[str, Any]]:
    return [json.loads(line) for line in connect.audit_path().read_text().splitlines()]


@pytest.mark.parametrize(
    "extra,present,flags",
    [
        ([], False, []),
        (["--keep-env", "MB_TEST_UNRELATED_SECRET"], True, ["keep_env"]),
        (["--inherit-env"], True, ["inherit_env"]),
    ],
)
def test_exec_environment_cli(
    repo: Path, monkeypatch: pytest.MonkeyPatch, extra: list[str], present: bool, flags: list[str]
) -> None:
    monkeypatch.setenv("MB_TEST_UNRELATED_SECRET", "x")
    monkeypatch.setenv("LC_ALL", "C")
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "parent-value")
    output = repo / "child.json"
    code = "import json,os,sys; open(sys.argv[1],'w').write(json.dumps(dict(os.environ)))"
    result = invoke(repo, "exec", *extra, "--", sys.executable, "-c", code, str(output))
    assert result.exit_code == 0, result.output
    child = json.loads(output.read_text())
    assert ("MB_TEST_UNRELATED_SECRET" in child) == present
    assert child["CLOUDFLARE_API_TOKEN"] == SECRET
    for name in ("PATH", "HOME", "LC_ALL"):
        expected = os.environ[name]
        actual = child[name]
        assert actual == expected
    assert entries()[0]["flags"] == flags


@pytest.mark.parametrize(
    "extra,reason",
    [
        (["--keep-env", "CLOUDFLARE_API_TOKEN"], "exec_env_conflict"),
        (["--keep-env", "BAD-NAME"], "exec_env_name"),
        (["--env", "BAD-NAME"], "exec_env_name"),
    ],
)
def test_exec_refused(repo: Path, extra: list[str], reason: str) -> None:
    result = invoke(repo, "exec", *extra, "--", "unused-child-argument")
    assert result.exit_code == 2
    assert len(entries()) == 1
    assert entries()[0]["result"] == "refused"
    assert entries()[0]["reason"] == reason
    assert entries()[0]["exit_code"] == 2


@pytest.mark.parametrize("tty", [True, False])
def test_token_print_cli(repo: Path, monkeypatch: pytest.MonkeyPatch, tty: bool) -> None:
    original = connect.token_for_output

    def with_stdin(*args: Any, **kwargs: Any) -> Any:
        with patch.object(sys, "stdin", SimpleNamespace(isatty=lambda: tty)):
            return original(*args, **kwargs)

    monkeypatch.setattr(connect, "token_for_output", with_stdin)
    result = invoke(repo, "token", "--print")
    assert result.exit_code == 0, result.output
    assert result.stdout == SECRET
    assert ("deprecated" in result.stderr) == (not tty)
    assert entries()[0]["flags"] == (["print"] if tty else ["print", "print_noninteractive"])


@pytest.mark.parametrize("kind", ["file", "pipe", "terminal"])
def test_token_refuses_all_stdout_destinations(repo: Path, kind: str) -> None:
    argv = [sys.executable, "-m", "mb", "connect", "token", "cloudflare", "--repo", str(repo)]
    if kind == "file":
        with (repo / "stdout").open("w") as stream:
            result = subprocess.run(argv, stdout=stream, stderr=subprocess.PIPE, text=True)
        stdout = (repo / "stdout").read_text()
    elif kind == "terminal":
        import pty

        leader, follower = pty.openpty()
        try:
            result = subprocess.run(argv, stdout=follower, stderr=subprocess.PIPE, text=True)
            os.close(follower)
            follower = -1
            try:
                stdout = os.read(leader, 1024).decode()
            except OSError:
                stdout = ""
        finally:
            os.close(leader)
            if follower != -1:
                os.close(follower)
    else:
        result = subprocess.run(argv, capture_output=True, text=True)
        stdout = result.stdout
    assert result.returncode == 3
    assert stdout == ""
    assert "--env NAME" in result.stderr
    assert len(entries()) == 1
    assert entries()[0]["reason"] == "token_print"
    assert entries()[0]["exit_code"] == 3


def test_audit_schema_permissions_and_no_sensitive_content(repo: Path) -> None:
    assert (
        invoke(repo, "exec", "--", sys.executable, "-c", "pass", "private-child-argument").exit_code
        == 0
    )
    assert invoke(repo, "exec").exit_code == 2
    assert invoke(repo, "token", "--print").exit_code == 0
    assert invoke(repo, "token").exit_code == 3
    (repo / ".mb/connect.yaml").unlink()
    assert invoke(repo, "exec", "--", "unused").exit_code == 1
    rows = entries()
    assert len(rows) == 5
    assert [(r["verb"], r["result"], r["reason"], r["exit_code"]) for r in rows] == [
        ("exec", "released", "", 0),
        ("exec", "refused", "exec_no_command", 2),
        ("token", "released", "", 0),
        ("token", "refused", "token_print", 3),
        ("exec", "failed", "not_connected", 1),
    ]
    for row in rows:
        assert set(row) == FIELDS
        assert row["provider"] == "cloudflare"
        assert row["flags"] == sorted(row["flags"])
        assert len(row["parent"]) <= 64
    assert rows[0]["scope"] == "repo"
    assert rows[0]["repo_id"]
    assert stat.S_IMODE(connect.audit_path().stat().st_mode) == 0o600
    assert stat.S_IMODE(connect.audit_path().parent.stat().st_mode) == 0o700
    text = connect.audit_path().read_text()
    for value in (SECRET, hashlib.sha256(SECRET.encode()).hexdigest(), "private-child-argument"):
        assert value not in text


@pytest.mark.parametrize("verb", ["exec", "token"])
def test_audit_unavailable_prevents_release(
    repo: Path, monkeypatch: pytest.MonkeyPatch, verb: str
) -> None:
    blocked = repo / "blocked"
    blocked.write_text("not a directory")
    monkeypatch.setenv("XDG_STATE_HOME", str(blocked))
    marker = repo / "child-started"
    args = (
        ["--print"]
        if verb == "token"
        else [
            "--",
            sys.executable,
            "-c",
            "import pathlib,sys; pathlib.Path(sys.argv[1]).touch()",
            str(marker),
        ]
    )
    result = invoke(repo, verb, *args)
    assert result.exit_code == 1
    assert "audit_unavailable" in result.stderr
    assert str(blocked / "mainbranch") in result.stderr
    assert result.stdout == ""
    assert not marker.exists()
    refused = invoke(repo, "token")
    assert refused.exit_code == 3


def test_audit_reader(repo: Path) -> None:
    empty = runner.invoke(app, ["connect", "audit"])
    assert empty.exit_code == 0
    assert "No audit entries" in empty.stdout
    for provider in ("cloudflare", "stripe", "cloudflare"):
        assert (
            runner.invoke(app, ["connect", "token", provider, "--repo", str(repo)]).exit_code == 3
        )
    args = ["connect", "audit", "--limit", "1", "--provider", "cloudflare"]
    result = runner.invoke(app, [*args, "--json"])
    assert result.exit_code == 0
    assert len(json.loads(result.stdout)) == 1
    assert json.loads(result.stdout)[0]["provider"] == "cloudflare"
    table = runner.invoke(app, args)
    assert table.exit_code == 0
    assert "cloudflare" in table.stdout
    assert "stripe" not in table.stdout
    assert len(entries()) == 3


@pytest.mark.parametrize("provider", ["CLOUDFLARE", "cloudflare-pages"])
def test_exec_alias_uses_canonical_variable(repo: Path, provider: str) -> None:
    result = runner.invoke(
        app,
        [
            "connect",
            "exec",
            provider,
            "--repo",
            str(repo),
            "--keep-env",
            "CLOUDFLARE_API_TOKEN",
            "--",
            "unused",
        ],
    )
    assert result.exit_code == 2
    assert entries()[0]["reason"] == "exec_env_conflict"


@pytest.mark.parametrize("verb", ["exec", "token"])
@pytest.mark.parametrize(
    "args,reason", [([], "provider_required"), (["cloudflare", "--json"], "json_not_supported")]
)
def test_usage_refusals_are_audited(
    repo: Path,
    verb: str,
    args: list[str],
    reason: str,
) -> None:
    result = runner.invoke(app, ["connect", verb, *args, "--repo", str(repo)])
    assert result.exit_code == 2
    assert len(entries()) == 1
    assert entries()[0]["reason"] == reason
    assert entries()[0]["result"] == "refused"


def test_token_failure_is_audited(repo: Path) -> None:
    result = runner.invoke(app, ["connect", "token", "stripe", "--print", "--repo", str(repo)])
    assert result.exit_code == 1
    assert result.stdout == ""
    assert entries()[0]["result"] == "failed"
    assert entries()[0]["reason"] == "not_connected"
    assert entries()[0]["exit_code"] == 1


def test_audit_scrubs_all_string_fields(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(connect, "_audit_parent", lambda: "Bearer fixture-token-for-scrubbing")
    connect.write_release_audit(
        "token",
        "Bearer fixture-token-for-scrubbing",
        repo,
        result="refused",
        flags=[],
        reason="token_print",
        exit_code=3,
    )
    text = connect.audit_path().read_text()
    assert "fixture-token-for-scrubbing" not in text


def test_audit_does_not_restore_directory_write_permission(repo: Path) -> None:
    assert invoke(repo, "token").exit_code == 3
    directory = connect.audit_path().parent
    directory.chmod(0o500)
    try:
        assert invoke(repo, "token").exit_code == 3
        assert stat.S_IMODE(directory.stat().st_mode) == 0o500
    finally:
        directory.chmod(0o700)
