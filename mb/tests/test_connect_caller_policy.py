"""Caller-policy contracts with synthetic credentials and process ancestry."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any
from unittest.mock import Mock

import pytest
import yaml
from typer.testing import CliRunner

from mb import connect
from mb.cli import app

runner = CliRunner()
SECRET = "sk_test_synthetic_caller_policy_secret"


@pytest.fixture()
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    for name in (
        "HOME",
        "XDG_STATE_HOME",
        "XDG_CONFIG_HOME",
        "XDG_DATA_HOME",
        "XDG_CACHE_HOME",
        "XDG_RUNTIME_DIR",
    ):
        monkeypatch.setenv(name, str(tmp_path / name))
    for provider in connect.PROVIDERS:
        for name in provider.env_vars:
            monkeypatch.delenv(name, raising=False)
    target = tmp_path / "repo"
    target.mkdir()
    for provider_id in ("stripe", "cloudflare"):
        connect.connect_provider(provider_id, repo=target, token=SECRET)
    ancestry(monkeypatch, "claude")
    monkeypatch.chdir(target)
    return target


def ancestry(monkeypatch: pytest.MonkeyPatch, parent: str) -> None:
    table = {os.getppid(): (12345678, "bash"), 12345678: (0, parent)}
    monkeypatch.setattr(connect, "_process_info", lambda pid: table[pid])


def policy(repo: Path, value: Any) -> None:
    config = connect._read_config(repo)
    config["caller_policy"] = value
    connect._write_config(repo, config)


def invoke(repo: Path, verb: str, provider: str = "stripe", *extra: str) -> Any:
    args = ["connect", verb, provider, "--repo", str(repo)]
    args += ["--print"] if verb == "token" else ["--", sys.executable, "-c", "pass"]
    return runner.invoke(app, [*args, *extra])


def rows() -> list[dict[str, Any]]:
    text = connect.audit_path().read_text()
    for value in (SECRET, hashlib.sha256(SECRET.encode()).hexdigest(), "private-env-value"):
        assert value not in text
    return [json.loads(line) for line in text.splitlines()]


def assert_refused(result: Any, rule: str, code: int = 3) -> None:
    assert result.exit_code == code, result.output
    assert result.stdout == ""
    assert rule in result.stderr
    assert "mb connect policy" in result.stderr
    assert "docs/connect.md" in result.stderr
    assert len(rows()) == 1
    assert rows()[0]["result"] == "refused"
    assert rows()[0]["reason"] == rule
    assert rows()[0]["exit_code"] == code
    assert rows()[0]["policy"] == "refused"


@pytest.mark.parametrize("verb", ["exec", "token"])
def test_absent_policy(repo: Path, verb: str) -> None:
    result = invoke(repo, verb)
    assert result.exit_code == 0, result.output
    assert rows()[0]["policy"] == "none"
    assert rows()[0]["caller"] == "bash"


@pytest.mark.parametrize("verb", ["exec", "token"])
@pytest.mark.parametrize("provider", ["stripe", "cloudflare"])
def test_listed_caller(
    repo: Path, monkeypatch: pytest.MonkeyPatch, verb: str, provider: str
) -> None:
    policy(repo, {"callers": {"claude": ["stripe"]}})
    read = Mock(side_effect=AssertionError("credential read on refusal"))
    if provider == "cloudflare":
        monkeypatch.setattr(connect, "read_token", read)
        monkeypatch.setattr(subprocess, "run", Mock(side_effect=AssertionError("child started")))
    result = invoke(repo, verb, provider)
    if provider == "stripe":
        assert result.exit_code == 0, result.output
        assert rows()[0]["policy"] == "allowed"
    else:
        assert_refused(result, "caller_policy_provider")
        read.assert_not_called()
    assert rows()[0]["caller"] == "claude"


@pytest.mark.parametrize("verb", ["exec", "token"])
@pytest.mark.parametrize("default", ["allow", "deny"])
def test_unlisted_caller(
    repo: Path, monkeypatch: pytest.MonkeyPatch, verb: str, default: str
) -> None:
    policy(repo, {"callers": {"claude": ["stripe"]}, "default": default})
    ancestry(monkeypatch, "cron")
    if default == "deny":
        monkeypatch.setattr(connect, "read_token", Mock(side_effect=AssertionError("read")))
    result = invoke(repo, verb)
    if default == "allow":
        assert result.exit_code == 0, result.output
        assert rows()[0]["policy"] == "allowed"
    else:
        assert_refused(result, "caller_policy_caller")
    assert rows()[0]["caller"] == "bash"


@pytest.mark.parametrize("verb", ["exec", "token"])
def test_policy_provider_alias(repo: Path, verb: str) -> None:
    policy(repo, {"callers": {"claude": ["CLOUDFLARE_PAGES"]}})
    assert invoke(repo, verb, "cloudflare").exit_code == 0
    assert rows()[0]["policy"] == "allowed"


@pytest.mark.parametrize("verb", ["exec", "token"])
@pytest.mark.parametrize("location", ["root", "subfolder", "outside", "symlink"])
def test_working_dirs(
    repo: Path, monkeypatch: pytest.MonkeyPatch, verb: str, location: str
) -> None:
    policy(
        repo,
        {
            "working_dirs": ["."],
            "default": "deny" if location in {"outside", "symlink"} else "allow",
        },
    )
    outside = repo.parent / "outside"
    outside.mkdir()
    sub = repo / "sub"
    sub.mkdir()
    link = repo / "link"
    link.symlink_to(outside, target_is_directory=True)
    monkeypatch.chdir(
        {"root": repo, "subfolder": sub, "outside": outside, "symlink": link}[location]
    )
    if location in {"outside", "symlink"}:
        monkeypatch.setattr(connect, "read_token", Mock(side_effect=AssertionError("read")))
        assert_refused(invoke(repo, verb), "caller_policy_working_dir")
    else:
        assert invoke(repo, verb).exit_code == 0


@pytest.mark.parametrize("verb", ["exec", "token"])
@pytest.mark.parametrize(
    "value,key",
    [
        ({"unknown": "do-not-echo-this-value"}, "caller_policy.unknown"),
        ({"default": []}, "caller_policy.default"),
        ({"callers": {"claude": ["not-a-provider"]}}, "caller_policy.callers"),
        ({"callers": {"invalid caller": ["stripe"]}}, "caller_policy.callers"),
        (None, "caller_policy"),
        ({"callers": []}, "caller_policy.callers"),
        ({"callers": {"claude": "stripe"}}, "caller_policy.callers"),
        ({"callers": {"claude": [5]}}, "caller_policy.callers"),
        ({"working_dirs": [5]}, "caller_policy.working_dirs"),
    ],
)
def test_invalid_policy(
    repo: Path, monkeypatch: pytest.MonkeyPatch, verb: str, value: Any, key: str
) -> None:
    policy(repo, value)
    read = Mock(side_effect=AssertionError("read"))
    monkeypatch.setattr(connect, "read_token", read)
    result = invoke(repo, verb)
    assert_refused(result, "caller_policy_invalid", 1)
    assert str(repo / ".mb/connect.yaml") in result.stderr
    assert key in result.stderr
    assert "do-not-echo-this-value" not in result.stderr
    read.assert_not_called()
    shown = runner.invoke(app, ["connect", "policy", "--repo", str(repo)])
    assert shown.exit_code == 1
    assert key in shown.stdout


@pytest.mark.parametrize(
    "command",
    [
        ["printenv"],
        ["/usr/bin/printenv", "PATH"],
        ["env"],
        ["env", "-i"],
        ["env", "FOO=private-env-value"],
        ["env", "FOO-BAR=private-env-value"],
        ["env", "-u", "FOO"],
        ["env", "--", "FOO=1"],
        ["env", "-0u", "FOO"],
        ["env", "-iu", "FOO"],
        ["env", "-0uFOO"],
        ["env", "-iC", "/tmp"],
        ["env", "-", "FOO=1"],
        ["env", "--un", "FOO"],
        ["env", "--unset=FOO"],
        ["env", "--ch", "/tmp"],
        ["env", "-S", "FOO=1"],
        ["env", "-S", "-i FOO=1"],
        ["env", "--split-string=-u FOO"],
        ["env", "-S", "${UNSET_NAME}"],
        ["env", "-S", "\\c"],
        ["env", "-S", "'unbalanced"],
    ],
)
def test_child_dump_refusal(
    repo: Path, monkeypatch: pytest.MonkeyPatch, command: list[str]
) -> None:
    read = Mock(side_effect=AssertionError("read"))
    child = Mock(side_effect=AssertionError("child"))
    monkeypatch.setattr(connect, "read_token", read)
    monkeypatch.setattr(subprocess, "run", child)
    result = runner.invoke(app, ["connect", "exec", "stripe", "--repo", str(repo), "--", *command])
    assert_refused(result, "exec_child_env_dump")
    read.assert_not_called()
    child.assert_not_called()


@pytest.mark.parametrize(
    "command",
    [
        ["env", "FOO=1", "true"],
        ["/usr/bin/env", "true"],
        ["env", "-u", "FOO", "true"],
        ["env", "-iu", "FOO", "true"],
        ["env", "-uFOO", "true"],
        ["env", "--un", "FOO", "true"],
        ["env", "-S", "FOO=1 true"],
        ["env", "-S", "true"],
        ["env", "--", "FOO=1", "true"],
    ],
)
def test_env_with_child_allowed(repo: Path, command: list[str]) -> None:
    result = runner.invoke(app, ["connect", "exec", "stripe", "--repo", str(repo), "--", *command])
    assert result.exit_code == 0, result.output
    assert rows()[0]["policy"] == "none"


def test_config_round_trip(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    original_policy = {"callers": {"claude": ["stripe"]}, "default": "deny", "working_dirs": ["."]}
    policy(repo, original_policy)
    config = connect._read_config(repo)
    extra = {"nested": ["example", 42]}
    config["future_config"] = extra
    connect._write_config(repo, config)
    result = runner.invoke(
        app,
        [
            "connect",
            "stripe",
            "--repo",
            str(repo),
            "--token-stdin",
            "--source",
            "op://example/item/field",
        ],
        input=SECRET,
    )
    assert result.exit_code == 0, result.output
    for key, expected in (("caller_policy", original_policy), ("future_config", extra)):
        assert yaml.safe_load((repo / ".mb/connect.yaml").read_text())[key] == expected
    monkeypatch.setattr(connect, "_read_onepassword_ref", lambda *a, **kw: SECRET)
    monkeypatch.setattr(
        connect,
        "_validate_with_provider",
        lambda *a, **kw: {
            "ok": True,
            "state": "ready",
            "summary": "synthetic probe",
            "checked_at": "2026-01-01T00:00:00Z",
            "provider_verified": True,
        },
    )
    result = runner.invoke(app, ["connect", "rotate", "stripe", "--repo", str(repo)])
    assert result.exit_code == 0, result.output
    after = yaml.safe_load((repo / ".mb/connect.yaml").read_text())
    assert after["caller_policy"] == original_policy
    assert after["future_config"] == extra


@pytest.mark.parametrize("state", ["absent", "valid", "invalid"])
@pytest.mark.parametrize("json_out", [False, True])
def test_policy_command(repo: Path, state: str, json_out: bool) -> None:
    if state != "absent":
        policy(
            repo,
            {"callers": {"claude": ["stripe"]}} if state == "valid" else {"default": "invalid"},
        )
    before = (repo / ".mb/connect.yaml").read_bytes()
    result = runner.invoke(
        app, ["connect", "policy", "--repo", str(repo), *(["--json"] if json_out else [])]
    )
    assert result.exit_code == (1 if state == "invalid" else 0), result.output
    expected_caller = "claude" if state == "valid" else "bash"
    assert connect.CALLER_POLICY_ADVISORY in result.stdout
    if json_out:
        shown = json.loads(result.stdout)
        assert shown["exists"] == (state != "absent")
        assert shown["valid"] == (state != "invalid")
        assert shown["caller"] == expected_caller
        if state == "valid":
            assert shown["policy"] == {"callers": {"claude": ["stripe"]}, "default": "allow"}
        if state == "invalid":
            assert "caller_policy.default" in shown["error"]
    else:
        assert ("present" if state == "valid" else state) in result.stdout
        assert f"Caller: {expected_caller}" in result.stdout
    assert (repo / ".mb/connect.yaml").read_bytes() == before
    assert not connect.audit_path().exists()


def test_audit_scrubs_context(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(connect, "resolve_caller", lambda _: "Bearer synthetic-hidden")
    assert invoke(repo, "exec").exit_code == 0
    text = connect.audit_path().read_text()
    for value in (
        SECRET,
        hashlib.sha256(SECRET.encode()).hexdigest(),
        "synthetic-hidden",
        "pass",
        "private-env-value",
    ):
        assert value not in text
    assert "caller" in rows()[0]
    assert "policy" in rows()[0]


def test_caller_resolution() -> None:
    start = os.getppid()
    table = {
        start: (10000001, "/bin/bash"),
        10000001: (10000002, "/opt/claude"),
        10000002: (0, "codex"),
    }
    assert (
        connect.resolve_caller({"claude": [], "codex": []}, process_table=table.__getitem__)
        == "claude"
    )
    assert connect.resolve_caller({}, process_table=table.__getitem__) == "bash"
    assert (
        connect.resolve_caller({}, process_table=lambda _: (_ for _ in ()).throw(OSError())) == ""
    )
    calls = []

    def deep(pid: int) -> tuple[int, str]:
        calls.append(pid)
        return pid + 1, "bash"

    assert connect.resolve_caller({"claude": []}, process_table=deep) == "bash"
    assert len(calls) == 8


def test_process_info_platforms(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "platform", "darwin")
    run = Mock(return_value=subprocess.CompletedProcess([], 0, " 12 /opt/example/claude\n"))
    monkeypatch.setattr(subprocess, "run", run)
    assert connect._process_info(99) == (12, "/opt/example/claude")
    assert run.call_args.args[0] == ["ps", "-o", "ppid=,comm=", "-p", "99"]
    monkeypatch.setattr(sys, "platform", "linux")
    read_text = Mock(side_effect=["99 (name with ) parens) S 12 1 1", "claude\n"])
    monkeypatch.setattr(Path, "read_text", read_text)
    assert connect._process_info(99) == (12, "claude")


@pytest.mark.parametrize("verb", ["exec", "token"])
def test_absolute_and_empty_working_dirs(repo: Path, verb: str) -> None:
    policy(repo, {"working_dirs": [str(repo)]})
    assert invoke(repo, verb).exit_code == 0
    connect.audit_path().unlink()
    policy(repo, {"working_dirs": []})
    assert_refused(invoke(repo, verb), "caller_policy_working_dir")


@pytest.mark.parametrize("verb", ["exec", "token"])
def test_invalid_yaml_keeps_existing_failure_rule(repo: Path, verb: str) -> None:
    (repo / ".mb/connect.yaml").write_text("providers: [invalid YAML")
    result = invoke(repo, verb)
    assert result.exit_code == 2
    assert rows()[0]["reason"] == "invalid_request"
    assert rows()[0]["policy"] == "none"
