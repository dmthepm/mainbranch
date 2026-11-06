"""Direct-child argument safety with invented credentials only."""

import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import Mock

import pytest

from mb import connect

SECRET = "invented-credential-for-argv-tests"


@pytest.fixture()
def isolated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(
        connect,
        "caller_policy_status",
        lambda repo: {"exists": False, "caller": "test", "valid": True, "policy": None},
    )
    monkeypatch.setattr(connect, "_audit_parent", lambda: "test")
    monkeypatch.setattr(connect, "audit_path", lambda: tmp_path / "audit.jsonl")
    monkeypatch.setattr(
        connect,
        "read_token",
        lambda *args: {"ok": True, "provider": "stripe", "token": SECRET, "source": "test"},
    )
    return tmp_path


@pytest.mark.parametrize("argument", [SECRET, f"Authorization: Bearer {SECRET}"])
def test_secret_arguments_refused(
    isolated: Path, capsys: pytest.CaptureFixture[str], argument: str
) -> None:
    child = Mock()
    with pytest.raises(connect.ConnectRefusal) as caught:
        connect.exec_with_secret("stripe", [sys.executable, argument], isolated, runner=child)
    assert caught.value.rule == "exec_child_argv_secret"
    assert connect.release_refusal_exit_code(caught.value) == 3
    child.assert_not_called()
    output = capsys.readouterr()
    audit = (isolated / "audit.jsonl").read_text()
    assert SECRET not in str(caught.value) + output.out + output.err + audit
    assert argument not in str(caught.value) + audit
    row = json.loads(audit)
    assert (row["result"], row["reason"], row["policy"], row["exit_code"]) == (
        "refused",
        "exec_child_argv_secret",
        "refused",
        3,
    )


@pytest.mark.parametrize("secret", [SECRET, "", "a", "abc"])
def test_placeholder_and_short_values_allowed(
    isolated: Path, monkeypatch: pytest.MonkeyPatch, secret: str
) -> None:
    monkeypatch.setattr(
        connect, "read_token", lambda *args: {"ok": True, "provider": "stripe", "token": secret}
    )
    child = Mock(return_value=subprocess.CompletedProcess([], 0))
    command = [sys.executable, "${EXAMPLE_TOKEN}", "abc"]
    result = connect.exec_with_secret(
        "stripe", command, isolated, env_name="EXAMPLE_TOKEN", runner=child
    )
    assert result["ok"]
    assert child.call_args.args[0] == command
    child_token = child.call_args.kwargs["env"]["EXAMPLE_TOKEN"]
    assert child_token == secret


@pytest.mark.parametrize("shell", ["sh", "bash", "dash", "zsh", "/bin/sh"])
@pytest.mark.parametrize("reference", ["$EXAMPLE_TOKEN", "${EXAMPLE_TOKEN}"])
def test_shell_warning(
    isolated: Path, capsys: pytest.CaptureFixture[str], shell: str, reference: str
) -> None:
    child = Mock(return_value=subprocess.CompletedProcess([], 0))
    result = connect.exec_with_secret(
        "stripe",
        [shell, "-c", f'test -n "{reference}"'],
        isolated,
        env_name="EXAMPLE_TOKEN",
        runner=child,
    )
    assert result["ok"]
    stderr = capsys.readouterr().err
    assert stderr.count("shell expands") == 1
    assert "arguments" in stderr
    assert reference not in stderr
    assert SECRET not in stderr
    child.assert_called_once()


@pytest.mark.parametrize(
    "command",
    [
        ["sh", "-c", "test -n $OTHER"],
        ["sh", "-c", "test -n $EXAMPLE_TOKEN_SUFFIX"],
        [sys.executable, "-c", "$EXAMPLE_TOKEN"],
    ],
)
def test_no_shell_warning(
    isolated: Path, capsys: pytest.CaptureFixture[str], command: list[str]
) -> None:
    child = Mock(return_value=subprocess.CompletedProcess([], 0))
    assert connect.exec_with_secret(
        "stripe", command, isolated, env_name="EXAMPLE_TOKEN", runner=child
    )["ok"]
    assert "shell expands" not in capsys.readouterr().err
